# Değerlendirme (benchmark) altyapısı

Dört stratejinin (`rule_based`, `llm_only`, `jev_only`, `hybrid`) aynı Türkçe servis taleplerinde doğruluk, süre ve maliyetini karşılaştırmak için. **Bu klasör veri ve belge içerir; kod `services/api/app/evaluation/` altındadır.**

> **Durum (2026-10-02):** altyapı hazır ve mock sağlayıcılarla doğrulandı; gerçek stratejiler harcama sınırıyla çalıştırılabilir durumda (sahte HTTP ile test edildi). **Gerçek Jev veya LLM ile ölçüm henüz yapılmadı**; hiçbir sonuç gerçek model ölçümü olarak sunulmamalıdır. Mock sonuçları raporlarda açıkça işaretlenir.

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

1. **Toplam harcama sınırı:** `--max-cost-usd <tutar>` (pozitif; yoksa komut reddedilir, hiçbir şey kurulmaz veya yazılmaz).
2. **Ücretli çağrılar açık** ve **anahtarlar tanımlı**: yalnızca o oturumun ortam değişkenleri olarak (PowerShell: `$env:TALEPAKIS_PAID_MODEL_CALLS_ENABLED = "true"`, `$env:TALEPAKIS_JEV_API_KEY = "..."`, `$env:TALEPAKIS_ANTHROPIC_API_KEY = "..."`). Anahtarı dosyaya, depoya veya sohbete yazma. Standart `ANTHROPIC_API_KEY` bilerek okunmaz.

```powershell
# Önce yaklaşık ücreti gör (ağ isteği yapmaz, anahtar gerekmez). Küçük deneme: --limit N (+ çeşitlilik için --shuffle-seed)
.\.venv\Scripts\python.exe -m app.evaluation plan --splits dev --shuffle-seed 4 --limit 5

# Sonra, sınırı kendin koyarak çalıştır:
.\.venv\Scripts\python.exe -m app.evaluation run --splits dev --shuffle-seed 4 --limit 5 --strategies jev_only,llm_only,hybrid --max-cost-usd 0.10
```

**Sınır nasıl uygulanır (çağrı başına muhafazakâr rezervasyon, `app/decision/budget.py`, DECISIONS D28):** her sağlayıcı çağrısından ve her retry'dan önce o çağrının ücretinin üst sınırı bütçeden rezerve edilir; kalan bütçe yetmiyorsa istek **hiç gönderilmez** ve çalıştırma durur. Çağrı bitince rezervasyon bırakılır ve gerçek ücret yazılır. **Maliyeti bilinemeyen çağrı ücretsiz sayılmaz**: kullanım bildirilmediyse, ağ hatası/zaman aşımı/HTTP hatası olduysa veya farklı bir model sürümü yanıtladıysa rezerve edilen en kötü durum bedeliyle sayılır. Üst sınır: girdi = istek gövdesinin UTF-8 bayt sayısı (bir token en az bir bayttır) + sabit ek + pay; çıktı = `max_tokens`; yani gerçek ücretin 2–3 katıdır ve bilerek aşırı muhafazakârdır. Her örneğe başlamadan önce o örneğin tüm gerçek stratejilerdeki en kötü durum ücreti (her çağrı tüm deneme haklarını kullanır) karşılanabiliyor olmalıdır; böylece stratejiler aynı örnekleri tamamlar. `plan` bu en kötü rakamı ve **gereken en küçük sınırı** gösterir; daha küçük sınırda hiçbir çağrı gönderilmez.

Durma nedeni (`budget`, `estimate_violated`, `unbounded`, Ctrl+C, hata), tamamlanan örnek sayısı, toplam harcama (bilinen ve en kötü bedelle sayılan kısım ayrı) ve varsa bütçe nedeniyle yarıda kesilen karar (`aborted_prediction`) `run.json`'a ve rapora yazılır; yarıda kalan çalıştırma raporda açıkça uyarılır ve yalnızca tüm stratejilerin tamamladığı örnekleri sayar.

**Garanti edilemeyenler** (sınır bu varsayımlar altında kesindir): fiyat tablosunun güncelliği; sağlayıcı faturasının yayımlanmış fiyat ve raporlanan kullanımla birebir örtüşmesi (önbellek, indirim, vergi, asgari ücret); aynı anahtarın başka süreçte/araçta kullanımı; bayt ≥ token varsayımı (gerçek ücret rezervasyonu aşarsa çalıştırma durur ve kayda geçer, ama o ücret harcanmıştır); süreç çağrı ile kayıt arasında çökerse bellekteki sayacın ve `run.json`'un kaybı.

`plan` çıktısı bir **tahmindir**, ölçüm değildir: "tipik" sütunu gövde uzunluğunun 1/3'ü kadar girdi token'ı ve tipik çıktıyla gerçekçi bir kestirimdir; "en kötü" sütunu bütçe korumasının gerçekte rezerve edeceği üst sınırdır.
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
