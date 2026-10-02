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
- **Soru metni İngilizce**, talep metni Türkçe (Jev'in birincil dili İngilizce). Bu bir **hipotezdir**: Türkçe soru metninin daha iyi olup olmadığı deneyle bakılacak. Her sonuç, soru metninin özetini içeren `prompt_version`'la kaydedilir (`jev-sorular-v1-<özet>`), metin değişince sürüm kendiliğinden değişir.
- **Model sürümü sabitlenir** (`jev-1.13.0`, `jev-latest` değil); kayıtta yanıttaki gerçek sürüm tutulur. Yanıtlayan sürüm fiyatı doğrulanmış sürümden farklıysa maliyet bilinmez (`None`) sayılır.
- **Yeniden deneme:** 3 deneme (ilk + 2 yeniden), 0,5 sn'den 5 sn'ye üstel bekleme; 408/429/5xx ve şema hatası yeniden denenir, 401/403/400/422 denenmez; `retry-after-ms` ve `retry-after` başlıklarına uyulur. Resmî SDK varsayılanlarıyla uyumludur (2 yeniden deneme, 0,5–5 sn). Zaman aşımı 10 sn.
- **Durum:** adaptör (`app/decision/jev.py`) yazıldı ve `httpx.MockTransport` ile test edildi. **Gerçek Jev'e hiç istek atılmadı.** Ücretli çağrılar `TALEPAKIS_PAID_MODEL_CALLS_ENABLED` ve `TALEPAKIS_JEV_API_KEY` olmadan kurulamaz.

## Ekonomik LLM — Anthropic Claude Haiku 4.5 — doğrulama tarihi: 2026-10-02

Kaynaklar: https://platform.claude.com/docs/en/about-claude/pricing, `/about-claude/models/overview`, `/about-claude/model-deprecations`, `/api/errors`, `/api/messages`, `/agents-and-tools/tool-use/define-tools`.

| Konu | Doğrulanan bilgi |
|---|---|
| Uç nokta | `POST https://api.anthropic.com/v1/messages` |
| Kimlik | `x-api-key: <API_KEY>`, `anthropic-version: 2023-06-01`, `content-type: application/json` |
| Model | `claude-haiku-4-5-20251001` (takma ad `claude-haiku-4-5` aynı sürüme gider). Bağlam 200K, en çok 64K çıktı. Kayıtlarda **gerçek sürüm** tutulur. |
| Fiyat | Girdi **1 USD**, çıktı **5 USD** / 1M token (standart; önbellek okuması 0,10, toplu iş 0,50/2,50 kullanılmaz) |
| Yaşam döngüsü | Durum "Active", kullanımdan kaldırma duyurulmadı; taahhüt: **en erken 15 Ekim 2026'da** kalkabilir ve en az 60 gün önceden bildirilir. Yani model benchmark'tan sonra kalkabilir; yeniden üretilebilirlik için sonuçlar tam model sürümü ve tarihle birlikte saklanır. |
| Zorunlu araç çağrısı | `tool_choice: {"type":"tool","name":...}` Haiku 4.5'te çalışır. **Opus 5.5, Sonnet 5.5 ve Fable 5.1'de 400 döner**; bu modellere geçilirse yöntem değişmelidir (`auto` + `strict`). Zorunlu çağrıda model araçtan önce metin yazmaz. |
| Araç sistem istemi | Zorunlu araç çağrısında Haiku 4.5 için ek **588 token**, bildirilen girdi token'ına dahil olur (maliyet hesabında zaten sayılır). |
| Sıcaklık | Haiku 4.5 kabul eder (biz 0 veriyoruz). Claude 4.7 ve sonrasında varsayılan dışı değer **400** döner; o modellerde `temperature=None` verilir, alan hiç gönderilmez. |
| Kullanım | `usage.input_tokens`, `output_tokens` (+ `cache_creation_input_tokens`, `cache_read_input_tokens`). Önbellek kullanmıyoruz; yine de sıfırdan büyük önbellek token'ı bildirilirse girdi maliyeti **bilinmez** sayılır. |
| İstek kimliği | `request-id` yanıt başlığı (hata gövdesinde de `request_id`). |
| Hatalar | 400 `invalid_request_error` (harcama sınırı dolunca da), 401 `authentication_error`, 402 `billing_error`, 403 `permission_error`, 413 `request_too_large`, 429 `rate_limit_error`, 500 `api_error`, 504 `timeout_error`, 529 `overloaded_error`. Katman harcama sınırı 429'unda `retry-after` yoktur ve hata sürer; sınırlı retry bunu zaten kısıtlar. |
| Tokenizer | Haiku 4.5 önceki tokenizer'ı kullanır; Claude 4.7+ ve Jev farklı tokenizer kullanır. Token sayıları birebir karşılaştırılamaz (rapora yazılır). |

### Bu projedeki kararlar

- **Ham HTTP, SDK değil.** `pip install --dry-run anthropic` (2026-10-02): `anthropic 1.11.0` ile birlikte `httpx2`, `httpcore2`, `jiter`, `truststore`, `sniffio`, `docstring_parser` gelir; yani D7 (onay bekliyor) çözülmeden kurulamaz. Ayrıca SDK kendi yeniden denemesini yapar; burada retry ve maliyet kaydı bizim katmanda (`retry.py`) olmalı. İstenirse SDK'ya geçmek yalnızca `llm_anthropic.py`'yi değiştirir (`Provider` arayüzü sabit).
- **Yanıt, zorunlu `submit_judgments` aracıyla.** Altı soru tek çağrıda, her biri `{answer, confidence}`. Kategori ve öncelikte "belirsiz" seçeneği vardır. Araç şeması model için kılavuzdur, garanti değildir: yanıt sıkı doğrulanır (bilinmeyen seçenek, bool olmayan evet/hayır, aralık dışı veya eksik güven, kesilmiş yanıt, birden çok/yanlış araç çağrısı → `schema_error`, yeniden denenir ve ücreti sayılır).
- **Sorular Jev'inkiyle aynı metinden üretilir** (`jev_questions.py`): seçenekler ve açıklamalar birebir aynıdır; strateji farkı yalnızca "kim yanıtladı"dan gelir. Sorular ve çerçeve notu İngilizce, talep metni Türkçe.
- **Kullanıcı metni yalnızca kullanıcı mesajında**, `{"title","description","location"}` JSON nesnesi olarak (kaçışlanmış; ek mesaj veya araç tanımı üretemez). Sistem istemi ve araç şeması sabittir; kullanıcı adı, kimlik ve geçmiş gönderilmez. `prompt_version` = `llm-istem-v1-<özet>`; metin değişince kendiliğinden değişir.
- **Güven = modelin kendi yazdığı sayı** (`self_reported`); olasılık verilmez (`None`). Jev güveniyle karşılaştırılmaz.
- **Ayarlar:** sıcaklık 0, `thinking` yok, `max_tokens` 600 (yaklaşık 150 token gerekir), zaman aşımı 30 sn, otomatik retry yok; 3 deneme, 0,5–5 sn üstel bekleme, 429'da `retry-after`.
- **Anahtar:** yalnızca `TALEPAKIS_ANTHROPIC_API_KEY` ortam değişkeni ve `TALEPAKIS_PAID_MODEL_CALLS_ENABLED=true` birlikte. Standart `ANTHROPIC_API_KEY` **bilerek okunmaz**: başka araçlar için tanımlı bir anahtar bu projede kazara ücretli çağrı yapmasın. Hata mesajlarına sunucu gövdesi konmaz; yalnızca durum kodu ve sınırlı `error.type`.
- **Durum:** adaptör (`app/decision/llm_anthropic.py`, `llm_prompt.py`) yazıldı ve `httpx.MockTransport` ile test edildi. **Gerçek Anthropic'e hiç istek atılmadı**; gerçek modelin araç çağrısına uyma oranı, Türkçedeki doğruluğu ve gerçek token kullanımı **ölçülmedi**.
