# Durum

Son güncelleme: 2026-10-01. Aşama: **0 tamamlandı**, sıradaki **Aşama 1**.

## Çalışan

- `services/api`: FastAPI iskeleti, `GET /health` (sürüm ve ortam bilgisi döner), TALEPAKIS_ önekli ayarlar (`pydantic-settings`).
- `docker-compose.yml`: yerel PostgreSQL 17 (yalnızca `127.0.0.1:5432`).
- Kalıcı kurallar `AGENTS.md` içinde; `CLAUDE.md` buraya yönlendirir.

## Doğrulananlar (2026-10-01)

- `pytest`: 4 test geçti (Python 3.12.7, pytest 9.1.1).
- `ruff check` ve `ruff format --check`: temiz.
- Gerçek uvicorn sunucusu başlatıldı; `GET /health` 200 ve beklenen JSON döndü; süreç kapatıldı.
- `docker compose config` geçerli; `docker compose up -d db` ile PostgreSQL 17.11 kapsayıcısı `healthy` oldu ve `select version()` yanıtladı; ardından `docker compose down` ile kapatıldı (`pgdata` birimi duruyor).

## Henüz yok / ölçülmedi

- Veritabanı modelleri, migration'lar, kimlik doğrulama, talepler, roller: Aşama 1.
- Mobil uygulama ve yönetici paneli: Aşama 1.
- Karar motoru, Jev/LLM adaptörleri, benchmark: Aşama 2–4. Hiçbir model ölçümü yapılmadı; ücretli çağrılar kapalı.
- API ile PostgreSQL arasındaki bağlantı henüz denenmedi (`psycopg` sürücüsü Aşama 1'de eklenecek).

## Sınırlamalar ve açık konular

- Testlerde Starlette `httpx` kullanımından kalkma uyarısı veriyor (bkz. DECISIONS D7). `httpx2` kullanıcı onayını bekliyor; şimdilik `httpx` kilitli.
- Bağımlılık kilidi Windows'ta üretildi; deploy aşamasında hedef platformda yeniden üretilmeli (DECISIONS D4).
- `git push` ve remote yapılmadı; depo yalnızca yerel.

## Sıradaki somut adım

Aşama 1'e başla: SQLAlchemy + Alembic + `psycopg` ekle; `users`, `teams`, `team_memberships`, `tickets`, `ticket_events` tablolarını ve rol bazlı durum geçiş tablosunu tasarla; kimlik doğrulama (argon2 parola özeti + imzalı oturum belirteci); talep açma/listeleme/ayrıntı uç noktaları ve yetkisiz erişim testleri. Mobil iskeleti kurmadan önce Expo SDK ve Node uyumunu resmî belgeden doğrula.
