# Güvenlik denetimi ve canlıya alma ön koşulları

Denetim tarihi: 2026-10-06. Kapsam: API (`services/api`), yönetici paneli (`apps/admin`), mobil uygulama (`apps/mobile`), bağımlılıklar, yapılandırma ve depo (geçmiş dahil). Yöntem: kod incelemesi, bağımlılık taraması (`pip-audit`, `npm audit`), depo ve geçmiş gizli bilgi taraması, düzeltmeler için testler ve kasıtlı hata denemesi. **Bu bir sızma testi değildir**; canlıya çıkmadan önce dış bir sızma testi ayrıca düşünülmelidir.

## Bulgular ve durum

| # | Ciddiyet | Bulgu | Durum |
|---|---|---|---|
| G1 | Yüksek | Giriş ucunda hız sınırı/kilit yoktu (parola denemesi sınırsız). | **Düzeltildi.** Başarısız girişler (IP+hesap) 5, (hesap) 20, (IP) 40 denemede 15 dk engellenir; engelliyken doğru parola da reddedilir ve parola doğrulaması çalışmaz; 429 + `Retry-After`; hesabın var olup olmadığı ele verilmez. Ayarlar: `TALEPAKIS_LOGIN_*`. |
| G2 | Yüksek | Üretimde `app.seed` kapalı olduğundan **ilk yönetici hesabını oluşturmanın yolu yoktu**. | **Düzeltildi.** `python -m app.manage create-admin` (parola komut satırına yazılmaz: etkileşimli ya da `--password-stdin`; en az 12 karakter). |
| G3 | Yüksek | `TALEPAKIS_ENVIRONMENT` unutulursa uygulama herkesçe bilinen geliştirme anahtarıyla çalışırdı; bununla imzalanan sahte yönetici belirteci kabul edilirdi. | **Düzeltildi.** Geliştirme anahtarı yalnızca yerel veritabanıyla kullanılabilir; uzak veritabanına bağlanan süreç bu anahtarla hiç başlamaz. (Üretimde güçlü anahtar zaten zorunluydu.) |
| G4 | Orta | Parola değişse de eski oturum belirteçleri geçerli kalırdı; parola sıfırlama yolu yoktu. | **Düzeltildi.** Belirteç parola sürümüne (özetin kısa parmak izi) bağlıdır; parola değişince eski belirteçler 401 olur. `python -m app.manage reset-password`. Eski biçimli belirteçler (sürümsüz) reddedilir. |
| G5 | Orta | Güvenlik başlıkları yoktu; etkileşimli belge sayfaları (`/docs`, `/openapi.json`) üretimde açıktı. | **Düzeltildi.** `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cache-Control: no-store`, API için katı CSP; üretimde HSTS ve belge uçları kapalı. |
| G6 | Orta | İstek gövdesi sınırı yoktu (çok büyük gövdeyle bellek tüketme). | **Düzeltildi.** Varsayılan 64 KiB; `Content-Length` ve parçalı gönderimde 413. Ters vekilde de sınır konmalı. |
| G7 | Orta | Üretimde CORS'a `http://` veya yerel adres girilebiliyordu; üretimde geliştirme veritabanı parolası kabul ediliyordu. | **Düzeltildi.** Üretim ayarları doğrulanır: yalnızca `https://` panel adresi, geliştirme/boş veritabanı parolası reddedilir. |
| G8 | Düşük | Oturum belirteci 8 saat geçerli; yenileme ve sunucu tarafı iptal yok (yalnızca parola değişimi ve hesabı pasife alma iptal eder). Panelde belirteç `sessionStorage`'dadır (XSS'te çalınabilir). | **Kabul + önlem.** XSS yüzeyi: `dangerouslySetInnerHTML`/`eval` yok (tarandı), React kaçışlar. Panel statik sunumunda CSP başlığı gerekir (aşağıda). |
| G9 | Düşük | Kullanıcılar kendi parolasını değiştiremez; yalnızca operatör `reset-password` ile değiştirir. | **Karar bekliyor** (yeni ürün özelliği: mobil/panel ekranı gerekir). |
| G10 | Düşük | `/health` ortam adı ve sürümü gösterir (parmak izi). | **Kabul.** İstenirse ters vekilde dışarıya kapatılır; `/health/ready` ayrıntı vermez. |
| G11 | Bilgi | Bağımlılıklar: API `pip-audit` **0**, panel `npm audit` **0**. Mobil `npm audit`: 66 (16 orta, 50 yüksek), tamamı Expo/Jest derleme-geliştirme zincirinin geçişli paketleri (`braces`, `node-forge`, `uuid`…); önerilen "düzeltme" Expo 44'e kırıcı gerilemedir. | **Uygulanmadı** (`npm audit fix --force` yasak: uyumu bozar). Bu paketler sunucuda çalışmaz; mobil yayın derlemesinden (EAS) önce Expo SDK güncellemesiyle yeniden değerlendirilir. |
| G12 | Bilgi | Mobil API adresi pakete gömülür (`EXPO_PUBLIC_API_URL`); `http://` düz metin trafiktir. | **Canlıda `https://` zorunlu** (yayın derlemesinde verilir). |
| G13 | Bilgi | Gizli bilgi: depoda ve tüm geçmişte gerçek anahtar/parola yok (taranan desenler: `sk-ant-`, `AKIA…`, özel anahtar blokları, `ghp_…`); tek eşleşme, anahtar sızıntısı testindeki **sahte** değerlerdir. `.env` izlenmez. | Temiz. |
| G14 | Bilgi | Yetkilendirme: talepler nesne düzeyinde süzülür (`_visible`), başkasının talebi 404 döner; yönetici uçları `require_admin`; rol ve aktiflik her istekte veritabanından okunur; deney uçları yalnızca yönetici, salt okunur, yol enjeksiyonuna kapalı. SQL: ORM parametreli. | Testli (PostgreSQL'li paket). |
| G15 | Bilgi | Model anahtarları yalnızca ortam değişkeninden okunur; ürün worker'ı ücretli çağrı yapmaz; ücretli çağrılar varsayılan kapalı. | Üretimde de böyle kalmalı (`TALEPAKIS_PAID_MODEL_CALLS_ENABLED` verilmez). |

## Canlıya alma ön koşulları (platformdan bağımsız)

1. **TLS/HTTPS** (HSTS API'de hazır). API ve panel ayrı alan adlarında olabilir; mobil için yalnızca `https://`.
2. **Ortam değişkenleri** (sunucuda, depoya değil): `TALEPAKIS_ENVIRONMENT=production`, `TALEPAKIS_SECRET_KEY` (en az 32 karakter rastgele: `python -c "import secrets; print(secrets.token_urlsafe(48))"`), `TALEPAKIS_DATABASE_URL` (güçlü parola, mümkünse TLS: `?sslmode=require`), `TALEPAKIS_CORS_ORIGINS=["https://panel.<alan-adı>"]`. Bunlar yoksa/yanlışsa uygulama **açılmaz** (bilerek).
3. **Veritabanı:** yönetilen PostgreSQL ya da ayrı, dışarıya kapalı bir kapsayıcı; düzenli yedek ve geri yükleme denemesi. Geliştirme `docker-compose.yml`'i üretim için değildir (sabit parola).
4. **Migration:** dağıtımda `alembic upgrade head`. Demo verisi yüklenmez; ilk yönetici `python -m app.manage create-admin` ile.
5. **Ters vekil:** istek gövdesi sınırı, `uvicorn --proxy-headers --forwarded-allow-ips=<vekil adresi>` (yoksa giriş sınırlayıcısı tüm istekleri tek IP görür), isteğe bağlı vekil düzeyinde oran sınırı. API **tek süreç** çalıştırılırsa sınırlayıcı sayaçları tutarlıdır; çok süreçte sınır süreç sayısıyla çarpılır.
6. **Panelin statik sunumu için başlıklar** (barındırıcıda ayarlanır; `index.html`'e CSP konamaz):
   `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' https://api.<alan-adı>; frame-ancestors 'none'; base-uri 'none'; form-action 'self'` · `X-Content-Type-Options: nosniff` · `Referrer-Policy: no-referrer` · `Strict-Transport-Security`. Panel `VITE_API_URL` ile derlenir (gizli bilgi konmaz).
7. **Worker** ayrı süreç olarak çalışır (`python -m app.worker`), yalnızca ücretsiz stratejiler; süreç yöneticisi (yeniden başlatma) gerekir.
8. **Günlük ve izleme:** hata günlükleri toplanmalı; günlüklere parola/belirteç/talep metni yazılmaz (uygulama yazmaz; vekil erişim günlüğü `Authorization` başlığını kaydetmemeli).
9. **Gizli bilgi yönetimi:** ortam değişkenleri barındırıcının gizli bilgi deposunda; kimseye sohbetten/e-postadan iletilmez. Sızıntı şüphesinde `SECRET_KEY` değiştirmek tüm oturumları düşürür.
10. **Test hesapları:** üretimde `yonetici`/demo hesapları bulunmaz (seed çalışmaz). Gerçek kullanıcılar panelden oluşturulur; ilk giriş parolaları kullanıcıya güvenli kanaldan iletilir.

## Bilinen kalan riskler

- Kimlik doğrulama tek faktörlüdür; yönetici hesapları için ikinci faktör yoktur.
- Kullanıcı kendi parolasını değiştiremez (G9); belirteç sunucuda iptal edilemez (G8).
- Giriş sınırlayıcısı süreç belleğindedir; yeniden başlatmada sayaçlar sıfırlanır.
- Mobil derleme zincirinin bağımlılık uyarıları (G11) mobil yayına kadar açık.
- Dış sızma testi ve gerçek yük/performans ölçümü yapılmadı.
