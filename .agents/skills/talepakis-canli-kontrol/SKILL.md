---
name: talepakis-canli-kontrol
description: TalepAkış canlı demosunu kontrol et, uyandır, teşhis et
version: 1.0.0
metadata:
  hermes:
    tags: [talepakis, render, neon, saglik, izleme]
    category: devops
    requires_toolsets: [terminal]
---

# TalepAkış canlı kontrol ve ayağa kaldırma

Canlı sistem: statik demo sitesi `https://talepakis-demo.onrender.com` (Render Static, uyumaz) →
API `https://talepakis-api.onrender.com` (Render Web ücretsiz, 15 dk boşta uyur) → Neon PostgreSQL
(5 dk boşta uyur) → Jev (yalnızca `jev_only`). Ayrıntı: `docs/DEPLOY.md`, karar: `docs/DECISIONS.md`
D35/D36.

## When to Use
- "Canlı çalışıyor mu?", "siteyi ayağa kaldır", "demo açılmıyor", "yayından sonra doğrula".
- `talepakis-yayin` skill'inin son adımı olarak.
- Zamanlanmış izleme raporunda sorun göründüğünde.

## Procedure
1. Depo kökünden kontrolü çalıştır (yalnızca okur, model çağrısı yapmaz):
   `services\api\.venv\Scripts\python.exe .agents\skills\talepakis-canli-kontrol\scripts\canli_kontrol.py`
   (makine için `--json`). Çıkış kodu 1 = en az bir `hata`.
2. "Ayağa kaldırmak" = API'yi uyandırmak: betik `/health`'i 150 sn'ye kadar bekler; uykudan uyanma
   ~60 sn sürer ve `[bilgi]` olarak raporlanır, hata değildir. Bir kez yeterli; tekrar tekrar çağırma.
3. Bulguyu aşağıdaki tabloya göre yorumla, kullanıcıya kısa rapor ver: ne ayakta, ne değil, neden,
   kimin adımı.

| Bulgu | Olası neden | Ne yapılır |
|---|---|---|
| `site` açılmıyor | Statik sitenin derlemesi başarısız / servis askıda | Kullanıcı Render → `talepakis-demo` → Events/Logs'a bakar; yerelde `apps/admin`'de `VITE_APP_MODE=demo npm run build` ile hatayı yeniden üret, düzelt, `talepakis-yayin` |
| CSP API'yi içermiyor | `VITE_API_URL` yanlış/boş derlenmiş | Kullanıcı Render'da statik sitenin `VITE_API_URL` değerini düzeltip Manual Deploy yapar |
| `demo-data/*.json` yok | `apps/admin/public/demo-data` eksik/bozuk | Depoda dosyaları kontrol et; gerekirse `python -m app.manage export-demo-data` (yerel, model çağrısı yok) |
| `api` /health başarısız | Açılışta migration hatası, ortam değişkeni doğrulaması, aylık 750 saat kotası | Kullanıcıdan Render → `talepakis-api` → Logs'un son 50 satırını iste (gizli değer içerirse maskelesin); `config.py` doğrulama mesajlarıyla eşleştir |
| `veritabani` hazır değil | Neon adresi/parolası, `?sslmode=require` eksik, Neon kotası | Kullanıcı Neon panelinde projeyi ve kotayı kontrol eder; adresler yalnızca Render panelinde |
| `jev` kapalı, `not_configured` | Bütçe tanımlı değil, anahtar yok veya `TALEPAKIS_PAID_MODEL_CALLS_ENABLED=false` | Kullanıcı adımı: `docs/DEPLOY.md` 3 (bütçe tutarını kullanıcı onaylar) ve 4 |
| `jev` mock bildiriyor | Yanlış sağlayıcı ayarı | Hata: canlıda mock gerçek gibi gösterilemez; `TALEPAKIS_DEMO_PROVIDER=jev` |
| `/docs` açık | Üretim modu kapalı | `TALEPAKIS_ENVIRONMENT=production` olmalı |

## Pitfalls
- **Uyanık tutmak için zamanlanmış ping kurma.** D35/D36: ücretsiz kotayı tüketir ve istenmedi. İzleme
  günde birkaç kez yeterli.
- Ücretli çağrı başlatma: `POST /demo/decisions` gerçek Jev çağrısıdır ve bütçeden düşer. Kontrolde
  yalnızca `GET` kullan; demo kararını kullanıcı açıkça isterse ve bütçe tanımlıysa dene.
- Gizli değerleri (Neon adresi, Jev anahtarı, Render deploy hook) sohbete, depoya, günlüğe yazma ve
  isteme; kullanıcı bunları yalnızca Render/Neon panelinde girer.
- Render panelinde ayar değiştirme, yayınlama veya servisi yeniden başlatma kullanıcının işidir; senin
  rolün teşhis ve kod düzeltmesidir.
- Demo sitesi `HashRouter` kullanır: `/#/sonuclar` doğrudur, `/sonuclar` 404 vermesi hata değildir.

## Verification
- Betik "Sonuç: AYAKTA" yazıyor ve çıkış kodu 0.
- Jev açıldıysa `[uyari] jev` satırı yok.
- Raporunda her sorunun sahibi (sen / kullanıcı) ve sıradaki adım yazılı.

## Zamanlanmış izleme (kurulu ise)
Hermes no-agent cron işi `talepakis-canli-izleme`, betiğin `--cron` kipini günde iki kez çalıştırır
(LLM yok, ücret yok); sorun yoksa sessizdir, rapor `%LOCALAPPDATA%\hermes\cron\output` altına düşer.
Hermes cron betikleri yalnızca kendi `scripts/` klasöründen çalıştırır; depodaki betik değişince iki
dosyayı yeniden kopyala:
`Copy-Item .agents\skills\talepakis-canli-kontrol\scripts\canli_kontrol.py, .agents\skills\talepakis-canli-kontrol\scripts\cron_izleme.py "$env:LOCALAPPDATA\hermes\scripts\"`
Kurulum (bir kez): `hermes cron create "0 9,21 * * *" --no-agent --script cron_izleme.py --deliver local --name talepakis-canli-izleme`.
Durum: `hermes cron list`; elle tetikleme: `hermes cron run <id>`.
