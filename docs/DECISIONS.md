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

## D15 — Mobil: Expo Router, bağımlılıksız durum yönetimi (2026-10-01)

Expo SDK 57 (React Native 0.86, resmî belgeden doğrulandı; Node ≥ 22.13, bizde 24). Gezinme Expo Router: korumalı rotalar (`Stack.Protected`) oturuma göre giriş/ana ekranı seçer. Bu yönlendirme yalnızca kolaylıktır; erişimi sunucu denetler. Durum yönetimi için ek kütüphane (Redux, React Query) yok: oturum bir React bağlamı, ekran verisi küçük bir `useResource` kancası (ilk yükleme, aşağı çek-yenile, ekran öne gelince sessiz yenileme, süzgeç değişince baştan yükleme). Simge kütüphanesi eklenmedi (sekmeler metin etiketli); bağımlılık sayısı bilerek düşük.

## D16 — İstemci izin kararı vermez (2026-10-01)

Ayrıntı ekranındaki işlem düğmeleri, sunucunun döndürdüğü `allowed_transitions`'tan çizilir; istemcide rol/durum kuralı yoktur (kural tek yerde: `domain/workflow.py`). İstemci yalnızca düğme adlarını Türkçeleştirir. Kuralların senkron kalması için `actions.test.ts` sunucudaki geçiş tablosunun bir kopyasıyla her geçişin okunur bir etiketi olduğunu doğrular. Onay adımı satır içidir; `Alert.alert` web'de çalışmadığı için kullanılmadı. Ham sunucu hata metinleri (5xx) kullanıcıya gösterilmez.

## D17 — Mobilin doğrulama yolu: Expo web önizlemesi (2026-10-01)

Bu geliştirme ortamında telefon veya emülatör yok. Mobil kod `react-native-web` ile tarayıcıda çalıştırılıp gerçek API'ye karşı uçtan uca denendi (giriş, liste, süzgeç, ayrıntı, işlemler, yeni talep, 401 ve bağlantı hatası durumları). Bu, gerçek cihaz testinin yerini tutmaz: SecureStore, klavye davranışı ve platform farkları cihazda ayrıca denenmelidir. Koordinatla tıklama bu tarayıcı bölmesinde güvenilmez olduğu için gezinme DOM tıklamasıyla, metin girişi gerçek klavye yazımıyla yapıldı.

## D18 — Yönetici paneli: Vite + React, mobille aynı kalıplar (2026-10-02)

