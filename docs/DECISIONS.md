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

## D8 — Veritabanı adresinde `127.0.0.1` (2026-10-01)

Windows'ta `localhost` önce IPv6 (`::1`) adresine gider; Docker portu yalnızca IPv4'te dinlediği için her bağlantı ~8 sn zaman aşımına uğrar (ölçüldü: `localhost` 8,05 sn, `127.0.0.1` 0,03 sn). Varsayılan adres, `.env.example` ve belgeler `127.0.0.1` kullanır.

## D9 — Senkron SQLAlchemy, açık commit (2026-10-01)

Asenkron motor yerine senkron `Session` + `def` uç noktaları: bu ölçekte darboğaz DB değil model çağrısıdır ve kod çok daha sade kalır. Commit, servis fonksiyonlarında açıkça yapılır (bağımlılık çıkış kodunda değil); böylece yanıt ve işlem sınırı net olur. Uç noktalar yanıtı oturum açıkken Pydantic nesnesine çevirir.

## D10 — Kimlik doğrulama (2026-10-01)

Argon2id (argon2-cffi) parola özeti; HS256 imzalı, 8 saatlik erişim belirteci (PyJWT), yenileme belirteci yok. Belirteç yalnızca kullanıcı kimliği taşır; rol ve `is_active` her istekte veritabanından okunur, böylece yetki değişikliği veya hesap kapatma hemen etki eder (belirteç kara listesi gerekmez). Olmayan kullanıcıda da parola maliyeti ödenir ve hata mesajı aynıdır (kullanıcı adı sızmaz). Bilinçli eksik: giriş hız sınırı (Aşama 5). Mobilde belirteç Expo SecureStore'da saklanacak.

## D11 — Geçiş kuralları "sıfat" tabanlı (2026-10-01)

İzinler rolden çok bağlamdan doğar: aynı kişi bir talepte SAHİP (OWNER), bir başkasında EKİP GÖREVLİSİ (TECHNICIAN), yönetici ise ADMIN sıfatındadır. Böylece kendi talebini açan bir görevli, o talepte sahip gibi davranır. Tablo (`domain/workflow.py`) saf Python'dur; HTTP ve DB'den bağımsız test edilir. Atama (Yeni/İnceleme → Atandı) ekip bilgisi gerektirdiği için genel geçiş tablosunda değil, ayrı "atama" işlemindedir. Görünürlük kuralının SQL karşılığı ile saf kural arasındaki tutarlılık testle sabitlenmiştir.

## D12 — Enum'lar metin + CHECK, ekipler migration ile (2026-10-01)

Roller/durumlar/kategoriler PostgreSQL ENUM tipi yerine `VARCHAR` + açık `CHECK` kısıtıdır (değer eklemek ENUM tipinden daha kolay). SQLAlchemy'nin kendi enum kısıtı Alembic'te her kısıtı iki kez ürettiği için kapatıldı; kısıtlar modelde açıkça tanımlı. Ekipler sözlüğün parçası olduğu için ilk migration ile eklenir (her ortamda vardır); testler bu tabloları boşaltmaz.

## D13 — Görünmeyen talep 404 döner (2026-10-01)

Yetkisiz bir kullanıcı, başkasının talep kimliğini bilse bile "var ama yasak" (403) değil "yok" (404) görür; varlık sızdırılmaz. Kimlikler UUID'dir. Yönetici uçları (atama, düzeltme) ise rol bağımlılığı sebebiyle herkese 403 verir ve talebin varlığı hakkında bilgi içermez. Yetki kontrolü hem uç noktada hem serviste vardır (çift kilit; ikisi de testle sınandı).

## D14 — Testler gerçek PostgreSQL'de, her oturumda sıfırdan (2026-10-01)

Test veritabanı `talepakis_test` her oturumda silinip yeniden kurulur ve migration'lar uygulanır; bu hem şemayı hem migration'ları sınar. Ad sabittir, geliştirme veritabanına dokunulmaz. Satır kilidi (`SELECT ... FOR UPDATE`) PostgreSQL'e özgü olduğu için SQLite ile sınanamazdı. Mutasyon denemesiyle (kasıtlı hata sokma) testlerin kilidi, görünürlüğü, imza doğrulamasını ve yetki kontrollerini gerçekten yakaladığı doğrulandı.

## Açık karar — D7: `httpx` ve `httpx2`

Starlette'in test istemcisi `httpx`'i artık kullanımdan kalkmış sayıyor ve `httpx2` öneriyor (Starlette kaynağı önce `httpx2`'yi içe aktarıyor; PyPI'da paket Pydantic gözetiminde, sürüm 2.13.1). Şimdilik `httpx==0.28.1` kilitli; testler geçiyor, yalnızca bir kullanımdan kalkma uyarısı görünüyor. `httpx2`'ye geçiş kullanıcı onayına bırakıldı: `requirements-dev.in` içinde `httpx` → `httpx2` ve `pip-compile` yeterli.
