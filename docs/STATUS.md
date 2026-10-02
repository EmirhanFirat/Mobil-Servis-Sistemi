# Durum

Son güncelleme: 2026-10-02. Aşama: **0 ve 1 tamamlandı** (API, mobil uygulama, yönetici paneli). **Aşama 2 sürüyor:** karar motorunun çekirdeği hazır (sözleşme, `rule_based`, mock adaptör, hibrit/tek sağlayıcı stratejileri, güvenlik kapısı, yönlendirme, sınırlı retry, fiyat tablosu); veritabanı katmanı (kalıcı iş durumu, `decisions`/`model_calls` tabloları) Docker açılınca yapılacak.

## Çalışan

- `services/api`: giriş (Argon2 + imzalı token), üç rol (talep sahibi, teknik görevli, yönetici), talep açma/listeleme/ayrıntı, ekip kuyruğu, rol ve bağlama göre durum geçişleri, olay geçmişi (görevli adlarıyla), yönetici atama/düzeltme, kullanıcı ve ekip üyeliği yönetimi, sözlük ucu, `/health` ve `/health/ready`.
- `apps/mobile` (Expo SDK 57): giriş, Taleplerim, Yeni talep, İş listesi (görevli/yönetici, süzgeçli), Hesap, talep ayrıntısı + geçmiş + sunucunun izin verdiği işlemler. Yükleniyor, boş liste, bağlantı hatası, oturum süresi dolması ve yetkisiz/bulunamadı durumları ele alınıyor. Karanlık/açık tema.
- `apps/admin` (Vite 8 + React 19): yönetici girişi (yönetici olmayan hesap reddedilir), talep listesi (görünümler + sayfalama), talep ayrıntısı (geçmiş, durum işlemleri, ekip/görevli ataması, öncelik/kategori/eksik bilgi düzeltme), kullanıcı yönetimi, ekip üyeliği yönetimi.
- `services/api/app/decision` (veritabanından bağımsız çekirdek): ortak karar sözleşmesi; `rule_based` strateji; Jev benzeri ve LLM benzeri deterministik **mock** sağlayıcı (hata enjeksiyonlu); `llm_only`/`jev_only` (`ProviderStrategy`) ve `hybrid` stratejileri; tüm stratejilere uygulanan güvenlik kapısı ve talimat-enjeksiyonu şüphesi; deterministik ekip yönlendirmesi (`needs_review` veya kategorinin varsayılan ekibi); sınırlı retry; tarihli fiyat tablosu (Jev `jev-1.13.0`: girdi 0,042 USD/1M token). **Gerçek Jev/LLM çağrısı henüz yok**; hiçbir sağlayıcıya ağ isteği atılmadı. Kararlar için DECISIONS D19–D22, sağlayıcı bilgileri için `docs/SAGLAYICILAR.md`.
- PostgreSQL 17 (Docker), Alembic migration'ı (`0001`), dev seed'i (`python -m app.seed`: 8 kullanıcı, 4 örnek talep).
- Kalıcı kurallar `AGENTS.md` içinde; uzak depo GitHub `origin`.

## Doğrulananlar

- API (2026-10-01): **145 test geçti** (gerçek PostgreSQL; migration, erişim kontrolü, akış, yönetici işlemleri, seed). `ruff` temiz. Mutasyon denemesiyle testlerin kilit, görünürlük, JWT imzası, pasif hesap ve yetki hatalarını yakaladığı görüldü.
- Mobil (2026-10-01): **51 Jest testi** geçti; `tsc --noEmit` ve `expo lint` temiz. Testler 5xx'te sunucunun ham metninin gösterilmesi hatasını yakaladı ve düzeltildi.
- Karar motoru çekirdeği (2026-10-02): **86 test geçti** (veritabanı gerekmiyor): metin normalleştirme, güvenlik kapısı, enjeksiyon şüphesi, `rule_based` örnekleri, mock davranışı, retry/üstel bekleme/sınırlı deneme, maliyet (Decimal, bilinmeyen maliyetin gizlenmemesi), hibrit akış, "sessiz sağlayıcı değişimi yok", yönlendirme kuralları. Mutasyon denemesinde 12 kasıtlı hata yakalandı (1 zayıf test bulundu ve güçlendirildi). `ruff` temiz. Not: bu oturumda Docker açılmadığı için API'nin veritabanlı 145 testi yeniden çalıştırılamadı; o kodlara dokunulmadı.
- Yönetici paneli (2026-10-02): **75 Vitest testi** geçti (API istemcisi, form mantığı, geçmiş cümleleri, işlem etiketleri, oturum mantığı, atama/düzeltme/durum işlemi bileşenleri, giriş sayfası); `tsc -b`, `oxlint` (uyarısız), `vite build` ve `npm audit` (0 açık) temiz. Mutasyon denemesinde 3 zayıf test (ekip değişince görevli sıfırlama, çift istek, oturum mantığı) bulundu ve güçlendirildi; sonra 8 kasıtlı hatanın hepsi yakalandı.
- Mobil ve panel, `react-native-web`/Vite ile tarayıcıda gerçek API'ye karşı uçtan uca denendi. Mobil: talep sahibi/görevli girişi, liste, süzgeç, ayrıntı, notlu işlemler, yeni talep, 401 ve bağlantı hatası. Panel: yönetici olmayan hesabın reddi, düzeltme, kategoriye göre ekip önerisi + atama, geçmiş cümleleri, kullanıcı oluşturma, ekibe üye ekleme ve açık işi olan görevlinin çıkarılmasının reddi.

