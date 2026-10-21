---
name: talepakis-arayuz
description: TalepAkış web arayüzünü (demo ve panel) incele ve düzelt
version: 1.0.0
metadata:
  hermes:
    tags: [talepakis, react, vite, frontend, arayuz]
    category: software-development
    requires_toolsets: [terminal]
---

# TalepAkış arayüz düzeltme

`apps/admin` tek kod tabanından iki paket üretir (`src/main.tsx`):
- **Demo** (`VITE_APP_MODE=demo`): herkese açık site, `HashRouter`, `src/demo/*`; yönetici kodu pakete
  girmez. Canlıda yayında olan budur.
- **Yönetici paneli** (kip verilmezse): `BrowserRouter`, `src/App.tsx`, `src/pages/*`; şu an canlıda yok.
Ortak parçalar: `src/components/*` (`ui.tsx` temel bileşenler), `src/lib/*` (API istemcisi, tipler,
biçimlendirme), tek stil dosyası `src/index.css`. Mobil uygulama (`apps/mobile`) ayrı; ona dokunmadan
önce `apps/mobile/AGENTS.md`.

## When to Use
- "Arayüzü düzelt", "mobilde bozuk görünüyor", "demo sayfası karışık", "panelde şu ekran".
- `docs/PLAN.md` Aşama 6 arayüz maddeleri.

## Procedure
1. Kökteki `AGENTS.md` kurallarını uygula (Türkçe, yeni ürün özelliğini kendiliğinden ekleme, commit
   biçimi). İşe `docs/PLAN.md` Aşama 6'daki açık maddeden başla.
2. **Önce gör, sonra değiştir.** Canlı demoyu (`https://talepakis-demo.onrender.com`) tarayıcı aracınla
   375 px ve 1280 px genişlikte aç; ana sayfa, `/#/sonuclar`, uyanma paneli, sonuç paneli. Somut
   sorunları (taşma, hizalama, okunmayan metin, karanlık tema, boş/hata durumları) dosya:satır ile
   listele ve kullanıcıya kısa liste olarak göster. Belirsiz zevk kararlarını (renk paleti, yeniden
   tasarım) kullanıcıya sor; açık kusurları düzelt.
3. Yerelde çalıştır (`apps/admin`):
   - Demo: `$env:VITE_APP_MODE="demo"; npm run dev` → http://localhost:5173. Statik sonuçlar API'siz
     açılır. "Jev ile dene" için yerel API gerekir (`services/api`, `docker compose up -d db`); canlı
     API'nin CORS listesi yalnızca canlı siteyi kabul eder.
   - Panel: `npm run dev` (kip yok) + yerel API ve seed (`python -m app.seed`).
4. Değişikliği küçük ve odaklı yap. Mevcut sınıf adı ve CSS değişkeni düzenini (`index.css`) sürdür;
   yeni UI kütüphanesi ekleme. Metinler Türkçe.
5. API sözleşmesi değişirse (`services/api/app/schemas.py`) panel ve mobil tipleri
   (`apps/admin/src/lib/types.ts`, `apps/mobile/src/lib/types.ts`) ve testleri birlikte güncelle.
6. Kontroller (`apps/admin`), hepsi geçmeli:
   `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`, ayrıca demo paketi:
   `$env:VITE_APP_MODE="demo"; $env:VITE_API_URL="https://talepakis-api.onrender.com"; npm run build`
   ve `dist` içinde yönetici ekranı izinin olmadığını kontrol et (ör. `Select-String -Path dist\assets\*.js -Pattern "kullanicilar"` boş dönmeli).
7. Düzeltilen ekranı yerelde aynı genişliklerde yeniden gör; önce/sonra farkını raporla.
8. Commit + push ve yayın için `talepakis-yayin` skill'ine geç.

## Pitfalls
- `tsconfig` `erasableSyntaxOnly` açık: sınıfta `constructor(readonly x)` yazma.
- Demo sayfası CSP ile korunur (`csp.ts`): dış yazı tipi, CDN betiği veya başka alan adına istek
  eklersen canlıda engellenir. Her şeyi yerel paketle.
- Demo kipinde yönetici koduna (`App.tsx`, `pages/*`, `lib/auth*`) içe aktarma ekleme; paket ayrımı
  bozulur.
- Uyanma akışı (`use-wake-up.ts`, `WakePanel.tsx`) ücretsiz `GET /demo/status` dışında istek atmamalı;
  sayfa açılışında Jev çağrısı (`POST /demo/decisions`) asla otomatik gitmemeli.
- Mock sonuç gerçek model sonucu gibi gösterilmez; rozet ve uyarılar korunur.
- `npm audit fix --force` çalıştırma.

## Verification
- Altıncı adımdaki tüm komutlar temiz; test sayısı düşmedi.
- 375 px ve 1280 px'te yatay kaydırma yok; açık/koyu temada metin okunuyor.
- Yayından sonra `talepakis-canli-kontrol` "AYAKTA" diyor ve canlıda değişiklik görünüyor.
