# Mimari kararlar

Kısa gerekçeli kayıtlar. Yalnızca sonradan "neden böyle yaptık?" sorusu çıkabilecek kararlar yazılır.

## D1 — Monorepo, küçük yığın (2026-10-01)

`apps/mobile`, `apps/admin`, `services/api`, `evaluation`, `docs` tek depoda. Boş projeden başlandığı için önerilen yığın uygulandı: React Native + Expo + TypeScript, FastAPI + SQLAlchemy + Alembic, PostgreSQL. Ortak bir paket veya ek servis yok; karar sözleşmesi ve sağlayıcı adaptörleri API içinde yaşar.

## D2 — API için Python 3.12 (2026-10-01)

Makinede 3.12 ve 3.14 var. 3.12 seçildi: yaygın deploy platformlarında varsayılan, bağımlılıkların derlenmiş paketleri (pydantic-core, psycopg vb.) olgun. Sanal ortam `services/api/.venv` içinde; global kurulum yok.

## D3 — Ajan talimatları: tek kaynak `AGENTS.md` (2026-10-01)

Kurallar `AGENTS.md` içinde; `CLAUDE.md` yalnızca `@AGENTS.md` içe aktarır. Claude Code belgesinde Windows için önerilen yol budur (symlink Windows'ta yönetici/Developer Mode ister ve Git'te düz metne dönebilir). İçe aktarma AGENTS.md'nin iki kez okunmasına yol açmaz.

## D4 — Bağımlılık kilidi: pip-tools (2026-10-01)

`requirements.in` / `requirements-dev.in` elle yazılır, `pip-compile` ile `requirements.txt` / `requirements-dev.txt` üretilir; ikisi de commitlenir. Neden pip-tools: ek global araç gerektirmez (venv içine kurulur), çıktı düz `pip install -r` ile çalışır. Not: kilit Windows'ta üretildi; platforma özgü paketler (ör. Linux'ta `uvloop`) kilitte yoktur, uvicorn onsuz da çalışır. Deploy aşamasında hedef platformda yeniden üretilir.

## D5 — PostgreSQL 17, yalnızca yerel erişim (2026-10-01)

`docker-compose.yml` `postgres:17` kullanır; port yalnızca `127.0.0.1`'e bağlanır, yerel ağa açılmaz. 17 seçildi: desteği uzun, veri dizini düzeni bilinen ve kararlı. Geliştirme parolası compose dosyasında açıktır ve yalnızca bu yerel kapsayıcı içindir.

## D6 — Testler ortamdan yalıtılır (2026-10-01)

`tests/conftest.py` her testte `TALEPAKIS_*` değişkenlerini temizler ve ayarları `.env` okumadan kurar; böylece geliştiricinin kendi yapılandırması sonucu değiştirmez.

## Açık karar — D7: `httpx` ve `httpx2`

Starlette'in test istemcisi `httpx`'i artık kullanımdan kalkmış sayıyor ve `httpx2` öneriyor (Starlette kaynağı önce `httpx2`'yi içe aktarıyor; PyPI'da paket Pydantic gözetiminde, sürüm 2.13.1). Şimdilik `httpx==0.28.1` kilitli; testler geçiyor, yalnızca bir kullanımdan kalkma uyarısı görünüyor. `httpx2`'ye geçiş kullanıcı onayına bırakıldı: `requirements-dev.in` içinde `httpx` → `httpx2` ve `pip-compile` yeterli.