## Henüz yok / ölçülmedi

- **Mobil uygulama gerçek telefonda veya emülatörde denenmedi** (bu ortamda yok); yalnızca web önizlemesinde doğrulandı. SecureStore, klavye ve platform farkları cihazda ayrıca denenmeli.
- Panelde tarayıcı doğrulamasından sonra yapılan iki küçük değişiklik (üst çubuk CSS'i, açılır listelere `aria-label`) tarayıcıda yeniden denenmedi: 2026-10-02'de Docker Desktop motoru açılmadığı için API/DB çalıştırılamadı. Bu değişiklikler 75 Vitest testi, `tsc`, `oxlint` ve `vite build` ile doğrulandı. Docker Desktop arayüzünde kullanıcı onayı bekleyen bir pencere olabilir; açıldığında panel bir kez daha elle denenmeli.
- Karar motoru (kategori/öncelik önerisi), `decisions` ve `model_calls` tabloları, Jev/LLM adaptörleri, benchmark, panelde deney sonuçları: Aşama 2–4. Hiçbir model ölçümü yapılmadı; ücretli çağrılar kapalı. Şu an kategori/öncelik/ekibi yalnızca yönetici belirler.
- Mobil ve panelde ekran/bileşen testleri sınırlı (panelde ana bileşenler var, mobilde yalnızca mantık); yük/performans ölçümü yapılmadı.

## Sınırlamalar ve açık konular

- Giriş denemelerine hız sınırı/hesap kilidi yok (Aşama 5). Yenileme belirteci yok; token 8 saat geçerli. Panelde içerik güvenlik politikası yok (Aşama 5).
- `httpx` → `httpx2` geçişi kullanıcı onayını bekliyor (DECISIONS D7); API testlerinde bir kullanımdan kalkma uyarısı görünüyor.
- `npm audit` mobil bağımlılıklarda 14 orta düzey uyarı bildiriyor (Expo geçişli bağımlılıkları). `npm audit fix --force` uyumu bozabileceği için çalıştırılmadı; Expo SDK güncellemeleriyle izlenecek. Panelde uyarı yok.
- API tipleri, olay cümleleri ve işlem etiketleri mobil ve panelde ayrı kopyalar (DECISIONS D18); sözleşme değişirse ikisi birlikte güncellenmeli.
- Şablonun getirdiği `.claude/settings.json` (Expo eklentisini etkinleştiriyordu) ve Expo'nun `LICENSE`/`README` dosyaları sahibinin onayı olmadan projeye alınmadı, silindi. `apps/mobile/AGENTS.md` (Expo'ya özgü yönergeler) incelendi ve tutuldu.
- Bağımlılık kilidi Windows'ta üretildi; deploy aşamasında hedef platformda yeniden üretilmeli (DECISIONS D4).
- Commit e-postası `emirhanfirat44@gmail.com`; GitHub hesabında doğrulanmış değilse commitler profile bağlanmaz.

## Sıradaki somut adım

Aşama 2'nin veritabanı yarısı (**Docker Desktop motoru açık olmalı**): `decisions`, `model_calls` ve kalıcı iş tablosu (`decision_jobs`) için Alembic migration'ı; talep oluşturma ile karar işini **aynı işlemde** kuyruğa yazmak (model çalışmasa da talep kaybolmaz); ayrı worker (DB tabanlı polling, `FOR UPDATE SKIP LOCKED`, yeniden başlatmada bekleyen işler kaybolmaz); kararı talebe **yalnızca** durumu `new` ve insan değişikliği yokken uygulamak (insan düzeltmesini ezme), ilk model kararını ve insan düzeltmesini ayrı tutmak; yeniden işlemede çift atama/olay üretmemek; sağlayıcı kalıcı hatasında talebi koruyup `needs_review` + görünür hata olayı yazmak; yönetici arayüzünde kararın kaynağını (strateji, mock mu) göstermek. Sonra Aşama 3 (gerçek Jev ve ekonomik LLM adaptörleri; bütçe onayı ve API anahtarı gerekir).
