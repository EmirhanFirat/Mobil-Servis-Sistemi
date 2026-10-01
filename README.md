# TalepAkış

Kampüs veya yurt bakım ekipleri için mobil servis talebi ve iş yönlendirme uygulaması. Kullanıcı metinle talep açar; sistem kategori, öncelik ve eksik bilgiyi önerir ve talebi ilgili ekip kuyruğuna yönlendirir.

Projenin araştırma sorusu: **Türkçe servis taleplerinde Jev, ekonomik bir LLM ve hibrit yaklaşım arasında doğruluk, işlem süresi ve maliyet nasıl değişiyor?** Sonuçlar ölçülmeden hiçbir tasarruf veya başarı iddiası yapılmaz.

> **Durum:** Aşama 1 sürüyor. **API ve mobil uygulama tamamlandı:** giriş ve roller, talep açma/listeleme/ayrıntı, ekip kuyruğu, rol bazlı durum geçişleri, olay geçmişi. Yönetici paneli (web) sırada. Karar motoru (kategori/öncelik önerisi) ve model karşılaştırması henüz yok; şu an yönlendirmeyi yönetici yapar. Mobil uygulama tarayıcı önizlemesinde uçtan uca doğrulandı; gerçek telefonda/emülatörde henüz denenmedi. Ayrıntı: [docs/STATUS.md](docs/STATUS.md), [docs/PLAN.md](docs/PLAN.md).

## Yapı

```
services/api   FastAPI sunucusu (Python 3.12, SQLAlchemy, Alembic, PostgreSQL)
apps/mobile    Expo (SDK 57) + React Native + TypeScript
apps/admin     Yönetici paneli, React web         (sırada)
evaluation     Benchmark ve değerlendirme         (Aşama 4)
docs           Plan, durum ve mimari kararlar
```

## Gereksinimler

- Windows 11 + PowerShell (diğer sistemlerde komutlar benzerdir)
- Python 3.12
- Docker Desktop (PostgreSQL için)
- Node.js 24 (mobil ve yönetici paneli geldiğinde)

## API'yi çalıştırma

Komutlar proje kökünden başlar. Klasör adında boşluk olduğu için yolları tırnak içine al.

```powershell
# 1) Veritabanı (Docker Desktop açık olmalı)
docker compose up -d db

# 2) Python ortamı ve bağımlılıklar
cd services\api
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env

# 3) Şema ve demo verisi
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m app.seed

# 4) Sunucu
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Sunucu `http://127.0.0.1:8000` adresinde açılır. Etkileşimli API belgeleri: `http://127.0.0.1:8000/docs` ("Authorize" ile giriş yanıtındaki token'ı gir). Kontrol uçları: `/health` (süreç ayakta mı), `/health/ready` (veritabanı dahil hazır mı).

> Veritabanı adresinde `localhost` yerine `127.0.0.1` kullan. Windows'ta `localhost` önce IPv6'yı dener ve her bağlantıda yaklaşık 8 saniye bekler.

### Demo kullanıcıları (yalnızca geliştirme)

`python -m app.seed` aşağıdaki hesapları ve dört örnek talebi oluşturur; üretim ortamında çalışmayı reddeder. Ortak demo parolası [services/api/app/seed.py](services/api/app/seed.py) içindeki `DEMO_PASSWORD` değeridir ve seed çıktısında da yazılır.

| Kullanıcı adı | Rol | Ekip |
|---|---|---|
| `yonetici` | Yönetici | — |
| `elektrik.usta`, `tesisat.usta`, `bt.destek`, `temizlik.gorevli`, `genel.bakim` | Teknik görevli | kendi ekibi |
| `ayse`, `burak` | Talep sahibi | — |

### API özeti

| Uç nokta | Kim | Ne yapar |
|---|---|---|
| `POST /auth/login`, `GET /auth/me` | herkes | Giriş ve oturumdaki kullanıcı |
| `GET /meta/vocabulary` | herkes | Kodlar ve Türkçe görünen adlar |
| `POST /tickets`, `GET /tickets`, `GET /tickets/{id}` | giriş yapmış | Talep aç; görebildiklerini listele (`scope=mine\|queue`, `status`, sayfalama); ayrıntı ve geçmiş |
| `POST /tickets/{id}/transitions` | rol ve bağlama göre | Durum değiştir (izinli geçişleri ayrıntı yanıtı `allowed_transitions` olarak söyler) |
| `POST /tickets/{id}/assignment`, `PATCH /tickets/{id}` | yönetici | Ekibe/görevliye ata; öncelik, kategori, eksik bilgi düzelt |
| `/admin/users`, `/admin/teams` | yönetici | Kullanıcı ve ekip üyeliği yönetimi |

