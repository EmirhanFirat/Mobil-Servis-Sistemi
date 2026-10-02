# Etiket belirsizlikleri kaydı

Bu dosya, veri seti etiketlerinde **bağımsız ikinci değerlendirme bekleyen** belirsizlikleri kaydeder. Burada kayıtlı bir
kalem, etiketin yanlış olduğunun kanıtı değildir; yalnızca "tek kişinin kararı yeterince güvenilir görünmüyor" demektir.

## Kurallar

- **Mevcut sürümün (v1) etiketleri ve bunlarla alınmış geçmiş deney sonuçları geriye dönük değiştirilmez.**
  `evaluation/datasets/v1/` (özet: `MANIFEST.json`) ve `evaluation/runs/` altındaki kayıtlar olduğu gibi kalır.
- Bir etiket değişecekse bu, rehberin `LABELING_GUIDE.md` "Yeni örnek ekleme" kuralına göre **yeni bir veri seti
  sürümüyle** (v2) yapılır; v1 değişmez. Eski ve yeni sürümlerle alınan sonuçlar ayrı sürüm olarak raporlanır.
- **Model çıktısına bakarak etiket değiştirilmez.** Birkaç modelin etiketten aynı yönde ayrılması, etiketin yanlış
  olduğunu kanıtlamaz; karar, modellerin tahminini görmemiş bir değerlendiricinin rehbere göre yaptığı bağımsız
  değerlendirmeden gelir.
- Veri seti özeti (sha256) bu dosyayı eklemekle değişmez; bu dosya veri setinin parçası değildir.

## Açık kalemler

### s023 — "Asansör bozuk" (grup G08, `dev`)

- **Durum:** gözden geçirme bekliyor (kayıt tarihi 2026-10-02). Bağımsız değerlendirme metni:
  `evaluation/review/s023-bagimsiz-inceleme.md` (model tahmini ve mevcut etiket gösterilmeden hazırlandı).
- **Mevcut v1 etiketi:** kategori `other`, öncelik `normal`, eksik bilgi yok, `expected_review: false`.
- **Belirsizlik:** rehber `high` kapsamına "güvenlik riski var (… **mahsur kalma** …)" ve "temel hizmet yok" ifadelerini
  koyuyor; asansörü ise yalnızca `other` kategorisinde sayıyor ve asansör taleplerinin önceliği için ayrı bir kural vermiyor.
  s023'ün metni ("kapısı kapanmıyor, kata gelince açılmıyor") aynı grubun diğer iki yazımından farklı bir olgu anlatıyor:
  s022 ("iki gündür çalışmıyor, merdiven kullanıyoruz") ve s024 ("hiç tepki vermiyor, galiba bozuk") yalnızca asansörün
  çalışmadığını söylüyor ve `normal` etiketli; s023'te ise kabinin içindeki biri için kapının açılmaması gibi bir durum
  okunabilir. Yani grubun "aynı olayın üç yazımı" varsayımı bu örnekte metin düzeyinde tam tutmuyor olabilir.
- **Gözlem (kanıt değil):** ilk gerçek bağlantı denemesinde (5 örnek) üç strateji de bu örnekte öncelik için etiketten
  ayrıldı. Bu, etiket hakkında karar vermek için kullanılmaz; yalnızca belirsizliğin fark edilmesini sağladı.
- **Beklenen çıktı:** ikinci değerlendiricinin cevabı kaydedilir; (a) etiketi doğrularsa kalem kapanır, (b) farklı ise
  rehbere (asansör/mahsur kalma için) bir açıklama eklenip v2 hazırlanır ve G08'in üç yazımı birlikte yeniden değerlendirilir.
- **Etkilenen sonuçlar:** v1 ile alınmış tüm çalıştırmalar (şimdilik yalnızca `20261002T162249Z-v1-dev`) v1 etiketiyle
  yorumlanır ve öyle kalır.
