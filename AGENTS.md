# TalepAkış — ajan talimatları

Bu dosya, projede çalışan tüm kodlama ajanları için kalıcı kuralların tek kaynağıdır. `CLAUDE.md` yalnızca buraya yönlendirir; kuralları iki yerde ayrı ayrı yazma.

## Proje

TalepAkış: bir kampüs/yurt bakım ekibi için mobil servis talebi ve iş yönlendirme uygulaması. Talepler metinle açılır; karar motoru kategori, öncelik ve eksik bilgiyi önerir; atama deterministik kurallarla yapılır. Araştırma sorusu: Türkçe servis taleplerinde Jev, ekonomik bir LLM ve hibrit yaklaşım arasında doğruluk, süre ve maliyet nasıl değişiyor? Jev'in kazanacağı varsayılmaz; sonuçlar dürüstçe ölçülür.

Yeni oturumda sırayla oku: bu dosya → `docs/STATUS.md` → `docs/PLAN.md` → `git log --oneline -20`. Belgelerdeki iddiaları mevcut kodla kontrol et; işi sıfırdan kurma.

## Kullanıcıyla çalışma biçimi

- Türkçe konuş. Önce değişikliğin amacını bir cümleyle söyle, sonra gerekli teknik ayrıntıyı ver. Satır satır ders anlatma; önemli kararların nedenini ve kullanıcıya etkisini açıkla.
- Büyük belirsizliklerde sor; rutin ve geri alınabilir uygulama kararlarında ilerle. Aşamalar arasında "devam edeyim mi?" diye sorma.
- Bir şeyin başarılı olduğunu yalnızca doğruladıysan söyle. Çalışmayan kontrolü, atlanan adımı ve mock sonuçlarını açıkça belirt.
- Önemli aşama raporu kısa olsun: ne çalışıyor, ne değişti, nasıl kontrol edildi, neyi henüz ölçmedik, commit kimliği, sıradaki adım.

## Ortam ve teknik yığın

- Windows 11 + PowerShell. Yol adında boşluk var (`Mobil Servis Sistemi`); komutlarda yolları tırnak içine al.
- Yığın: mobil `apps/mobile` (React Native + Expo + TypeScript), yönetici paneli `apps/admin` (React web), API `services/api` (Python 3.12 + FastAPI + SQLAlchemy + Alembic), veritabanı PostgreSQL (Docker), değerlendirme `evaluation/`, belgeler `docs/`.
- Mevcut çalışan kodu sırf yığın listesine uymak için yeniden yazma. Küçük proje için gereksiz servis ve soyutlama üretme.
- Global paket kurulumu ve makinede gereksiz değişiklik yapma. Python bağımsızlıkları `services/api/.venv` içinde, Node bağımsızlıkları proje içinde kurulur. Kilit dosyaları commitlenir.
- Python komutları: `services/api` içinde `.venv\Scripts\python.exe -m ...` (testler `pytest`, lint `ruff check .` ve `ruff format --check .`).
- Docker daemon kapalı olabilir; PostgreSQL için `docker compose` kullan, varsayma, önce `docker info` ile kontrol et.

## Mimari ilkeler