Vite 8.3 + React 19 + React Router, ek durum yönetimi/arayüz kütüphanesi yok (düz CSS, açık/koyu tema). Mobildeki kalıplar korundu: sunucu izin kararı verir (`allowed_transitions`, `can_assign`, `can_edit`), istemci yalnızca sunar; satır içi onay; ham 5xx metni gösterilmez. Panel yalnızca yönetici rolüne açıktır: yönetici olmayan hesabın token'ı hiç saklanmaz (bu istemci tarafı kontrol yalnızca kolaylıktır; yönetim uçlarını sunucu zaten 403 ile reddeder). Token `sessionStorage`'dadır (sekme kapanınca silinir, `localStorage`'dan kısa ömürlü); bu XSS'e karşı koruma değildir, bu yüzden metinler hiçbir yerde HTML olarak basılmaz (React kaçışlar) ve yayında içerik güvenlik politikası eklenecek (Aşama 5).

Ekip önerisi: atama formu, talebin kategorisinin varsayılan ekibini ön seçer (sözlükteki tek kaynak `category_default_team`); ekip ile kategori birbirinden bağımsız tahmin edilmez. Yönetici değiştirebilir; ekip değişince görevli seçimi sıfırlanır (görevli seçilen ekibin üyesi olmalı).

Bilinçli tekrar: API tipleri, olay cümleleri ve işlem etiketleri mobil ve panelde ayrı kopyalardır. Ortak paket (monorepo çalışma alanı) bu ölçekte (iki küçük istemci) kurulum maliyetine değmedi; sapma riski testlerle sınırlı (sunucudaki geçiş tablosunun kopyası her iki istemcide de her geçişin okunur bir etiketi olduğunu doğrular). Üçüncü bir istemci veya ilk sapma olursa ortak pakete geçilir.

## D19 — Karar sözleşmesi (2026-10-02)

Dört strateji aynı sözleşmeye uyar (`app/decision/contract.py`). Her soru **tek bir yargıdır**: kategori, öncelik ve her eksik bilgi türü ayrı sorulur; kategori/öncelik kapalı seçenekli ve her zaman "belirsiz" seçeneği içerir (model zorla sınıflandırılmaz, belirsizlik insana gider). Sağlayıcıya özgü olasılık ve güven değerleri karar alanlarından **ayrı** `Judgment` kayıtlarında tutulur; tek bir "güven" alanı uydurulmaz. Güvenin türü açık işaretlenir: `jev_confidence` (Jev'in verdiği, seçenek sayısına bağlı), `derived_margin` (olasılıktan bizim türettiğimiz) ve `self_reported` (LLM'in yazdığı; kalibre değil). Bunlar birbirine eşdeğer sayılmaz. Bulunmayan değer `None`'dır.

Maliyet dürüstlüğü: her deneme (retry ve fallback dahil) ayrı `CallRecord`'dur. Sağlayıcı kullanım bildirmezse maliyet **bilinmez** (`None`), sıfır sayılmaz; toplam bilinmeyen çağrı varsa `None` döner ve bilinen kısım ile bilinmeyen çağrı sayısı ayrı verilir. "Çıktı ücretsiz" çıktı token'ının kaydedilmeyeceği anlamına gelmez. Fiyatlar tarihli, kaynaklı ve `Decimal`'dir (`pricing.py`).

## D20 — Güvenlik kapısı, enjeksiyon şüphesi ve yönlendirme deterministiktir (2026-10-02)

Tüm stratejilerin ortak son adımı (`assemble.py`) kodla çalışır: (1) **güvenlik kapısı**: metinde tehlike ifadesi (yangın, kıvılcım, gaz kokusu, elektrik çarpması...) varsa öncelik en az "yüksek" olur ve karar insan incelemesi ister; (2) **enjeksiyon şüphesi**: modeli yönlendirmeye çalışan ifade ("önceki talimatları yok say", "kategoriyi ... seç") görülürse insan incelemesi; (3) engelleyici eksik bilgi (konum, açıklama) insan incelemesi. Bu kurallar strateji ne derse desin uygulanır, böylece karşılaştırma adil kalır ve can güvenliği kararı modele bırakılmaz. Liste geniştir ama garanti değildir; arayüzde her zaman "112'yi ara" uyarısı vardır. Ekibe yerleştirme (`routing.py`) de kuraldır: karar inceleme gerektiriyorsa `needs_review`, aksi halde kategorinin varsayılan ekibinin kuyruğu; görevli seçimi insanındır ve model çıktısı hiçbir yetki vermez.

## D21 — Hibrit: sessiz sağlayıcı değişimi yok (2026-10-02)

Hibrit önce Jev'e tüm soruları sorar; yalnızca Jev'in **yanıtladığı ama güvenmediği** sorular LLM'e gider (maliyet için). LLM da "belirsiz" derse soru çözülmemiş sayılır ve karar insana gider. Jev çağrısı sınırlı retry'dan sonra da başarısızsa LLM'e **geçilmez**: görünür hata (`DecisionUnavailable`) fırlar; sağlayıcı kesintisi belirsizlik değildir. LLM ikinci aşaması başarısız olursa Jev'in güvenli yanıtları korunur, kalanlar için `llm_unavailable` nedeniyle insan incelemesi istenir. LLM'in kendi yazdığı güven Jev güveniyle kıyaslanmaz (yalnızca isteğe bağlı bir çekimserlik kapısıdır). Jev eşikleri doğrulama kümesinde ayarlanır, test kümesinde değil.

## D22 — Jev'e ham HTTP ile bağlanılır (2026-10-02)

Resmî Python SDK `httpx2`'ye bağlı (bkz. D7: onay bekliyor). Adaptör, belgelenmiş `POST /v1/systemone` şemasına doğrudan konuşur; `docs/SAGLAYICILAR.md` bilgileri ve kaynaklarıyla tutar. Jev'in birincil eğitim dili İngilizcedir; Türkçe doğruluğu varsayılmaz, ölçülür.

## D23 — Jev adaptörü ve ücretli çağrı koruması (2026-10-02)

Adaptör belgelenmiş HTTP şemasına uyar ve **kendi başına ağ isteği yapmaz**: yalnızca örneği oluşturulup `classify` çağrılırsa istek atılır; örnek, ücretli çağrılar açık ve anahtar tanımlı değilse fabrikadan alınamaz (`TALEPAKIS_PAID_MODEL_CALLS_ENABLED=false` varsayılan). Anahtar yalnızca `Authorization` başlığındadır; kayıtlara, hata mesajlarına, `repr`'a girmez. Sunucu yanıt gövdesi (kullanıcı metnini yansıtabilir) hata kayıtlarına konmaz, yalnızca durum kodu. Kullanıcı metni yalnızca `state` verisidir; sorular sabittir ve her biri durumu veri olarak ele almasını söyler. Yanıt şeması sıkı doğrulanır (bilinmeyen seçenek, 1'e toplanmayan olasılık, aralık dışı değer → `schema_error`, yeniden denenir). `httpx` dev'den çalışma zamanı bağımlılığına alındı (`httpx2` kararı hâlâ açık, D7).

