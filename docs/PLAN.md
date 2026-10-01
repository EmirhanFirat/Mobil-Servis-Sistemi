# TalepAkış — uygulama planı

Son güncelleme: 2026-10-01. Kalıcı çalışma kuralları `AGENTS.md` içindedir; güncel durum `STATUS.md`, kararların gerekçesi `DECISIONS.md` içindedir.

## Hedef

Kampüs/yurt bakım ekibi için mobil servis talebi ve iş yönlendirme uygulaması (tek kurum). Kullanıcı metinle talep açar; karar motoru kategori, öncelik ve eksik bilgiyi önerir; atama deterministik kurallarla yapılır.

Araştırma sorusu: Türkçe servis taleplerinde Jev, ekonomik bir LLM ve hibrit yaklaşım arasında doğruluk, işlem süresi ve maliyet nasıl değişiyor? Sonuç ne çıkarsa çıksın dürüstçe raporlanır.

Kapsam dışı (ilk sürüm): ses, fotoğraf/OCR, push bildirim, WhatsApp, ödeme, rota optimizasyonu, otonom agent sürüsü, Kubernetes, çok kiracılı SaaS. Bunlar ürün tamamlandıktan sonra ayrı öneri olarak ele alınır.

## Ortam (2026-10-01'de kontrol edildi)

| Araç | Durum |
|---|---|
| Git 2.52, kimlik tanımlı | kullanılıyor |
| Python 3.12.7 ve 3.14.2 | API için 3.12 seçildi (bkz. DECISIONS D2) |
| Node 24.15, npm 12.0.2 | mobil/yönetici paneli için |
| Docker Desktop 4.83 | kurulu; kapalıysa uygulamayı elle başlatmak gerekir (açılması birkaç dakika sürebilir). `postgres:17` kapsayıcısı doğrulandı |
| `psql`, `uv`, `pnpm` | yok; gerekmiyor |

## Aşamalar

Her aşama çalışan bir dikey dilimdir; bitince doğrulanır ve yerel commit atılır.

**Aşama 0 — Ortam, plan, kalıcı talimatlar.** `AGENTS.md`, README, belgeler, `.gitignore`, FastAPI iskeleti ve `/health`, kilitli bağımlılıklar, ilk commit. Bitiş: testler ve lint geçiyor, sunucu gerçekten ayağa kalkıp `/health` yanıtlıyor.

**Aşama 1 — AI olmadan ürün.** Giriş ve roller (talep sahibi, teknik görevli, yönetici), talep açma/listeleme/ayrıntı, görevli kuyruğu, rol bazlı durum geçişleri, olay geçmişi (audit), seed verisi, Alembic migration'ları, mobil ekranlar ve sade yönetici paneli. Bitiş: seed ile uçtan uca akış çalışıyor; başka kullanıcının talebine erişim engelleniyor (testli); yükleniyor/boş/hata/yetkisiz durumları ele alınmış.

**Aşama 2 — Karar motoru.** Ortak karar sözleşmesi, `rule_based` yöntem, deterministik mock adaptör, kalıcı iş durumu (DB tabanlı worker/polling), hata ve sınırlı retry davranışı. Bitiş: sağlayıcı hatasında talep korunuyor; yeniden işleme çift atama/olay üretmiyor.

**Aşama 3 — Gerçek modeller.** Jev ve ekonomik LLM adaptörleri (belge ve fiyat doğrulamasıyla), hibrit yönlendirme, kullanıcının onayladığı bütçeyle küçük canlı test. Bitiş: sağlayıcı değiştirmek ürün kodunu yeniden yazdırmıyor.

**Aşama 4 — Ölçüm ve benchmark.** Veri seti sürümleme, etiketleme rehberi, token/ücret/süre kayıtları, adil değerlendirme scripti, Markdown rapor, yönetici metrik ekranı. Mock ve gerçek sonuçlar ayrı. Bitiş: kayıtlı çıktılardan rapor model çağrısı olmadan yeniden üretilebiliyor.

**Aşama 5 — Yayına hazırlık.** Yapılandırma, migration, demo verisi, hata yönetimi, secret kontrolü, kurulum/deploy yönergesi, demo senaryosu. Deploy platformu ve maliyet kullanıcıyla netleştirilmeden yayın yapılmaz.

## Açık riskler

- Docker Desktop kendiliğinden açılmaz; testler PostgreSQL'e bağlı çalışacaksa önce kapsayıcının ayakta olması gerekir. Worker kilitleri gibi PostgreSQL'e özgü davranış gerçek PostgreSQL üzerinde test edilecek.
- Jev API şeması, model kimliği ve fiyat bilgisi Aşama 2–3'te resmî belgeden yeniden doğrulanacak; şimdiki bilgi yok sayılmamalı ama varsayılmamalı.
- Expo SDK ve Node uyumu Aşama 1'de mobil iskelet kurulurken resmî belgeden doğrulanacak.