Görme yetkin olmayan bir talep, olmayan bir talepten ayırt edilemez (`404`).

## Mobil uygulamayı çalıştırma

API çalışıyorken (yukarıdaki 1–4. adımlar):

```powershell
cd apps\mobile
npm install
npx expo start              # QR kodu telefondaki Expo Go ile okut
npx expo start --web        # tarayıcıda önizleme (geliştirme/doğrulama için)
```

**API adresi** şu sırayla bulunur: `EXPO_PUBLIC_API_URL` ortam değişkeni → Expo geliştirme sunucusunun bilgisayar adresi (telefonda Expo Go ile otomatik, bilgisayar ve telefon aynı Wi-Fi'da olmalı) → Android emülatöründe `10.0.2.2` → `127.0.0.1`. Telefonda API'yi `--host 0.0.0.0` ile başlatmayı unutma (aşağıdaki bölüm). `http://` yalnızca geliştirme içindir; yayında `https://` adres ver. Bu değişken uygulama paketine gömülür, gizli bilgi koyma.

Oturum token'ı telefonda cihazın güvenli deposunda (iOS Keychain / Android Keystore, `expo-secure-store`) saklanır. Web önizlemesinde güvenli depo olmadığı için `localStorage` kullanılır; bu yalnızca geliştirme içindir.

Giriş yaptıktan sonra: **Taleplerim** (açtığın talepler), **Yeni talep**, **İş listesi** (yalnızca teknik görevli ve yönetici; ekip kuyruğu ve süzgeçler), **Hesap**. Talep ayrıntısında olay geçmişi ve sunucunun sana izin verdiği işlemler (işleme al, çözüldü, kapat, yeniden aç...) görünür.

## Testler ve lint

Mobil: `cd apps\mobile`, sonra `npm test` (Jest), `npm run typecheck`, `npx expo lint`.

API testleri gerçek PostgreSQL ister: her çalıştırmada ayrı bir `talepakis_test` veritabanı **sıfırdan** kurulur ve migration'lar uygulanır; geliştirme verisine dokunulmaz. Docker kapalıysa testler açık bir mesajla durur.

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

Geliştirme veritabanını sıfırlamak için: `docker compose down -v`, sonra yukarıdaki 1–3. adımlar.

## Telefondan API'ye erişim (localhost ve bilgisayarın IP'si)

Telefondaki uygulamada `localhost` veya `127.0.0.1`, **telefonun kendisi** demektir; bilgisayardaki API'ye ulaşmaz. Telefondan erişmek için:

1. Bilgisayar ve telefon aynı Wi-Fi ağında olsun.
2. Bilgisayarın yerel IP'sini bul: `ipconfig` çıktısında Wi-Fi bağdaştırıcısındaki "IPv4 Address" (genelde `192.168.x.x` veya `10.x.x.x`).
3. API'yi tüm ağ arayüzlerinde dinleyecek şekilde başlat (`services\api` içinde): `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --reload`.
4. Telefonda API adresi olarak `http://<bilgisayar-IP'si>:8000` kullan. Windows Güvenlik Duvarı ilk seferde izin sorabilir; yalnızca özel (ev/ofis) ağlar için izin ver.

`--host 0.0.0.0` sunucuyu o ağdaki herkese açar; ortak veya halka açık Wi-Fi'da kullanma. Emülatör kullanıyorsan adres farklıdır (ör. Android emülatöründe bilgisayar `10.0.2.2` olarak görünür).

## Güvenlik notları

- Yetkilendirme sunucuda uygulanır; istemci yalnızca gösterir. Rol ve hesap durumu her istekte veritabanından okunur, token'daki bilgiye güvenilmez.
- Parolalar Argon2 ile özetlenir; oturum token'ı HS256 imzalıdır ve `TALEPAKIS_SECRET_KEY` ile imzalanır. Üretimde bu anahtar zorunlu ve en az 32 karakterdir (yoksa uygulama açılmaz).
- API anahtarları yalnızca backend ortam değişkenlerinden okunur; mobil uygulamaya hiçbir zaman konmaz.
- `.env` dosyaları commitlenmez; yalnızca sahte değerli `.env.example` depoda durur.
- Ücretli model çağrıları varsayılan olarak kapalıdır; bütçe onayı olmadan gerçek model çağrısı yapılmaz.
- Bilinen eksik: giriş denemelerine hız sınırı/hesap kilidi henüz yok (Aşama 5'te eklenecek).