## D24 — Değerlendirme: önce DB'siz, dosya tabanlı, yeniden üretilebilir (2026-10-02)

Değerlendirme altyapısı veritabanına bağlı değildir: veri seti `evaluation/datasets/<sürüm>/` altında JSONL + manifest (sha256), çalıştırma çıktıları `evaluation/runs/` altında (Git'e girmez). `dataset_versions`/`evaluation_runs`/`predictions` tabloları yerine dosyalar seçildi: model çağrısı olmadan rapor yeniden üretilebilsin, depoda küçük kalsın ve DB olmadan çalışsın (gerekirse sonradan içe aktarılır). Veri seti **olay grupları** halinde bölünür (bir olayın yeniden yazımları aynı bölümde; sızıntı yok, testle sabit). Stratejilere yalnızca başlık/açıklama/konum gider, etiketler hiçbir zaman gitmez (yapısal olarak sınanır). Test bölümü yalnızca `--final` ile çalışır. Strateji sırası her örnekte döndürülür (sıra etkisi), eşzamanlılık 1 (tek istek gecikmesi; throughput ile karışmaz). Her çalıştırma kaynak commit SHA'sı (ve kirli ağaç bayrağı), veri sha256'sı, model/istem sürümleri, eşikler, fiyat tablosu ve yeniden deneme ayarlarını kaydeder. Mock sonuçları raporda zorunlu uyarıyla işaretlenir; gerçek ölçüm sayılmaz.

Bilinçli sınırlar: v1 sentetiktir, tek etiketleyicilidir ve kurallar aynı kişice yazıldığı için `rule_based` sonuçları iyimserdir; eksik bilgiden yalnızca `location`/`detail` değerlendirilir.

## D25 — Ekonomik LLM: Claude Haiku 4.5, ham HTTP, zorunlu araç çağrısı (2026-10-02)

"Ekonomik LLM" için Anthropic **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`, 1 / 5 USD) seçildi; adaptör `app/decision/llm_anthropic.py`. **Bu seçimi kullanıcıya sorarak değil, geri alınabilir bir varsayılan olarak ben yaptım** (soru kullanıcı tarafından geçildi): sağlayıcı değişirse yalnızca bu adaptör ve fiyat girdisi değişir, `Provider` arayüzü ve stratejiler aynı kalır. Haiku 4.5, Claude ailesinin en ucuzu ve zorunlu araç çağrısını destekleyen en ucuz modeldir (Sonnet 5.5 2/10 USD'dir ve zorunlu araç çağrısını reddeder).

Resmî SDK yerine ham HTTP (D22 ile aynı gerekçe): `anthropic 1.11.0` `httpx2` ve beş paket daha getirir ve D7 hâlâ açıktır; ayrıca SDK'nın gizli yeniden denemesi retry/maliyet kaydıyla çatışır. Yanıt, zorunlu `submit_judgments` aracıyla alınır ve sıkı doğrulanır; sorular Jev'le aynı metinden üretilir (adil karşılaştırma); kullanıcı metni yalnızca kullanıcı mesajında JSON verisi olarak gider; güven modelin kendi yazdığı sayıdır (`self_reported`). Risk: Haiku 4.5 en erken 15 Ekim 2026'da kullanımdan kalkabilir (60 gün önceden bildirimle); benchmark sonuçları model sürümü ve tarihle birlikte saklanır. Ayrıntı ve kaynaklar: `docs/SAGLAYICILAR.md`.

Ortak ham-HTTP yardımcıları (`http_common.py`: Retry-After, token okuma, durum eşleme, şema denetimi) Jev ve Anthropic adaptörlerince paylaşılır; 402 (faturalandırma) kimlik/hesap hatası, 504 zaman aşımı sayılır (yeniden denemesi sırasıyla yok/var).

## D26 — Gerçek stratejiler yalnızca zorunlu harcama sınırıyla çalışır (2026-10-02; sınırın uygulanış yöntemi D28 ile değişti)

`jev_only`, `llm_only` ve `hybrid` değerlendirme çalıştırıcısına kaydedildi ama varsayılan listede değildir; `--max-cost-usd` (pozitif) olmadan reddedilir, ücretli çağrılar kapalıysa veya anahtar yoksa strateji kurulamaz ve çıktı klasörü bile açılmaz. **Bu bölümdeki ilk uygulama (örnek sınırında denetim, ağ hatalarını takibe katmama) kesin sınır sağlamadığı için kaldırıldı; geçerli yöntem D28'dedir.** Yarıda kalan çalıştırma (sınır, Ctrl+C, hata) `run.json`'a durma nedeniyle ve harcamayla yazılır, raporda uyarıyla gösterilir ve yalnızca tüm stratejilerin tamamladığı örnekleri sayar. `plan` komutu ağ isteği yapmadan, açık varsayımlarla yaklaşık ücreti gösterir (tahmindir; sınır gerçek ücretlere göre uygulanır).

## D28 — Harcama sınırı çağrı başına muhafazakâr rezervasyonla uygulanır; D26'nın örnek sezgisi kaldırıldı (2026-10-02)

D26'daki yöntem ("bir sonraki örnek, şimdiye dek görülen en pahalı örnek kadar sürer") kesin sınır sağlamıyordu: daha uzun bir örnek, retry'lar veya maliyeti bilinmeyen çağrı sınırı aşabilirdi; ayrıca ağ/HTTP hata denemelerini bütçeye hiç katmayarak **belirsiz maliyeti ücretsiz sayıyordu**. Yerine `app/decision/budget.py`: HER sağlayıcı çağrısından ve her retry'dan önce o çağrının ücretinin kanıtlanabilir üst sınırı bütçeden rezerve edilir (`BudgetedProvider`); kalan bütçe yetmiyorsa istek **hiç gönderilmez** (`BudgetExhausted`: hata değil durma sinyali; yeniden denenmez, başka sağlayıcıya geçilmez). Çağrı bitince rezervasyon bırakılır ve gerçek ücret yazılır; **maliyeti bilinemeyen çağrı** (kullanım yok, ağ hatası, zaman aşımı, HTTP hatası, farklı model sürümü, beklenmeyen kesinti) **rezerve edilen en kötü durum bedeliyle sayılır**. Böylece `harcanan + rezerve ≤ sınır` her an korunur. Üst sınır: girdi = istek gövdesinin UTF-8 bayt sayısı (bir token en az bir bayttır) + sağlayıcıya özgü sabit ek (Anthropic'te zorunlu araç çağrısı için 588) + 256 token payı; çıktı = `max_tokens` (ücretli çıktıda; çıktı tavanı bilinmiyorsa veya fiyat yoksa çağrı reddedilir). Gerçek ücretin 2–3 katıdır; bilerek aşırı muhafazakârdır. Çalıştırıcı ayrıca her örneğe başlamadan önce o örneğin TÜM gerçek stratejilerdeki en kötü durum ücretini (her çağrı tüm deneme haklarını kullanır) karşılayabildiğini denetler; böylece stratejiler aynı örnekleri tamamlar. Bütçe karar ortasında biterse (ön denetim aşılmışsa) yarım karar tahmin sayılmaz, harcanan çağrılar `run.json` `aborted_prediction` içinde saklanır. `--limit N` ilk N örnekle (isteğe bağlı `--shuffle-seed`) küçük deneme yapar; `plan` aynı hesapla "en kötü" rakamı ve gereken en küçük sınırı gösterir.

**Hâlâ garanti edilemeyenler:** (1) fiyat tablosunun güncelliği (yanlış fiyat sınırı yanlış hesaplatır); (2) sağlayıcı faturasının yayımlanmış fiyat ve raporlanan kullanımla birebir örtüştüğü (önbellek, indirim, vergi, asgari ücret); (3) aynı anahtarın başka süreçte/araçta kullanımı; (4) bayt ≥ token varsayımı bayt düzeyli tokenizer'lar içindir — gerçek ücret rezervasyonu aşarsa (`bound_violations`) çalıştırma durur ve kayda geçer, ama o çağrının ücreti harcanmıştır (tespit edilir, önlenemez); (5) süreç çağrı ile kayıt arasında çökerse bellekteki sayaç ve `run.json` kaybolabilir. Bu yüzden sınır "kesin" değil, "bu varsayımlar altında kesin"dir.

## D27 — Karar hattı: kalıcı iş kuyruğu, ayrı worker, insan düzeltmesi korunur (2026-10-02)

Talep açılırken karar işi (`decision_jobs`) **aynı işlemde** kaydedilir; model veya worker çalışmasa da talep kaybolmaz. Ayrı bir süreç (`python -m app.worker`) işi veritabanından alır: `FOR UPDATE SKIP LOCKED` + kira (`locked_until`); çöken worker'ın işi kira dolunca yeniden alınır, hak (3) bitince iş başarısız sayılır ve talep `needs_review` olur. Bir iş üç aşamadır ve **model çağrısı sırasında satır kilidi tutulmaz**: (A) kısa okuma, (B) sağlayıcı çağrısı, (C) tek işlemde kayıt (talep satırı kilitlenir, uygunluk yeniden denetlenir, kira sahipliği doğrulanır). Aynı iş iki kez tamamlanamaz (kira + `decisions.job_id` tekilliği): çift olay ve çift atama yok. Bir talepte aynı anda en çok bir açık iş olabilir (kısmi tekil indeks).

Model kararı yalnızca talep **`new` ve hiçbir insan değişikliği yokken** (durum/ekip/görevli/alan olayı) uygulanır; uygulanırsa ekip kategoriden deterministik bulunur ve talep ekip kuyruğuna (`assigned`, görevlisiz) ya da `needs_review`'a gider — görevli seçimi insanındır. Uygulanmazsa karar yine `decisions`'a yazılır (`applied_outcome`: `skipped_not_new` / `skipped_human_edit`); talep değişmez. Talep zaten uygun değilse model hiç çağrılmaz. **İlk model kararı ve her çağrı denemesi (`model_calls`, maliyet dahil; NULL = bilinmiyor, sıfır değil) değişmez kayıtlardır**; insan düzeltmesi olay geçmişine yazılır ve otomatik "gerçek etiket" sayılmaz. Sağlayıcı kalıcı hatasında talep korunur, `needs_review` + görünür `decision_failed` olayı yazılır, başarısız denemelerin maliyeti saklanır; sessizce başka sağlayıcıya geçilmez.

Görünürlük: olay geçmişi (talep sahibi dahil herkes görür) yalnızca sistem eylemini yazar (`decision_applied`: strateji, mock mu, kategori, öncelik, durum, ekip). İnceleme nedenleri (enjeksiyon şüphesi, güvenlik terimleri), model/sağlayıcı sürümü, yargılar ve maliyet yalnızca **yönetici** yanıtındaki `decision` alanında döner (`TicketDetail.decision`; yetki sunucuda).

Sınırlar: worker şimdilik yalnızca ücretsiz stratejileri çalıştırır (`FREE_STRATEGY_NAMES`; ayar doğrulaması gerçek stratejileri reddeder, veritabanına elle yazılmış `llm_only` işi `UnknownStrategy` ile başarısız olur) — gerçek Jev/LLM ürün akışına, ürün için tasarlanmış bir harcama koruması olmadan bağlanmaz. Worker sağlayıcı çağrısı ile kayıt arasında çökerse o denemenin çağrı/maliyet kaydı kaybolur (ücretsiz stratejilerde etkisiz). Beklenmeyen hatalarda iş düzeyinde yeniden deneme 30 sn'den başlayan üstel beklemeyle (en çok 5 dk), yalnızca hata türü kaydedilir.

## Açık karar — D7: `httpx` ve `httpx2`

Starlette'in test istemcisi `httpx`'i artık kullanımdan kalkmış sayıyor ve `httpx2` öneriyor (Starlette kaynağı önce `httpx2`'yi içe aktarıyor; PyPI'da paket Pydantic gözetiminde, sürüm 2.13.1). Şimdilik `httpx==0.28.1` kilitli; testler geçiyor, yalnızca bir kullanımdan kalkma uyarısı görünüyor. `httpx2`'ye geçiş kullanıcı onayına bırakıldı: `requirements-dev.in` içinde `httpx` → `httpx2` ve `pip-compile` yeterli.
