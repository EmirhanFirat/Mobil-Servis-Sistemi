# Değerlendirme (benchmark) altyapısı

Dört stratejinin (`rule_based`, `llm_only`, `jev_only`, `hybrid`) aynı Türkçe servis taleplerinde doğruluk, süre ve maliyetini karşılaştırmak için. **Bu klasör veri ve belge içerir; kod `services/api/app/evaluation/` altındadır.**

> **Durum (2026-10-02):** altyapı hazır ve mock sağlayıcılarla doğrulandı; gerçek stratejiler harcama sınırıyla çalıştırılabilir durumda (sahte HTTP ile test edildi). **Gerçek Jev ve LLM ile yalnızca 5 örneklik bir bağlantı denemesi yapıldı** (2026-10-02, bütçe kimliği `ilk-deneme`; ayrıntı `docs/STATUS.md`); bu bir doğruluk veya maliyet ölçümü değildir ve hiçbir sonuç öyle sunulmamalıdır. Mock sonuçları raporlarda açıkça işaretlenir.

## İçerik

| Yol | Ne |
|---|---|
| `datasets/v1/samples.jsonl` | 54 sentetik Türkçe talep (18 olay grubu × 3 yazım), etiketli |
| `datasets/v1/MANIFEST.json` | Sürüm, sha256 özeti, bölümler, etiket durumu |
| `LABELING_GUIDE.md` | Etiketleme kuralları ve yeni örnek ekleme prosedürü |
| `runs/` | Çalıştırma çıktıları (**Git'e girmez**) |

## Kullanım

`services/api` içinden (Docker veya veritabanı gerekmez):

```powershell
# Çalıştır: aynı örnekler, aynı sorular, tüm stratejiler. Çıktı: evaluation\runs\<kimlik>\
.\.venv\Scripts\python.exe -m app.evaluation run --splits dev,val

# Raporu kayıtlı çıktılardan üret (model çağrısı YAPMAZ, tekrar tekrar üretilebilir)
.\.venv\Scripts\python.exe -m app.evaluation report --run ..\..\evaluation\runs\<kimlik>
```

Seçenekler: `--strategies rule_based,mock_jev,...`, `--shuffle-seed N`, `--limit N` (ilk N örnek), `--out <klasör>`. Test bölümü yalnızca nihai rapor içindir: `--splits test --final` gerekir; bayrak olmadan çalıştırma reddedilir (ayarları test sonucuna bakarak değiştirmemek için).

Varsayılan stratejiler (ücretsiz, ağ isteği yok): `rule_based` (gerçek taban) ve `mock_jev`, `mock_llm`, `mock_hybrid` (**mock**).

## Gerçek (ücretli) çalıştırma

Gerçek stratejiler `jev_only`, `llm_only` (Claude Haiku 4.5) ve `hybrid` **varsayılan listede yoktur**; yalnızca `--strategies` ile açıkça istenir ve şunların hepsi gerekir:

1. **Toplam harcama sınırı ve bütçe kimliği:** `--max-cost-usd <tutar>` ve `--budget-id <ad>`. Sınır, **aynı bütçe kimliğiyle yapılan TÜM çalıştırmaların toplamıdır** ve süreçler arası diskte (`evaluation/budget/<ad>.json`, Git'e girmez) tutulur: süreç yeniden başlarsa önceki harcama ve çözülmemiş rezervasyonlar düşülür, yeni bir sınır açılmaz. Sınır deftere ilk açılışta yazılır; farklı bir sınırla açmak reddedilir (kendiliğinden artırma yok). Kimlik veya sınır yoksa komut reddedilir, hiçbir şey kurulmaz veya yazılmaz.
2. **Ücretli çağrılar açık** ve **anahtarlar tanımlı**: yalnızca o PowerShell oturumunun ortam değişkenleri olarak (aşağıdaki gizli giriş). Anahtarı dosyaya, depoya veya sohbete yazma. Standart `ANTHROPIC_API_KEY` bilerek okunmaz.

### Anahtarları güvenle tanımlama (PowerShell, anahtar ekrana ve geçmişe girmez)

Anahtarı **hiçbir zaman komut satırına yapıştırma**: yapıştırdığın satır ekrana, kaydırma belleğine ve `ConsoleHost_history.txt`'e düz metin olarak girer. Önce `Read-Host` komutunu çalıştır, **istem geldikten sonra** yapıştır (yazarken görünmez):

```powershell
$k = Read-Host "Anthropic API anahtari" -AsSecureString
$env:TALEPAKIS_ANTHROPIC_API_KEY = [System.Net.NetworkCredential]::new('', $k).Password; Remove-Variable k

$j = Read-Host "Jev API anahtari" -AsSecureString
$env:TALEPAKIS_JEV_API_KEY = [System.Net.NetworkCredential]::new('', $j).Password; Remove-Variable j
```

Değişkenler yalnızca o pencerede yaşar; pencere kapanınca silinir. Panonu temizle (başka bir şey kopyala). Yalnızca tanımlı olup olmadığına bakmak için `python -m app.evaluation preflight ...` kullan (değer yazdırmaz). Anahtarın bir yerde düz metin göründüyse **hemen iptal edip yenisini oluştur** (Anthropic: Console → Settings → API keys).

### Çalıştırma sırası

```powershell
# 1) Ön kontrol: ağ isteği yapmaz, anahtar DEĞERİNİ yazdırmaz; anahtar/bayrak durumu, model ve fiyatlar,
#    bütçe defteri (önceki harcama dahil), seçilen örnekler, maliyet planı ve çalıştırılacak komutu gösterir.
.\.venv\Scripts\python.exe -m app.evaluation preflight --splits dev --shuffle-seed 4 --limit 5 --max-cost-usd 0.10 --budget-id ilk-deneme

# 2) Ücretli çağrıları bu pencerede aç (yalnızca ön kontrol "HAZIR" derse):
$env:TALEPAKIS_PAID_MODEL_CALLS_ENABLED = "true"

# 3) Çalıştır (nihai test bölümü kullanılamaz; yalnızca dev, açıkça 5 örnek):
.\.venv\Scripts\python.exe -m app.evaluation run --splits dev --shuffle-seed 4 --limit 5 --strategies jev_only,llm_only,hybrid --max-cost-usd 0.10 --budget-id ilk-deneme

# 4) Sonuç: örnek bazında ayrıntı (beklenen etiket, tahmin, token, süre, retry, ücret) ve defter durumu
.\.venv\Scripts\python.exe -m app.evaluation detail --run ..\..\evaluation\runs\<kimlik>
.\.venv\Scripts\python.exe -m app.evaluation budget --budget-id ilk-deneme
```

**Sınır nasıl uygulanır (çağrı başına muhafazakâr rezervasyon + kalıcı defter, `app/decision/budget.py`, `budget_ledger.py`, DECISIONS D28/D29):** her sağlayıcı çağrısından ve her retry'dan önce o çağrının ücretinin üst sınırı bütçeden rezerve edilir ve **çağrıdan önce diske yazılır**; kalan bütçe (sınır − önceki harcama − çözülmemiş rezervasyonlar − bu çalıştırma) yetmiyorsa istek **hiç gönderilmez** ve çalıştırma durur. Çağrı bitince rezervasyon bırakılır ve gerçek ücret yazılır. **Maliyeti bilinemeyen çağrı ücretsiz sayılmaz**: kullanım bildirilmediyse, ağ hatası/zaman aşımı/HTTP hatası olduysa veya farklı bir model sürümü yanıtladıysa rezerve edilen en kötü durum bedeliyle sayılır. Süreç bir çağrının ortasında çökerse o rezervasyon deftere `pending` kalır ve sonraki çalıştırmada **çözülmemiş rezervasyon** olarak en kötü bedelle bütçeden düşülür (gerçek harcamadan ayrı raporlanır). Aynı anda tek süreç yazabilir (kilit dosyası); çöken süreçten kalan kilit **otomatik silinmez**, kullanıcıya bildirilir. Üst sınır: girdi = istek gövdesinin UTF-8 bayt sayısı (bir token en az bir bayttır) + sabit ek + pay; çıktı = `max_tokens`; gerçek ücretin 2–3 katıdır, bilerek aşırı muhafazakârdır. Her örneğe başlamadan önce o örneğin tüm gerçek stratejilerdeki en kötü durum ücreti de karşılanabilmelidir; `plan`/`preflight` gereken en küçük sınırı gösterir.

**Hızlı durdurma (devre kesici):** sistematik bir hata bütçeyi boşuna yakmasın diye gerçek çalıştırmalar şu durumlarda hemen durur ve nedenini kaydeder: bir sağlayıcı kalıcı bir istemci hatası döndürürse (401/402/403 yanlış anahtar veya yetki, 400/413/422 hatalı istek) tek seferde (`provider_error`; o karar tahmin sayılmaz, harcanan çağrılar `run.json`'da saklanır), ya da aynı stratejinin ardışık iki kararı tüm denemelerine rağmen başarısız olursa (`provider_unavailable`; sağlayıcı kesintisi). Durdurulan çalıştırmanın harcaması deftere yazılmıştır ve düşülür; yeniden denemeden önce nedeni gider.

Bütçe yetmezse çalıştırma durur, o ana dek olan sonuçlar kaydedilir ve **bütçe kendiliğinden artırılmaz**. Durma nedeni, tamamlanan örnek sayısı, bu çalıştırmanın **gerçek ücreti**, **en kötü durum rezervasyonu**, önceki harcama ve çözülmemiş rezervasyonlar ayrı ayrı `run.json`'a ve rapora yazılır.

**Garanti edilemeyenler** (sınır bu varsayımlar altında kesindir): fiyat tablosunun güncelliği; sağlayıcı faturasının yayımlanmış fiyat ve raporlanan kullanımla birebir örtüşmesi (önbellek, indirim, vergi, asgari ücret); aynı anahtarın başka süreçte/araçta kullanımı (defter yalnızca bu çalıştırıcıyı bilir); bayt ≥ token varsayımı (gerçek ücret rezervasyonu aşarsa çalıştırma durur ve kayda geçer, ama o ücret harcanmıştır); defter dosyasının elle değiştirilmesi/silinmesi; diske yazılamayan bir rezervasyon çağrıyı durdurur (güvenli yönde).

`plan` çıktısı bir **tahmindir**, ölçüm değildir: "tipik" sütunu gövde uzunluğunun 1/3'ü kadar girdi token'ı ve tipik çıktıyla gerçekçi bir kestirimdir; "en kötü" sütunu bütçe korumasının gerçekte rezerve edeceği üst sınırdır. Küçük çalıştırmalarda (< 30 örnek) rapor "KÜÇÜK ÖRNEKLEM" uyarısı taşır ve ≤ 20 örnekte örnek bazında ayrıntı eklenir; birkaç örnekten genel doğruluk veya tasarruf sonucu çıkarılmaz.

## Çalıştırma başına kaydedilenler

- `predictions.jsonl`: her örnek × strateji için karar, sağlayıcıya özgü olasılık/güven sinyalleri, her çağrı (deneme, token, süre, maliyet, istek kimliği) ve uçtan uca gecikme.
- `run.json` (yeniden üretilebilirlik): kaynak commit SHA ve çalışma ağacının kirli olup olmadığı, veri seti sürümü ve sha256, strateji/model/istem sürümleri ve eşikler, fiyat tablosu (kaynak ve kontrol tarihi), yeniden deneme ve eşzamanlılık ayarları, zaman damgası.
- `report.md`, `metrics.json`: rapor ve makine okunur metrikler.

## Metrikler

Kategori doğruluğu ve macro-F1, kategori karışıklık matrisi, yüksek öncelik recall ve kaçırılan örnekler, inceleme (çekimserlik) oranı, **otomatik kararların doğruluğu** (incelemeye bırakılanlar başarı sayılmaz), inceleme kesinliği/duyarlılığı, eksik bilgi (konum/açıklama) F1, p50/p95 gecikme, hata oranı, toplam/karar başına/doğru otomatik karar başına USD, token ve çağrı sayıları. Oranlar için %95 Wilson güven aralığı verilir. Bilinmeyen maliyet sıfır sayılmaz.

## Önemli sınırlamalar

- Veri **sentetiktir** ve etiketler **tek kişiyce, gözden geçirilmeden** yazılmıştır; aciliyet etiketleri insan kontrolü bekliyor.
- Kural tabanı ve veri seti aynı kişi tarafından yazıldığı için `rule_based`'in dev/val sonuçları **iyimserdir**. Gerçek bir karşılaştırma için bağımsız etiketlenmiş, daha büyük ve (mümkünse) gerçek kullanımdan gelen bir veri gerekir (hedef 500–1000 örnek).
- Küçük örneklemde (v1: dev 21, val 15, test 18) farklar anlamlı sayılmamalıdır.
