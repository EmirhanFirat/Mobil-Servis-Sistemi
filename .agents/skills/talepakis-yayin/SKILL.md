---
name: talepakis-yayin
description: TalepAkış değişikliğini doğrula, gönder, yayına hazırla
version: 1.0.0
metadata:
  hermes:
    tags: [talepakis, git, render, yayin]
    category: devops
    requires_toolsets: [terminal]
---

# TalepAkış yayın akışı

Render'da otomatik yayın kapalı (`render.yaml`: `autoDeployTrigger: off`). **Yayını kullanıcı yapar**
(Render paneli → servis → Manual Deploy). Senin işin: kontrolleri geçen commit'i `origin/main`'e
göndermek, kullanıcıya hangi servisin yayınlanacağını söylemek ve yayından sonra doğrulamak.

## When to Use
- Bir düzeltme bitti ve canlıya çıkması gerekiyor.
- Kullanıcı "yayına al", "canlıya gönder" dediğinde.

## Procedure
1. Değişen alanı belirle (`git status`, `git diff`) ve yalnızca ilgili kontrolleri çalıştır:
   - `services/api`: `.venv\Scripts\python.exe -m pytest`, `-m ruff check .`, `-m ruff format --check .`
     (DB'li testler için önce `docker info`, sonra `docker compose up -d db`; Docker kapalıysa bunu
     açıkça yaz).
   - `apps/admin`: `talepakis-arayuz` 6. adımdaki komutlar.
   - `apps/mobile`: `npm run typecheck`, `npx expo lint`, `npm test`.
2. Kökteki `AGENTS.md` git kurallarıyla commit at: yalnızca bu işin dosyalarını stage et, mesaj sade
   Türkçe, `git commit --file <geçici dosya>`, ortak yazar/atıf satırı yok. Gerekirse `docs/STATUS.md`
   aynı commit'e girer.
3. `git fetch origin`; `git merge-base --is-ancestor origin/main main` başarılı değilse **dur ve
   bildir**. Başarılıysa `git push origin main`. Force push yok.
4. Kullanıcıya yayın talimatı ver:
   - API değiştiyse: Render → `talepakis-api` → Manual Deploy → "Deploy latest commit".
   - Arayüz değiştiyse: Render → `talepakis-demo` → Manual Deploy.
   - Yeni ortam değişkeni gerekiyorsa adını ve nereye girileceğini yaz; değerini isteme.
5. Kullanıcı "yayınlandı" deyince `talepakis-canli-kontrol` çalıştır; arayüz değişikliğini tarayıcıda
   canlıda gör.
6. Kısa rapor: ne değişti, hangi kontroller geçti, commit kısa SHA + başlık, yayın durumu, kalan iş.

## Pitfalls
- Kırık kontrolle commit veya push yapma; atlanan kontrolü gizleme.
- Migration eklendiyse: API açılışta `alembic upgrade head` çalıştırır, başarısızsa servis açılmaz.
  Migration yalnızca ekleme yapmalı; yıkıcı migration'ı kullanıcıya sormadan yazma.
- Ücretli model çağrısı açan ayarı (`TALEPAKIS_PAID_MODEL_CALLS_ENABLED`) kendiliğinden önerip
  açtırma; bütçe tutarı kullanıcı onayıdır (`docs/DEPLOY.md` 3-4).
- Render deploy hook veya API anahtarı isteme/saklama; bu projede yayın kararı kullanıcıda (D36).

## Verification
- `git status` temiz, `git log origin/main -1` senin commit'in.
- Yayından sonra canlı kontrol "AYAKTA".
