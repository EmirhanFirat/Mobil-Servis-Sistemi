"""TalepAkış canlı demo kontrolü: yalnızca okur, model çağrısı yapmaz, gizli bilgi kullanmaz.

Kontrol edilenler: statik demo sitesi (sayfa, CSP'deki API adresi, önceden kaydedilmiş sonuçlar),
API `/health` (uyanma süresi dahil), `/demo/status` (veritabanı ve Jev demosu hazır mı), üretimde
`/docs`'un kapalı olması ve temel güvenlik başlıkları.

Kullanım:
    python canli_kontrol.py                # okunur rapor; hata varsa çıkış kodu 1
    python canli_kontrol.py --json         # makine için
    python canli_kontrol.py --cron         # her şey yolundaysa hiçbir şey yazmaz; çıkış kodu hep 0

Yalnızca standart kütüphane kullanır (Hermes'in kendi Python'unda da çalışır).
Not: `/health` ve `/demo/status` uyuyan API'yi ve Neon'u uyandırır. Bu betik izleme içindir,
uyanık tutmak için sık çalıştırılmaz (DECISIONS D35/D36).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

VARSAYILAN_API = "https://talepakis-api.onrender.com"
VARSAYILAN_SITE = "https://talepakis-demo.onrender.com"
# Bu süreden uzun /health yanıtı, API'nin uykudan uyandığı anlamına gelir (Render ücretsiz plan).
SOGUK_BASLANGIC_ESIGI_S = 10.0

HATA = "hata"
UYARI = "uyari"
BILGI = "bilgi"


@dataclass
class Yanit:
    durum: int | None  # HTTP durum kodu; bağlantı kurulamadıysa None
    sure_s: float
    govde: str = ""
    basliklar: dict[str, str] = field(default_factory=dict)
    ag_hatasi: str | None = None

    def json(self) -> dict | None:
        try:
            veri = json.loads(self.govde)
        except ValueError:
            return None
        return veri if isinstance(veri, dict) else None


@dataclass
class Bulgu:
    seviye: str
    konu: str
    mesaj: str


def getir(url: str, zaman_asimi: float) -> Yanit:
    istek = urllib.request.Request(url, headers={"User-Agent": "talepakis-canli-kontrol/1"})
    baslangic = time.monotonic()
    try:
        with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
            govde = yanit.read(512_000).decode("utf-8", "replace")
            basliklar = {k.lower(): v for k, v in yanit.headers.items()}
            return Yanit(yanit.status, time.monotonic() - baslangic, govde, basliklar)
    except urllib.error.HTTPError as hata:
        govde = hata.read(64_000).decode("utf-8", "replace")
        basliklar = {k.lower(): v for k, v in hata.headers.items()}
        return Yanit(hata.code, time.monotonic() - baslangic, govde, basliklar)
    except (urllib.error.URLError, TimeoutError, OSError) as hata:
        neden = getattr(hata, "reason", hata)
        return Yanit(None, time.monotonic() - baslangic, ag_hatasi=str(neden)[:200])


def koken(url: str) -> str:
    parca = urlsplit(url)
    return f"{parca.scheme}://{parca.netloc}"


def degerlendir(api: str, y: dict[str, Yanit]) -> list[Bulgu]:
    """Toplanan yanıtlardan bulgu listesi üretir (ağ erişimi yok; testlerde doğrudan çağrılır)."""
    b: list[Bulgu] = []

    site = y["site"]
    if site.durum != 200:
        b.append(Bulgu(HATA, "site", f"Demo sitesi açılmıyor ({_durum_metni(site)})."))
    else:
        csp = _meta_csp(site.govde)
        if csp is None:
            b.append(Bulgu(UYARI, "site", "Sayfada Content-Security-Policy meta etiketi yok."))
        elif koken(api) not in csp:
            b.append(
                Bulgu(
                    HATA,
                    "site",
                    f"Sitenin CSP connect-src'si API'yi ({koken(api)}) içermiyor: VITE_API_URL "
                    "yanlış derlenmiş olabilir; 'Jev ile dene' API'ye bağlanamaz.",
                )
            )

    for ad in ("experiments", "vocabulary"):
        r = y[ad]
        if r.durum != 200 or r.json() is None:
            b.append(
                Bulgu(
                    HATA,
                    "site",
                    f"demo-data/{ad}.json okunamıyor ({_durum_metni(r)}): "
                    "ölçüm sonuçları sayfası boş kalır.",
                )
            )

    saglik = y["health"]
    veri = saglik.json() or {}
    if saglik.durum != 200 or veri.get("status") != "ok":
        b.append(Bulgu(HATA, "api", f"API /health başarısız ({_durum_metni(saglik)})."))
    else:
        if veri.get("environment") != "production":
            b.append(
                Bulgu(
                    HATA,
                    "api",
                    f"API üretim modunda değil: environment={veri.get('environment')!r}",
                )
            )
        if saglik.sure_s > SOGUK_BASLANGIC_ESIGI_S:
            b.append(
                Bulgu(
                    BILGI,
                    "api",
                    f"API uykudaydı; ilk yanıt {saglik.sure_s:.0f} sn sürdü "
                    "(ücretsiz planın beklenen davranışı).",
                )
            )

    durum = y["demo_status"]
    dv = durum.json()
    if durum.durum != 200 or dv is None:
        b.append(Bulgu(HATA, "demo", f"/demo/status okunamıyor ({_durum_metni(durum)})."))
    else:
        if not dv.get("database_ready"):
            b.append(Bulgu(HATA, "veritabani", "API veritabanına (Neon) bağlanamıyor."))
        if not dv.get("enabled"):
            neden = dv.get("reason") or "bilinmiyor"
            b.append(
                Bulgu(
                    UYARI,
                    "jev",
                    f"Jev demosu kapalı (reason={neden}). Bütçe tanımı ve Render ortam "
                    "değişkenleri kullanıcı adımıdır: docs/DEPLOY.md 3-4.",
                )
            )
        if dv.get("is_mock"):
            mesaj = "Canlı demo mock sağlayıcı bildiriyor; gerçek gibi gösterilmemeli."
            b.append(Bulgu(HATA, "jev", mesaj))

    docs = y["docs"]
    if docs.durum not in (404, None):
        b.append(Bulgu(HATA, "guvenlik", f"Üretimde /docs kapalı olmalı, durum {docs.durum}."))

    if saglik.durum == 200:
        eksik = [
            ad
            for ad in ("strict-transport-security", "x-content-type-options")
            if ad not in saglik.basliklar
        ]
        if eksik:
            mesaj = f"API yanıtında eksik güvenlik başlığı: {', '.join(eksik)}."
            b.append(Bulgu(UYARI, "guvenlik", mesaj))

    return b


def _durum_metni(r: Yanit) -> str:
    if r.durum is None:
        return f"bağlantı yok: {r.ag_hatasi}"
    return f"HTTP {r.durum}, {r.sure_s:.1f} sn"


def _meta_csp(html: str) -> str | None:
    isaret = 'http-equiv="Content-Security-Policy"'
    i = html.find(isaret)
    if i < 0:
        return None
    j = html.find('content="', i)
    if j < 0:
        return None
    j += len('content="')
    k = html.find('"', j)
    return html[j:k] if k > j else None


def topla(api: str, site: str) -> dict[str, Yanit]:
    api, site = api.rstrip("/"), site.rstrip("/")
    return {
        "site": getir(f"{site}/", 30),
        "experiments": getir(f"{site}/demo-data/experiments.json", 30),
        "vocabulary": getir(f"{site}/demo-data/vocabulary.json", 30),
        # Render ücretsiz plan uyanması "yaklaşık 1 dk"; payla bekle.
        "health": getir(f"{api}/health", 150),
        "demo_status": getir(f"{api}/demo/status", 60),
        "docs": getir(f"{api}/docs", 30),
    }


def rapor(api: str, site: str, y: dict[str, Yanit], bulgular: list[Bulgu]) -> str:
    satirlar = [
        f"TalepAkış canlı kontrol — {time.strftime('%Y-%m-%d %H:%M')}",
        f"API: {api}",
        f"Site: {site}",
    ]
    for ad, r in y.items():
        satirlar.append(f"  {ad:12} {_durum_metni(r)}")
    hatalar = [x for x in bulgular if x.seviye == HATA]
    sonuc = "SORUN VAR" if hatalar else "AYAKTA"
    satirlar.append(f"Sonuç: {sonuc}")
    for x in bulgular:
        satirlar.append(f"  [{x.seviye}] {x.konu}: {x.mesaj}")
    return "\n".join(satirlar)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api", default=VARSAYILAN_API)
    ap.add_argument("--site", default=VARSAYILAN_SITE)
    ap.add_argument("--json", action="store_true", help="JSON çıktı")
    ap.add_argument(
        "--cron",
        action="store_true",
        help="Hata/uyarı yoksa sessiz kal; çıkış kodu hep 0 (Hermes no-agent cron için)",
    )
    a = ap.parse_args(argv)
    # Windows'ta boru çıktısı yerel kod sayfasına düşer; Hermes çıktıyı UTF-8 okur.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    y = topla(a.api, a.site)
    bulgular = degerlendir(a.api, y)
    hata_var = any(x.seviye == HATA for x in bulgular)

    if a.json:
        print(
            json.dumps(
                {
                    "ayakta": not hata_var,
                    "yanitlar": {
                        k: {"durum": v.durum, "sure_s": round(v.sure_s, 2)} for k, v in y.items()
                    },
                    "bulgular": [asdict(x) for x in bulgular],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif a.cron:
        if any(x.seviye in (HATA, UYARI) for x in bulgular):
            print(rapor(a.api, a.site, y, bulgular))
        return 0
    else:
        print(rapor(a.api, a.site, y, bulgular))
    return 1 if hata_var else 0


if __name__ == "__main__":
    sys.exit(main())
