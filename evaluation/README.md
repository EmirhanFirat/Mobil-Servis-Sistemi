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

Seçenekler: `--strategies rule_based,mock_jev,...`, `--shuffle-seed N`, `--out <klasör>`. Test bölümü yalnızca nihai rapor içindir: `--splits test --final` gerekir; bayrak olmadan çalıştırma reddedilir (ayarları test sonucuna bakarak değiştirmemek için).

Varsayılan stratejiler (ücretsiz, ağ isteği yok): `rule_based` (gerçek taban) ve `mock_jev`, `mock_llm`, `mock_hybrid` (**mock**).

## Gerçek (ücretli) çalıştırma

Gerçek stratejiler `jev_only`, `llm_only` (Claude Haiku 4.5) ve `hybrid` **varsayılan listede yoktur**; yalnızca `--strategies` ile açıkça istenir ve şunların hepsi gerekir:

1. **Toplam harcama sınırı:** `--max-cost-usd <tutar>` (pozitif; yoksa komut reddedilir, hiçbir şey kurulmaz veya yazılmaz).
2. **Ücretli çağrılar açık** ve **anahtarlar tanımlı**: yalnızca o oturumun ortam değişkenleri olarak (PowerShell: `$env:TALEPAKIS_PAID_MODEL_CALLS_ENABLED = "true"`, `$env:TALEPAKIS_JEV_API_KEY = "..."`, `$env:TALEPAKIS_ANTHROPIC_API_KEY = "..."`). Anahtarı dosyaya, depoya veya sohbete yazma. Standart `ANTHROPIC_API_KEY` bilerek okunmaz.

```powershell
# Önce yaklaşık ücreti gör (ağ isteği yapmaz, anahtar gerekmez):
.\.venv\Scripts\python.exe -m app.evaluation plan --splits dev,val

# Sonra, sınırı kendin koyarak çalıştır:
.\.venv\Scripts\python.exe -m app.evaluation run --splits dev,val --strategies jev_only,llm_only,hybrid --max-cost-usd 1.00
```

Sınır nasıl uygulanır: örnek sınırında denetlenir; bir sonraki örneğin (şimdiye dek görülen en pahalı örnek kadar) ücreti sınırı aşacaksa durulur. Böylece tüm stratejiler aynı örnekleri tamamlamış olur ve aşım yalnızca beklenenden pahalı bir örnekle (ör. çok retry) olabilir; en çok bir örneğin ücreti kadardır. Maliyeti hesaplanamayan bir model yanıtı (kullanım bildirilmedi) sınırı garanti edilemez kıldığı için çalıştırmayı durdurur. Ağ/HTTP hata denemelerinin (zaman aşımı, 5xx, 429) sunucu tarafı ücreti bilinemez; takibe girmez ama raporda "bilinmiyor" olarak görünür. Durma nedeni, tamamlanan örnek sayısı ve toplam bilinen harcama `run.json`'a ve rapora yazılır; yarıda kalan çalıştırma raporda açıkça uyarılır ve yalnızca tüm stratejilerin tamamladığı örnekleri sayar. Ctrl+C ve beklenmeyen hata da kayıt bırakır.

`plan` çıktısı bir **tahmindir**, ölçüm değildir (girdi token'ı gövde uzunluğunun 1/3'ü, LLM çıktısı tipik 160 token); gerçek ücret yanıtlardaki kullanımdan hesaplanır ve sınır ona göre uygulanır.

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
