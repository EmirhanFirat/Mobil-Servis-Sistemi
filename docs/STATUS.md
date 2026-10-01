# Durum

Son güncelleme: 2026-10-01. Aşama: **0 tamamlandı; Aşama 1'in API kısmı tamamlandı**, mobil ve yönetici paneli sırada.

## Çalışan

- `services/api`: giriş (Argon2 + imzalı token), üç rol (talep sahibi, teknik görevli, yönetici), talep açma/listeleme/ayrıntı, ekip kuyruğu, rol ve bağlama göre durum geçişleri, olay geçmişi, yönetici atama/düzeltme, kullanıcı ve ekip üyeliği yönetimi, sözlük ucu, `/health` ve `/health/ready`.
- PostgreSQL 17 (Docker), Alembic migration'ı (`0001`), dev seed'i (`python -m app.seed`: 8 kullanıcı, 4 örnek talep).
- Kalıcı kurallar `AGENTS.md` içinde; uzak depo GitHub `origin`.

## Doğrulananlar (2026-10-01)

- `pytest`: **145 test geçti** (gerçek PostgreSQL üzerinde; migration, erişim kontrolü, akış, yönetici işlemleri, seed). `ruff check` ve `ruff format --check` temiz.
- Mutasyon denemesi: satır kilidini kaldırma, görünürlük süzgecini açma, JWT imza doğrulamasını kapatma, pasif hesabı kabul etme, işi üstlenmeyen görevlinin çözmesi, servis katmanında yetki kontrolünü kaldırma gibi 10 kasıtlı hata testlerce yakalandı (zamanlama korumasının kaldırılması bir casus testiyle yakalanıyor).
- Gerçek uvicorn sunucusu üzerinden uçtan uca akış (giriş → talep → atama → görevli kuyruğu → çözme → kapatma), başkasının talebinde 404, CORS yalnızca yönetici paneli adresine izinli.

## Henüz yok / ölçülmedi

- Mobil uygulama ve yönetici paneli (Aşama 1'in kalanı).
- Karar motoru (kategori/öncelik önerisi), `decisions` ve `model_calls` tabloları, Jev/LLM adaptörleri, benchmark: Aşama 2–4. Hiçbir model ölçümü yapılmadı; ücretli çağrılar kapalı. Şu an kategori/öncelik/ekibi yalnızca yönetici elle belirler.
- Yük/performans ölçümü yapılmadı.

## Sınırlamalar ve açık konular

- Giriş denemelerine hız sınırı/hesap kilidi yok (Aşama 5). Yenileme belirteci yok; token 8 saat geçerli.
- Testlerde Starlette `httpx` kullanımından kalkma uyarısı veriyor (bkz. DECISIONS D7). `httpx2` kullanıcı onayını bekliyor; şimdilik `httpx` kilitli.
- Bağımlılık kilidi Windows'ta üretildi; deploy aşamasında hedef platformda yeniden üretilmeli (DECISIONS D4).
- Commit e-postası `emirhanfirat44@gmail.com`; GitHub hesabında doğrulanmış değilse commitler profile bağlanmaz.

## Sıradaki somut adım

Mobil uygulama (`apps/mobile`): Expo SDK ve Node uyumunu resmî belgeden doğrula; giriş, taleplerim, yeni talep, talep ayrıntısı + geçmiş ve görevli iş listesi ekranları; yükleniyor/boş/bağlantı hatası/yetkisiz durumları; belirteci SecureStore'da sakla. Ardından yönetici paneli (`apps/admin`).
