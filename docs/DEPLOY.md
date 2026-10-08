# Canlı portföy demosu: ücretsiz dağıtım yönergesi

Hedef: ziyaretçilerin tarayıcıdan deneyebildiği, **gerçek Jev** ile karar üreten bir demo. Hepsi
ücretsiz planlarla: statik demo sitesi (Render Static) + API (Render Web, ücretsiz) + veritabanı (Neon,
ücretsiz). **Ücretli hosting, veritabanı, alan adı veya ek hizmet gerekmez ve satın alınmaz.** Yalnızca
gerçek Jev kullanımına, sizin onaylayacağınız küçük bir bütçe ayrılır (aşağıda).

> Ücretsiz barındırma **sürekli açık değildir**. İlk ziyarette API ve veritabanı uyanır (aşağıdaki tablo).
> Sayfa, ziyaretçiye bunu söyler; **zamanlanmış ping veya yapay trafik KULLANILMAZ**.

## Mimari

```
Ziyaretçi ─► Statik demo sitesi (Render Static; uyumaz)   ─ önceden kaydedilmiş sonuçlar buradan
                │  yalnızca "Jev ile dene" için ▼
              API (Render Web, ücretsiz; boştayken uyur) ─► Neon PostgreSQL (ücretsiz; boştayken uyur)
                                                       └► Jev API (yalnızca jev_only; tek deneme)
```