- Yetkilendirme backend'de uygulanır. Model çıktısı hiçbir zaman erişim yetkisi vermez. Atama, izin ve durum geçişleri deterministik kodla yönetilir.
- Talep kaydı model servisine bağlı olmaz: model çalışmasa da talep kaybolmaz. Model işleri kalıcı DB durumuyla ve ayrı worker/polling ile yürür; yeniden işlemede aynı atama veya olay tekrarlanmaz.
- Model kararı ile insanın nihai düzeltmesi ayrı kayıtlardır; ilk tahmin silinmez, değişiklik olay geçmişine yazılır. İnsan düzeltmesi otomatik "gerçek etiket" sayılmaz.
- Dört strateji aynı karar sözleşmesine uyar: `rule_based`, `llm_only`, `jev_only`, `hybrid`. Sağlayıcıya özgü olasılık/confidence alanları ayrı saklanır; olmayan güven değeri uydurulmaz; LLM'in yazdığı yüzde Jev güveniyle eşdeğer sayılmaz.
- Kullanıcı metni veri olarak ele alınır (prompt injection testi zorunlu). Sınırlı retry, görünür hata durumu; sessizce başka sağlayıcıya geçme. Tüm retry/fallback maliyetleri kaydedilir.
- API anahtarları yalnızca backend ortam değişkenlerinden okunur; mobil uygulamaya konmaz. Anahtar yoksa deterministik mock adaptör kullanılır ve arayüzde/raporda mock olduğu belirtilir. Mock sonuçları gerçek ölçüm olarak raporlanmaz.
- Fiyatlar tarihli yapılandırmada tutulur (kaynak, kontrol tarihi, birim: USD / 1 milyon token); Decimal kullanılır. Hibrit maliyet tüm çağrıların toplamıdır. Sağlayıcı usage vermiyorsa değer null/tahmin olarak işaretlenir.
- Jev belgeleri (https://docs.typesafe.ai/ ve /models) ilgili aşamada yeniden doğrulanır; belgeyle çelişen varsayım güncel gerçekle değiştirilip not düşülür.

## Bütçe ve dış işlemler

- Ücretli model çağrıları varsayılan olarak kapalıdır. Canlı test öncesi planlanan örnek sayısını ve yaklaşık ücreti göster, kullanıcıdan toplam harcama sınırını al; sınır içinde her istek için yeniden sorma. Sınırı aşacak iş veya yeni ücretli hizmet için yeniden konuş.
- API anahtarını sohbete veya repoya yazdırma; kullanıcıya güvenli ortam değişkeni yöntemini anlat.
- Ücretli servis satın alma, public deploy, remote oluşturma ve `git push` ayrıca yetkilendirilmeden yapılmaz. Yerel kodlama, test ve yerel commit için tekrar izin istenmez.
- Git kimliği tanımlı değilse ad/e-posta uydurma, global git ayarını değiştirme.

## Git ve commit kuralları

- Anlamlı, tek başına açıklanabilen, ilgili kontrolleri geçen bir gelişme tamamlandığında otomatik yerel commit at. Her commit için onay isteme.
- Commit sınırı örnekleri: çalışır proje iskeleti; yetkilendirmeyle talep akışı; karar motoru sözleşmesi; Jev adaptörü; hibrit yönlendirme; ölçüm altyapısı; benchmark; tamamlanmış hata düzeltmesi. Her dosya kaydında commit atma, projenin tamamını da tek dev committe toplama.
- Mevcut kapsam içindeki küçük iyileştirmeyi nedenini açıklayarak yapabilirsin. Yeni ürün özelliği veya büyük mimari değişikliği kendiliğinden ekleme.
- Her commit öncesi `git status`, `git diff` ve `git diff --cached` incele. Yalnızca bu görev kapsamında değiştirdiğin dosyaları stage et; körlemesine `git add .` kullanma. Kullanıcının önceden var olan, ilgisiz değişikliklerini sahiplenme.
- Commitlenmez: anahtarlar, `.env`, tokenlar, gerçek kişisel veri, yerel veritabanı dökümleri, `node_modules`, build çıktıları, özel model yanıtları. `.env.example` yalnızca sahte/boş değer içerir.
- Değişiklikle ilgili test/lint/typecheck/build kontrollerini çalıştır. Küçük doküman değişikliğinde tüm testleri tekrarlama. Başarısızlığı gizleme; ortam yüzünden çalışmayan kontrolü açıkça yaz. Bilinen kırık uygulama kodunu tamamlanmış aşama gibi commit etme.
- Mesajlar sade, doğal Türkçe olsun. `feat:`/`fix:` önekleri, emoji, reklam dili, "çeşitli iyileştirmeler", "update", "WIP" yok. Biçim: kısa somut başlık cümlesi; boş satır; ne değiştiğini ve nedenini anlatan 1–3 cümle (kullanıcının göreceği fark veya çözülen sorun; önemliyse çalıştırılan testin sonucu; çalıştırılmayan test yazılmaz).
- Çok satırlı mesajı güvenli bir geçici dosyada hazırlayıp `git commit --file` ile kullan; kabuğun özel karakterleri çalıştırmasına yol açan komut üretme.
- İş bitiminde kısa SHA ve commit başlığını bildir. Commit atılamadıysa atılmış gibi davranma; nedenini ve bekleyen dosyaları söyle.
- Kullanıcı istemeden `push`, force push, `reset --hard`, geçmiş yeniden yazma veya `amend` yapma. Kullanıcının commitlerini değiştirme. Hook/imza hatalarını `--no-verify` veya güvenlik ayarı değişikliğiyle atlama; nedenini çöz veya bildir.
- Commit geçmişi gerçek geliştirme akışını yansıtsın; geriye dönük tarih veya yapılmamış işi anlatan mesaj yok.

## Oturum devamlılığı

- `docs/STATUS.md`: mevcut durum, son doğrulamalar, sınırlamalar, sıradaki somut adım. İlgili commitin içine al; yalnızca son SHA'yı yazmak için ek commit zinciri oluşturma.
- `docs/DECISIONS.md`: anlamlı mimari kararlar, kısa gerekçeyle. Her küçük seçimi kaydetme.
- `docs/PLAN.md`: aşamalar ve bitiş ölçütleri. Her aşama çalışan bir dikey dilim olarak tamamlanır.
