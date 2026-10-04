# TalepAkış

Kampüs veya yurt bakım ekipleri için mobil servis talebi ve iş yönlendirme uygulaması. Kullanıcı metinle talep açar; sistem kategori, öncelik ve eksik bilgiyi önerir ve talebi ilgili ekip kuyruğuna yönlendirir.

Projenin araştırma sorusu: **Türkçe servis taleplerinde Jev, ekonomik bir LLM ve hibrit yaklaşım arasında doğruluk, işlem süresi ve maliyet nasıl değişiyor?** Sonuçlar ölçülmeden hiçbir tasarruf veya başarı iddiası yapılmaz.

> **Durum:** Aşama 1 (AI olmadan ürün) tamamlandı: API, mobil uygulama ve yönetici paneli. Giriş ve roller, talep açma/listeleme/ayrıntı, ekip kuyruğu, rol bazlı durum geçişleri, olay geçmişi, yönetici düzeltme/atama ve kullanıcı/ekip yönetimi çalışıyor. Karar motoru (kategori/öncelik önerisi) ve model karşılaştırması henüz yok; şu an yönlendirmeyi yönetici yapar. Mobil uygulama ve panel tarayıcıda gerçek API'ye karşı uçtan uca doğrulandı; mobil gerçek telefonda/emülatörde henüz denenmedi. Ayrıntı: [docs/STATUS.md](docs/STATUS.md), [docs/PLAN.md](docs/PLAN.md).

## Yapı

```
services/api   FastAPI sunucusu (Python 3.12, SQLAlchemy, Alembic, PostgreSQL)
apps/mobile    Expo (SDK 57) + React Native + TypeScript
apps/admin     Yönetici paneli: React + Vite + TypeScript (web)
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

Talepler açılırken bir **karar işi** kaydedilir (kategori/öncelik/eksik bilgi önerisi). İşleri ayrı bir süreç işler; API çalışmasa da talepler kaybolmaz:

```powershell
# 5) Karar worker'ı (ayrı terminalde sürekli çalışır; kuyruğu bir kez boşaltmak için --once)
.\.venv\Scripts\python.exe -m app.worker
```

Worker şimdilik yalnızca ücretsiz stratejileri çalıştırır (`TALEPAKIS_DECISION_STRATEGY`: varsayılan `rule_based`; `mock_jev`, `mock_llm`, `mock_hybrid`; `off` işi kapatır). Gerçek Jev/LLM çağrıları ürün akışında kapalıdır.

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

## Yönetici panelini çalıştırma

API çalışıyorken:

```powershell
cd apps\admin
npm install
npm run dev                 # http://localhost:5173
```

Demo hesabı `yonetici` ile giriş yap (yönetici olmayan hesaplar panele giremez). Panel: **Talepler** (Yönlendirme bekleyen / Ekipte / Çözüldü / Kapatıldı / Tümü, sayfalı), **talep ayrıntısı** (geçmiş, durum işlemleri, ekip ve görevli ataması, öncelik/kategori/eksik bilgi düzeltme; ekip, kategorinin varsayılan ekibinden önerilir), **Kullanıcılar** (oluştur, rol değiştir, pasife al) ve **Ekipler** (görevli ekle/çıkar).

### Model karşılaştırma sayfası

Üstteki menüden **Model karşılaştırma** (`http://localhost:5173/model-karsilastirma`; yalnızca yönetici). Sayfa `evaluation/runs/` altındaki **kayıtlı deneyleri salt okunur** gösterir; açmak, yenilemek, süzmek veya dışa aktarmak **hiçbir model çağrısı başlatmaz** ve bütçe defterine dokunmaz. Deney yoksa veya dosyaları eksikse açık bir boş durum görünür, rakam uydurulmaz.

