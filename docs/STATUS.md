# Durum

Son güncelleme: 2026-10-01. Aşama: **0 tamamlandı; Aşama 1'de API ve mobil uygulama tamamlandı**, yönetici paneli (web) sırada.

## Çalışan

- `services/api`: giriş (Argon2 + imzalı token), üç rol (talep sahibi, teknik görevli, yönetici), talep açma/listeleme/ayrıntı, ekip kuyruğu, rol ve bağlama göre durum geçişleri, olay geçmişi (görevli adlarıyla), yönetici atama/düzeltme, kullanıcı ve ekip üyeliği yönetimi, sözlük ucu, `/health` ve `/health/ready`.
- `apps/mobile` (Expo SDK 57): giriş, Taleplerim, Yeni talep, İş listesi (görevli/yönetici, süzgeçli), Hesap, talep ayrıntısı + geçmiş + sunucunun izin verdiği işlemler. Yükleniyor, boş liste, bağlantı hatası, oturum süresi dolması ve yetkisiz/bulunamadı durumları ele alınıyor. Karanlık/açık tema.
- PostgreSQL 17 (Docker), Alembic migration'ı (`0001`), dev seed'i (`python -m app.seed`: 8 kullanıcı, 4 örnek talep).
- Kalıcı kurallar `AGENTS.md` içinde; uzak depo GitHub `origin`.

## Doğrulananlar (2026-10-01)

- API: **145 test geçti** (gerçek PostgreSQL; migration, erişim kontrolü, akış, yönetici işlemleri, seed). `ruff check` ve `ruff format --check` temiz. Mutasyon denemesiyle (kasıtlı hata) testlerin kilit, görünürlük, JWT imzası, pasif hesap ve yetki hatalarını yakaladığı görüldü.
- Mobil: **51 Jest testi geçti** (API istemcisi, adres çözümleme, olay geçmişi cümleleri, işlem etiketleri, doğrulama); `tsc --noEmit` ve `expo lint` temiz. Test, 5xx'te sunucu ham metninin gösterilmesi hatasını yakaladı ve düzeltildi.
- Mobil uygulama `react-native-web` ile tarayıcıda, gerçek API'ye karşı uçtan uca denendi: talep sahibi girişi, liste, görevli iş listesi ve süzgeçleri, ayrıntı/geçmiş, çözüldü işlemi, yeniden açma (gerçek klavye yazımıyla notlu), yeni talep + alan doğrulaması, geçersiz token (giriş ekranı + uyarı), sunucu kapalıyken bağlantı hatası ve "Tekrar dene".
- Gerçek uvicorn sunucusu üzerinden uçtan uca API akışı, başkasının talebinde 404, CORS yalnızca izinli adreslere açık.

## Henüz yok / ölçülmedi

- Yönetici paneli (`apps/admin`): talep listesi, düzeltme, ekip atama, kullanıcı/ekip yönetimi (Aşama 1'in kalanı).
- **Mobil uygulama gerçek telefonda veya emülatörde denenmedi** (bu ortamda yok); yalnızca web önizlemesinde doğrulandı. SecureStore, klavye ve platform farkları cihazda ayrıca denenmeli.
- Karar motoru (kategori/öncelik önerisi), `decisions` ve `model_calls` tabloları, Jev/LLM adaptörleri, benchmark: Aşama 2–4. Hiçbir model ölçümü yapılmadı; ücretli çağrılar kapalı. Şu an kategori/öncelik/ekibi yalnızca yönetici belirler.
- Mobilde bileşen/ekran testleri yok (yalnızca mantık testleri); ekranlar elle ve tarayıcıda doğrulandı. Yük/performans ölçümü yapılmadı.

## Sınırlamalar ve açık konular

- Giriş denemelerine hız sınırı/hesap kilidi yok (Aşama 5). Yenileme belirteci yok; token 8 saat geçerli.
- `httpx` → `httpx2` geçişi kullanıcı onayını bekliyor (DECISIONS D7); testlerde bir kullanımdan kalkma uyarısı görünüyor.
- `npm audit` mobil bağımlılıklarda 14 orta düzey uyarı bildiriyor (şablon/Expo geçişli bağımlılıkları). `npm audit fix --force` uyumu bozabileceği için çalıştırılmadı; Expo SDK güncellemeleriyle izlenecek.
- Şablonun getirdiği `.claude/settings.json` (Expo eklentisini etkinleştiriyordu) ve Expo'nun `LICENSE`/`README` dosyaları sahibinin onayı olmadan projeye alınmadı, silindi. `apps/mobile/AGENTS.md` (Expo'ya özgü yönergeler) incelendi ve tutuldu.
- Bağımlılık kilidi Windows'ta üretildi; deploy aşamasında hedef platformda yeniden üretilmeli (DECISIONS D4).
- Commit e-postası `emirhanfirat44@gmail.com`; GitHub hesabında doğrulanmış değilse commitler profile bağlanmaz.

## Sıradaki somut adım

Yönetici paneli (`apps/admin`, Vite + React + TypeScript): giriş, talep listesi (süzgeç), talep ayrıntısı + geçmiş, öncelik/kategori/eksik bilgi düzeltme, ekip ve görevli atama (kategoriye göre varsayılan ekip önerisiyle), kullanıcı ve ekip üyeliği yönetimi. Ardından Aşama 1 kapanır ve Aşama 2'ye (karar motoru sözleşmesi, `rule_based`, mock adaptör, kalıcı iş durumu) geçilir.
