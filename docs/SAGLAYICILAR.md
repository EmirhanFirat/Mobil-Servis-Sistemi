# Sağlayıcı notları (Jev ve ekonomik LLM)

Bu belge, resmî belgelerden doğrulanmış sağlayıcı bilgilerini ve kontrol tarihlerini tutar. Fiyat ve şema bilgisi zamanla değişir: **canlı deney öncesi yeniden doğrula** ve tarihi güncelle.

## Jev (TypeSafe) — doğrulama tarihi: 2026-10-02

Kaynaklar: https://docs.typesafe.ai/ (dizin: `/llms.txt`), `/models.md`, `/api.md`, `/primitives/choice.md`, `/confidence.md`, `/model-jaggedness/jev-1.13.md`, `/sdk/python/api/types/responses.md`.

| Konu | Doğrulanan bilgi |
|---|---|
| Uç nokta | `POST https://api.typesafe.ai/v1/systemone` (tüm modeller aynı uç nokta) |
| Kimlik | `Authorization: Bearer <API_KEY>`; SDK ortam değişkeni adı `TYPESAFE_API_KEY` |
| İstek | `{"state": <metin: string \| nesne \| dizi>, "model": "jev-latest", "questions": {ad: {type, instructions, criteria}}}`. Yalnızca metin kabul eder. |
| Model | `jev-1.13.0` (takma adlar `jev-latest` ve `jev-preview` aynı sürüme gider). Kayıtlarda **gerçek sürüm** tutulur, takma ad değil. |
| Fiyat | Girdi **0,042 USD / 1M token**; çıktı **ücretsiz** (çıktı token'ı yine de kaydedilir). Önbellek fiyatı belirtilmemiş. |
| Bağlam | İstek başına 64k token; `state` + en uzun soru için 32k |
| Hız sınırı | 100K token/sn ve 40 istek/sn (talebe göre dinamik) |
| Choice | `criteria`: seçenek→açıklama sözlüğü, en çok 255 seçenek. Yanıt: `choice`, `probabilities` (toplam 1), `confidence`. |
| Güven | `confidence = (p_max − 1/n) / (1 − 1/n)`: **seçenek sayısı n'ye bağlıdır**; farklı n'li sorular ve LLM'in yazdığı yüzde birbiriyle karşılaştırılamaz. |
| Noul (evet/hayır) | Yanıtta yalnızca `noul` (0–1 olasılık); ayrı `confidence` yoktur. Biz `\|2p − 1\|` kenar payını **kendimiz türetiriz** ve `derived_margin` olarak işaretleriz. |
| Çoklu soru | Aynı `state` için birden çok soru tek çağrıda sorulabilir ("tüm soru türleri tek çağrıda karıştırılabilir"). |
| Yanıt | `{"model", "answers", "usage": {"input_tokens", "output_tokens"}}`; başlık `x-typesafe-request-id`. SDK'da kullanım alanları `None` olabilir (bildirilmediyse). |
| Hatalar | 401 (anahtar), 422 (doğrulama), 429 (hız sınırı), 529 (aşırı yük). SDK varsayılan zaman aşımı 10 sn. |
| Belgeli sınırlılıklar | Soruyu yazıldığı gibi (literal) okur; sayma/sayısal işlem/tarih karşılaştırma zayıf; **gereksiz bağlam doğruluğu düşürür** (`state`'e yalnızca gerekeni koy); **düşmanca içerik yanıtı kaydırabilir**; farklı biçimli eşdeğer sorular tutarlı olmak zorunda değil; metin üretmek yavaştır. |
| Dil | Birincil eğitim dili **İngilizce** ve en iyi doğruluk orada. Türkçede doğruluk **ölçülmeden varsayılmaz**; bu projenin ölçtüğü şeylerden biridir. |

### Bu projedeki kararlar

- **Ham HTTP, SDK değil.** Resmî Python SDK var, ama `httpx2`'ye bağlı (bkz. DECISIONS D7: `httpx2` kullanıcı onayı bekliyor). Adaptör, belgelenmiş HTTP şemasına doğrudan konuşacak; böylece sağlayıcı kitaplığına bağımlılık yok.
- **Soru tasarımı:** kategori ve öncelik Choice (her biri "belirsiz" seçeneğiyle, 6 ve 4 seçenek), her eksik bilgi türü ayrı Noul. Altı soru tek çağrıda gider. Jev'den açıklama istenmez.
- **State:** yalnızca `title`, `description`, `location` (nesne olarak, adlandırılmış alanlar). Kullanıcı adı, kimlik ve geçmiş gönderilmez. Metin **veri olarak** taşınır, talimat olarak değil.
- **Güven eşikleri** doğrulama kümesinde ayarlanır (test kümesinde değil); başlangıç değerleri muhafazakârdır.

## Ekonomik LLM — henüz seçilmedi

Aşama 3'te, kullanıcının elindeki anahtar ve bütçeye göre belirlenecek. O zaman: model kimliği (takma ad değil gerçek sürüm), güncel fiyat ve kaynağı, kullanım alanları (önbellek/akıl yürütme dahil) resmî belgeden doğrulanıp bu belgeye eklenecek. LLM'in kendi yazdığı güven yüzdesi `self_reported` türündedir ve Jev güveniyle eşdeğer sayılmaz.