- Ücretsiz planda **ayrı, sürekli çalışan worker yoktur** ve veritabanını sürekli yoklayan döngü
  (Neon'u uyanık tutardı) **yoktur**. Talep ve karar işi kalıcı kaydedilir, Jev kararı aynı HTTP isteğinin
  içinde, 15 sn zaman aşımıyla, tek denemelik çalışır (`app/services/demo.py`). Mevcut worker
  (`python -m app.worker`) diğer dağıtımlar için aynen durur.
- HTTP yanıtından sonra bellekte çalışan arka plan görevine güvenilmez; süreç kapanırsa durum
  veritabanındadır.
- **Tek sağlayıcı: Jev (`jev_only`).** Anthropic ve hibrit canlı demoda kurulamaz; Jev başarısız olursa
  başka sağlayıcıya geçilmez, mock sonuç gerçekmiş gibi gösterilmez.

## Ücretsiz plan koşulları (resmî belgelerden, 2026-10-08)

| Kaynak | Koşul | Demoya etkisi |
|---|---|---|
| Render Web (ücretsiz) | 15 dk trafik yoksa uyur; uyanma "yaklaşık 1 dakika" ([belge](https://render.com/docs/free)) | İlk ziyaretçi bekler; arayüz bunu söyler |
| | 750 ücretsiz örnek saati/ay; bitince tüm ücretsiz web servisleri ay sonuna dek askıya alınır | Kota dolarsa demo kapanır (ücret çıkmaz) |
| | Geçici disk; "istediği zaman yeniden başlatabilir" | Durum yalnızca PostgreSQL'de |
| | Tek örnek; SSH/kabuk yok; giden bant ve derleme dakikası kotası var ama **belgede sayısı yok** | Kota sayısını doğrulayamadık; ödeme yöntemi eklemezseniz aşımda hizmet askıya alınır, ücret çıkmaz |
| Render Static | Ücretsiz; aynı bant/derleme kotasını kullanır; uyumaz | API'siz açılır |
| Neon Free ([belge](https://neon.com/docs/introduction/plans)) | 1 GB/proje, 100 CU-saat/ay; 5 dk boştaysa uyur (kapatılamaz); çıkış 5 GB/ay | Demo verisi küçük tutulur ve silinir |
| | Geri yükleme penceresi 6 saat; zamanlanmış yedek yok; 1 elle anlık görüntü | Düzenli `pg_dump` (aşağıda) |
| | 0,25 CU'da `max_connections` 104; havuzlu bağlantı 10.000 istemciye kadar ([belge](https://neon.com/docs/connect/connection-pooling)) | Küçük havuz yeterli |
| | Limit dolunca hesaplama askıya alınır veya yazma başarısız olur; ücret kesilmez, veri silinmez | Kota dolarsa demo hata verir |
| Jev | idempotency anahtarı yok; zaman aşımı ve "başarısız istek faturalanır mı" belgelenmemiş ([belge](https://docs.typesafe.ai/api.md)) | "Tam olarak bir kez" garantisi verilmez; belirsiz çağrı yeniden gönderilmez, en kötü bedelle sayılır |

Render'ın istemci IP başlığı davranışı resmî belgede **yok** (topluluk raporları tutarsız). Bu yüzden
**IP sınırı varsayılan kapalıdır** ve tek başına güvenlik sayılmaz (aşağıda).

## Sizin yapacağınız adımlar (hesap, giriş ve gizli değerler)

Bunları ben yapamam ve yapmamalıyım (hesap açma, giriş, gizli anahtar girme). Her biri kısa:

### 1) Neon (veritabanı)
1. https://neon.com adresinde ücretsiz hesap açın; **yeni proje** oluşturun (bölge: AWS **Frankfurt /
   eu-central-1**, Render API ile aynı bölge).
2. Panelde **Connect** → iki adres kopyalayın: **havuzlu** (host adında `-pooler`) ve **doğrudan**.
   İkisi de parola içerir: **sohbete, Git'e veya ekran görüntüsüne koymayın.**

### 2) Render (API + statik site)
1. https://render.com → GitHub ile giriş → **New → Blueprint** → `EmirhanFirat/Mobil-Servis-Sistemi`
   deposunu seçin (`render.yaml` okunur; iki ücretsiz servis kurulur; **ödeme yöntemi eklemeyin**).
2. İstenen gizli değişkenleri **Render panelinde** girin (`sync: false` olanlar):
   - `TALEPAKIS_DATABASE_URL` = Neon **havuzlu** adres; sonuna `?sslmode=require` ekli olmalı.
   - `TALEPAKIS_MIGRATION_DATABASE_URL` = Neon **doğrudan** adres (`?sslmode=require`).
   - `TALEPAKIS_CORS_ORIGINS` = `["https://<demo-sitesi-adresi>.onrender.com"]` (JSON dizisi; site adresi
     servis oluşunca görünür, gerekirse sonradan güncelleyin).
   - `VITE_API_URL` (statik site) = `https://<api-adresi>.onrender.com`.
   - `TALEPAKIS_JEV_API_KEY` = **şimdilik boş bırakın** (onay sonrası, aşağıda).
3. API servisi ilk açılışta migration'ı çalıştırır (`alembic upgrade head`); günlükte "Running upgrade"
   görmelisiniz. Adresler beklenenden farklıysa (`-xxxx` eki) iki değişkeni düzeltip **Manual Deploy**
   yapın.

### 3) Bütçeyi tanımlama (YALNIZCA tutarı onayladıktan sonra)
Ücretsiz Render servisinde kabuk yoktur; bütçe **kendi bilgisayarınızdan**, Neon doğrudan adresiyle
tanımlanır (oturum boyunca geçerli, geçmişe yazılmaz):

```powershell
cd services\api
$env:TALEPAKIS_DATABASE_URL = "<Neon doğrudan adres>"
$env:TALEPAKIS_SECRET_KEY   = "bu-komut-icin-gecici-yerel-deger-0123456789"   # yalnızca yerel komut içindir
.\.venv\Scripts\python.exe -m app.manage create-budget --id canli-demo --cap-usd <ONAYLANAN_TUTAR> --purpose "Canlı demo"
.\.venv\Scripts\python.exe -m app.manage budget-status --id canli-demo
```

### 4) Gerçek Jev'i açma (bütçe tanımlandıktan sonra)
Render → `talepakis-api` → **Environment**: `TALEPAKIS_JEV_API_KEY` = Jev anahtarınız (gizli),
`TALEPAKIS_PAID_MODEL_CALLS_ENABLED` = `true` → kaydedin (servis yeniden başlar). Anahtarı daha önce
sohbette veya başka yerde paylaştıysanız **yenisini üretin**.

## Doğrulama (yayından sonra)
- `https://<api>/health` → `{"status":"ok"...}`; `https://<api>/docs` → **404** (üretimde kapalı).
- `https://<api>/demo/status` → `database_ready: true`, `enabled: true` (bütçe ve anahtar tanımlıysa).
- Demo sitesini açın: hazırlık süresi gösterilir; bir örnek seçip **Gerçek Jev ile karar üret**.
- Tarayıcı geliştirici araçları → Network: `Content-Security-Policy` meta etiketi var; sayfa yalnızca
  kendi kaynağı ve API'ye bağlanır.
- Render IP başlığı: bir istekte `X-Forwarded-For`/`CF-Connecting-IP` gerçekten ziyaretçi IP'sini
  taşıyor mu doğrulamadan `TALEPAKIS_DEMO_IP_LIMITS_ENABLED` ve `TALEPAKIS_CLIENT_IP_HEADER` açmayın.

## Güvenlik ve sınırlar (sunucu tarafında)

| Sınır | Varsayılan | Ayar |
|---|---|---|
| Metin uzunluğu | başlık 120, açıklama 1000, konum 120 | kodda sabit (`schemas_demo.py`) |
| Oturum başına karar | 5 | `TALEPAKIS_DEMO_MAX_DECISIONS_PER_SESSION` |
| Eşzamanlı Jev çağrısı (tüm süreçler) | 2 | `TALEPAKIS_DEMO_MAX_CONCURRENT_CALLS` |
| Günlük ziyaretçi / karar (genel) | 300 / 500 | `..._MAX_SESSIONS_PER_DAY`, `..._MAX_DECISIONS_PER_DAY` |
| IP başına (en iyi çaba, **kapalı**) | 5 oturum, 20 karar / saat | `TALEPAKIS_DEMO_IP_LIMITS_ENABLED` |
| İstek gövdesi | 64 KiB | `TALEPAKIS_MAX_REQUEST_BODY_BYTES` |
| **Toplam Jev bütçesi** | onaylanan tutar | `manage create-budget` (PostgreSQL, atomik) |

- **IP tek başına yeterli değildir**: asıl sınırlar oturum/genel kotalar, eşzamanlılık ve bütçedir.
  Bütçe her çağrıdan önce satır kilidiyle rezerve edilir; eşzamanlı istekler ve yeniden başlatmalar
  toplam sınırı aşamaz. Bilinen gerçek harcama, muhafazakâr (bilinemeyen) bedel ve çözülmemiş
  rezervasyon **ayrı** kaydedilir; süreç çağrıdan sonra ölürse rezervasyon sıfır sayılmaz.
- Ziyaretçi hesapları parolasızdır, rol yükseltemez, yalnızca kendi taleplerini görür; normal talep
  açma/durum geçişi ve yönetici uçları onlara kapalıdır. Demo sitesinde yönetici ekranları **yoktur**.
- Bütçe fiyatı: Jev `jev-1.13.0`, 0,042 USD / 1M girdi tokenı, çıktı ücretsiz (2026-10-08'de
  doğrulandı). Hesaplama: ücret yalnızca Jev'in bildirdiği kullanımdan; bildirilmezse bilinmez ve
  rezervasyon bedeliyle sayılır. Sağlayıcı faturasıyla birebir örtüşme **garanti edilmez**.

## Veri saklama ve temizleme
Ziyaretçi hesabı ve talepleri **72 saat** sonra silinir (`TALEPAKIS_DEMO_RETENTION_HOURS`): her yeni
oturum açılışında süresi dolanlar (en çok 100) silinir; elle: `python -m app.manage purge-demo` (Neon
doğrudan adresi ve geçici `TALEPAKIS_SECRET_KEY` ile, yukarıdaki gibi). Yalnızca `is_demo` hesapları
silinir; yerel E2E kayıtları ve deney sonuçları etkilenmez. Bütçe kayıtları (yalnızca tutarlar) kalır.

## Yedekleme, geri yükleme, geri dönüş
- **Yedek** (Neon ücretsizde zamanlanmış yedek yok; yalnızca 6 saatlik geçmiş): önemli olan tek kalıcı
  durum bütçe tablolarıdır.
  ```powershell
  pg_dump "<Neon doğrudan adres>" --table=budgets --table=budget_entries --data-only -f butce-yedek.sql
  ```
  Tam yedek için `pg_dump "<adres>" -Fc -f talepakis.dump`; geri yükleme `pg_restore -d "<adres>" talepakis.dump`
  (boş bir veritabanına). Yedek dosyalarında parola yoktur ama **ziyaretçi metinleri** olabilir: Git'e koymayın.
- **Geri dönüş (kod):** Render → servis → **Deploys** → önceki başarılı yayında **Rollback**. Migration'lar
  yalnızca ekler; kodu geri almak şemayı bozmaz.
- **Acil durdurma (harcama):** `TALEPAKIS_PAID_MODEL_CALLS_ENABLED=false` (veya anahtarı silin) → demo
  "yapılandırılmadı" der, Jev'e istek gitmez. Tam kapatma: `TALEPAKIS_DEMO_ENABLED=false` veya servisi
  askıya alın.
- Şema geri alma (yalnızca bilinçli): `alembic downgrade 0002` yeni tabloları kaldırır; önce yedek alın.
  Otomatik veri sıfırlama veya yıkıcı migration yoktur.

## Gizli değişken ADLARI (değerler yalnızca Render panelinde)
`TALEPAKIS_DATABASE_URL`, `TALEPAKIS_MIGRATION_DATABASE_URL`, `TALEPAKIS_SECRET_KEY` (Render üretir),
`TALEPAKIS_JEV_API_KEY`. Gizli olmayanlar `render.yaml` içindedir. `TALEPAKIS_ANTHROPIC_API_KEY`
**tanımlanmaz** (canlı demoda Anthropic yoktur).
