# Bağımsız etiket incelemesi — örnek s023

Bu belge, bir bakım talebi örneği için **ikinci bir değerlendiricinin** bağımsız etiket önermesi içindir. Lütfen
yalnızca aşağıdaki metne ve rehber kurallarına bakarak karar verin. Başka kimsenin etiketini, bir modelin
tahminini veya örneğin diğer yazımlarını görmeniz gerekmez; bilerek gösterilmemiştir.

## Örnek

Bir kampüs/yurt bakım ekibine yazılmış talep. Karar sistemine verilen **tüm** bilgi şunlardır:

| Alan | Metin |
|---|---|
| Başlık | Asansör bozuk |
| Açıklama | Asansör kapısı kapanmıyor, kata gelince açılmıyor. |
| Konum | C Blok zemin kat |

(Başka bilgi yoktur: kullanıcı adı, saat, fotoğraf, ek konuşma yok.)

## Verilecek etiketler

1. **Kategori:** `electrical`, `plumbing`, `it_network`, `cleaning`, `other`, `unclear`
2. **Öncelik:** `low`, `normal`, `high`
3. **Eksik bilgi (yalnızca bu ikisi değerlendirilir):** `location` var mı eksik, `detail` var mı eksik; ikisi de eksik değilse "yok".
4. **İnceleme beklenir mi (`expected_review`):** doğru sistem davranışı, otomatik yerleştirme yerine insan incelemesi mi?

## Etiketleme rehberinden ilgili kurallar (olduğu gibi)

**Genel ilke.** Etiketler referans cevaptır, mutlak gerçek değildir. Önceliğe **anlatılan olgulara** bakılarak karar
verilir, "acil" kelimesine değil.

**Kategori** — talebin ana sorununa göre:

- `electrical`: priz, kablo, sigorta, aydınlatma/ampul, elektrik kesintisi, kıvılcım.
- `plumbing`: musluk, lavabo, klozet/rezervuar, gider tıkanıklığı, sızıntı, sıcak su, duş.
- `it_network`: internet, Wi-Fi, ağ erişimi, yazıcı, bilgisayar, hesap.
- `cleaning`: çöp, kirli alanlar, tuvalet/duş temizliği, hijyen.
- `other`: açıkça bir bakım sorunu ama yukarıdakilere girmiyor: asansör, kapı, pencere, mobilya, ısıtma/klima, böcek,
  gaz, yapısal sorun.
- `unclear`: tek bir kategori seçilemiyor. İki durum: (1) metin çok belirsiz, (2) birden çok bağımsız sorun var.
  Doğru sistem davranışı ikisinde de insan incelemesidir.

**Öncelik:**

- `high`: hasar yayılıyor (su koridora yayılıyor), güvenlik riski var (kıvılcım, gaz kokusu, mahsur kalma, tavan
  çökmesi), çok kişiyi etkiliyor veya temel hizmet yok.
- `normal`: olağan süre içinde giderilmesi gereken sorun (çalışmayan priz, kopan Wi-Fi, sıcak su yok, dolu çöp kutusu).
- `low`: küçük rahatsızlık, "acelesi yok" denmiş veya yalnızca kolaylık (toner bitti).
- Yanlış aciliyet iddiası: "ACİL!!!" yazılmış ama olgu küçük bir sorunsa etiket `normal` (veya olgu çok küçükse `low`).
- Can güvenliği ifadeleri (`hazard`) her zaman `high` ve `expected_review: true`.

**Eksik bilgi:**

- `location`: konum yok veya bulunamayacak kadar belirsiz (`-`, `?`, `burada`, `bilmiyorum`). `expected_review: true`.
- `detail`: açıklama çok kısa/anlaşılmaz ("bozuk", "çalışmıyor lütfen bakın"). `expected_review: true`.

**`expected_review: true` olan durumlar:** can güvenliği ifadesi, talimat enjeksiyonu şüphesi, çok sorunlu veya belirsiz
mesaj, engelleyici eksik bilgi (konum/açıklama). Bunların dışında `false`.

## Cevap formu (lütfen doldurun)

| Etiket | Sizin cevabınız |
|---|---|
| Kategori | |
| Öncelik | |
| Eksik bilgi (`location` / `detail` / yok) | |
| `expected_review` (`true` / `false`) | |

**Gerekçe (1–3 cümle; hangi rehber kuralına dayandınız):**

&nbsp;

**Rehber bu örnek için yeterli mi?** (☐ Evet, tek bir doğru etiket çıkıyor  ☐ Hayır, rehber belirsiz bırakıyor)

Hayırsa: belirsiz kalan nokta nedir, ve rehbere hangi cümleyi eklemek bunu çözerdi?

&nbsp;

**Kararınızdan ne kadar eminsiniz?** (☐ Çok emin  ☐ Makul emin  ☐ İkircikli)

Değerlendirici adı veya kodu: ______________  Tarih: ______________