- **Karşılaştırma:** aynı deneyde Jev, LLM ve hibrit yan yana (doğruluk, macro-F1, kaçırılan yüksek öncelik, inceleme/otomasyon, p50/p95 süre, ücret ve token, çağrı/retry/hata, hibritin LLM'e geçiş oranı ve tetikleyen sorular). Ölçülen toplamlar ile "1.000 talebe ölçeklenen **TAHMİN**" ayrı satırlardadır; bilinmeyen değer 0 yazılmaz.
- **Örnek bazında inceleme:** tam metin, beklenen etiket, üç stratejinin tahmini yan yana, süre/ücret/token, hibritin LLM'e gönderdiği sorular; tartışmalı etiketli örnekler (ör. s023) işaretlenir, etiketler değişmez.
- **Paylaşım görünümü:** ekran görüntüsüne uygun Türkçe özet kartı (üç modelin temel ölçümleri, ayrı ücret ve süre grafikleri, bir örnek talep, veri kaynağı/örnek sayısı/tarih/sürüm altbilgisi). **PNG indir** kartın kendisini indirir; **CSV indir** ve **Markdown tablo indir** aynı veriden üretilir (CSV: Excel için BOM'lu, ondalık nokta, bilinmeyen değer boş hücre).
- Mevcut ilk deney **5 sentetik geliştirme örneği — bağlantı denemesi**dir ve eski **hibrit v1** yönlendirmesiyle alınmıştır; doğruluk/maliyet sonucu çıkarılamaz. Farklı veri/kapsam/eşik/sürümle alınmış deneyler kendiliğinden karşılaştırılmaz; v1/v2 öncesi-sonrası karşılaştırması aynı örneklerde ayrı bir değerlendirme olarak yapılmalıdır.

Deney klasörü varsayılan olarak `evaluation/runs`'tır; farklı bir yer için API'de `TALEPAKIS_EXPERIMENTS_DIR` verilir. İstemci dosya yolu veremez, yalnızca `run_id`/`sample_id` ile okunur.

API adresi `VITE_API_URL` ile verilir (varsayılan `http://127.0.0.1:8000`; derleme zamanında pakete gömülür, gizli bilgi koyma). Tarayıcıdan erişebilmesi için panelin adresi API'nin CORS izin listesinde olmalıdır (`TALEPAKIS_CORS_ORIGINS`; geliştirme varsayılanı 5173 ve 8081 portlarını içerir). Oturum token'ı `sessionStorage`'da tutulur: sekme kapanınca silinir.

## Testler ve lint

Mobil: `cd apps\mobile`, sonra `npm test` (Jest), `npm run typecheck`, `npx expo lint`.

Yönetici paneli: `cd apps\admin`, sonra `npm test` (Vitest), `npm run typecheck`, `npm run lint`, `npm run build`.

API testleri gerçek PostgreSQL ister: her çalıştırmada ayrı bir `talepakis_test` veritabanı **sıfırdan** kurulur ve migration'lar uygulanır; geliştirme verisine dokunulmaz. Docker kapalıysa testler açık bir mesajla durur.

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

Geliştirme veritabanını sıfırlamak için: `docker compose down -v`, sonra yukarıdaki 1–3. adımlar.

## Sorun giderme

**Girişte "Sunucu zamanında yanıt vermedi" veya "Sunucu şu anda veritabanına ulaşamıyor"** (hem telefonda hem web önizlemesinde): neredeyse her zaman Docker'daki veritabanı kapalıdır. Docker Desktop yeniden başlayınca (bilgisayar açılışı, güncelleme) konteyner durabilir.

```powershell
docker compose ps                  # db satırı "Up (healthy)" olmalı
docker compose up -d db            # kapalıysa başlatır; veri korunur (pgdata birimi)
```

API'nin kendisi ayaktaysa `http://127.0.0.1:8000/health/ready` adresi `{"status":"ok","database":"ok"}` demelidir; veritabanı yoksa 503 döner. `docker-compose.yml` artık `restart: unless-stopped` içerir: konteyner bir kez bu ayarla oluşturulduktan sonra Docker Desktop her açıldığında veritabanı kendiliğinden kalkar. Veritabanı yokken API artık asılı kalmaz; 5 sn içinde açık bir 503 (`database_unavailable`) döner, worker çökmeden bekleyip yeniden dener.

**Telefon API'ye ulaşamıyor, ama Expo uygulaması açılıyor:** bilgisayarın Wi-Fi adresi ağ değişince değişir (`(Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Wi-Fi").IPAddress`). Telefonun tarayıcısında `http://<IP>:8000/health` açılmıyorsa sorun ağdadır (farklı ağ, istemci yalıtımı veya güvenlik duvarı); API'yi `--host 0.0.0.0` ile başlattığından emin ol ve Expo'yu o ağdayken yeniden başlat. `EXPO_PUBLIC_API_URL` verirsen `<IP>` yer tutucusu yerine gerçek adresi yaz; Expo'yu o değişkenle başlattığın sekmede ver.

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
