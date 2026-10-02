"""Karar işi alanı: iş durumları, sonuçlar ve "insan değişikliği" kuralı.

Karar işi, talep açılırken AYNI veritabanı işleminde kaydedilir; model çalışmasa veya çökse de talep
kaybolmaz. Ayrı bir worker işi işler. Model kararı ile insanın düzeltmesi ayrı kayıtlardır: model
kararı yalnızca talep hâlâ "new" ve hiçbir insan değişikliği yokken talebe uygulanır; sonradan gelen
insan düzeltmesi model tarafından asla ezilmez.
"""

from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobOutcome(StrEnum):
    DECIDED = "decided"  # model kararı üretildi (uygulanıp uygulanmadığı Decision'da)
    SKIPPED_NOT_NEW = "skipped_not_new"  # model hiç çağrılmadı: talep artık 'new' değil
    SKIPPED_HUMAN_EDIT = "skipped_human_edit"  # model hiç çağrılmadı: insan alan düzeltmiş
    FAILED_PROVIDER = "failed_provider"  # sağlayıcı sınırlı retry'dan sonra yanıt vermedi
    FAILED_ERROR = "failed_error"  # beklenmeyen hata, iş denemeleri tükendi
    FAILED_WORKER_LOST = "failed_worker_lost"  # worker kayboldu, iş denemeleri tükendi


class ApplyOutcome(StrEnum):
    """Model kararının talebe uygulanıp uygulanmadığı."""

    APPLIED = "applied"
    SKIPPED_NOT_NEW = "skipped_not_new"  # model çalışırken talebin durumu 'new' olmaktan çıktı
    SKIPPED_HUMAN_EDIT = "skipped_human_edit"  # model çalışırken bir insan alan düzeltti


# Bir insanın talepte yaptığı değişiklikleri gösteren olay türleri. Bunlardan biri varsa model
# kararı talebe UYGULANMAZ (kayıtta kalır, yönetici görür).
HUMAN_CHANGE_EVENT_KINDS = frozenset(
    {"status_changed", "team_changed", "assignee_changed", "field_changed"}
)

# Üretimde kapalı ücretli çağrılarla çalışabilen (ağ isteği yapmayan) stratejiler. Worker şimdilik
# yalnızca bunları destekler: gerçek Jev/LLM stratejileri harcama koruması olmadan ürün akışına
# bağlanmaz.
FREE_STRATEGY_NAMES = ("rule_based", "mock_jev", "mock_llm", "mock_hybrid")
DECISION_OFF = "off"  # karar işi kaydetme
