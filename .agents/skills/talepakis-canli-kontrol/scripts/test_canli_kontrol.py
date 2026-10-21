"""canli_kontrol.degerlendir için ağsız testler.

Çalıştırma (`services/api` sanal ortamıyla, depo kökünden):
    python -m pytest .agents/skills/talepakis-canli-kontrol/scripts -q
"""

import json

import canli_kontrol as ck

API = "https://talepakis-api.onrender.com"
CSP = (
    '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; '
    f"connect-src 'self' {API}; base-uri 'none'\" />"
)


def saglikli(**degisen: ck.Yanit) -> dict[str, ck.Yanit]:
    y = {
        "site": ck.Yanit(200, 0.3, f"<html><head>{CSP}</head></html>"),
        "experiments": ck.Yanit(200, 0.2, json.dumps({"runs": []})),
        "vocabulary": ck.Yanit(200, 0.2, json.dumps({"categories": []})),
        "health": ck.Yanit(
            200,
            0.5,
            json.dumps({"status": "ok", "environment": "production"}),
            {"strict-transport-security": "max-age=1", "x-content-type-options": "nosniff"},
        ),
        "demo_status": ck.Yanit(
            200, 1.0, json.dumps({"database_ready": True, "enabled": True, "is_mock": False})
        ),
        "docs": ck.Yanit(404, 0.1, "{}"),
    }
    y.update(degisen)
    return y


def seviyeler(bulgular: list[ck.Bulgu]) -> list[tuple[str, str]]:
    return [(b.seviye, b.konu) for b in bulgular]


def test_her_sey_yolundaysa_bulgu_yok():
    assert ck.degerlendir(API, saglikli()) == []


def test_api_ulasilamazsa_hata():
    y = saglikli(health=ck.Yanit(None, 150.0, ag_hatasi="timed out"))
    assert (ck.HATA, "api") in seviyeler(ck.degerlendir(API, y))


def test_soguk_baslangic_yalnizca_bilgi():
    y = saglikli()
    y["health"].sure_s = 62.0
    assert seviyeler(ck.degerlendir(API, y)) == [(ck.BILGI, "api")]


def test_jev_kapali_uyari_ve_nedeni_yazilir():
    durum = json.dumps({"database_ready": True, "enabled": False, "reason": "not_configured"})
    bulgular = ck.degerlendir(API, saglikli(demo_status=ck.Yanit(200, 1.0, durum)))
    assert seviyeler(bulgular) == [(ck.UYARI, "jev")]
    assert "not_configured" in bulgular[0].mesaj


def test_veritabani_yoksa_hata():
    durum = json.dumps({"database_ready": False, "enabled": True})
    assert (ck.HATA, "veritabani") in seviyeler(
        ck.degerlendir(API, saglikli(demo_status=ck.Yanit(200, 1.0, durum)))
    )


def test_mock_saglayici_canlida_hata():
    durum = json.dumps({"database_ready": True, "enabled": True, "is_mock": True})
    assert (ck.HATA, "jev") in seviyeler(
        ck.degerlendir(API, saglikli(demo_status=ck.Yanit(200, 1.0, durum)))
    )


def test_csp_baska_apiyi_gosteriyorsa_hata():
    html = CSP.replace(API, "https://baska.onrender.com")
    bulgular = ck.degerlendir(API, saglikli(site=ck.Yanit(200, 0.3, html)))
    assert seviyeler(bulgular) == [(ck.HATA, "site")]


def test_statik_sonuc_dosyasi_bozuksa_hata():
    bulgular = ck.degerlendir(API, saglikli(experiments=ck.Yanit(200, 0.2, "<html>")))
    assert seviyeler(bulgular) == [(ck.HATA, "site")]


def test_docs_aciksa_guvenlik_hatasi():
    bulgular = ck.degerlendir(API, saglikli(docs=ck.Yanit(200, 0.1, "<html>")))
    assert seviyeler(bulgular) == [(ck.HATA, "guvenlik")]


def test_uretim_disi_ortam_hata():
    y = saglikli()
    y["health"].govde = json.dumps({"status": "ok", "environment": "development"})
    assert (ck.HATA, "api") in seviyeler(ck.degerlendir(API, y))


def test_cron_modu_sorunsuzken_sessiz(monkeypatch, capsys):
    monkeypatch.setattr(ck, "topla", lambda api, site: saglikli())
    assert ck.main(["--cron"]) == 0
    assert capsys.readouterr().out == ""


def test_cron_modu_hatada_rapor_yazar_ama_sifir_doner(monkeypatch, capsys):
    monkeypatch.setattr(ck, "topla", lambda api, site: saglikli(health=ck.Yanit(503, 1.0, "{}")))
    assert ck.main(["--cron"]) == 0
    assert "SORUN VAR" in capsys.readouterr().out


def test_normal_mod_hatada_bir_doner(monkeypatch, capsys):
    monkeypatch.setattr(ck, "topla", lambda api, site: saglikli(health=ck.Yanit(503, 1.0, "{}")))
    assert ck.main([]) == 1
