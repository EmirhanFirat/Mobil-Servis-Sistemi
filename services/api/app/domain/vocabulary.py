"""Alan sözlüğü: roller, durumlar, kategoriler, ekipler ve Türkçe görünen adları.

Kodlar kararlı ASCII değerleridir (veritabanı ve API bunları kullanır); Türkçe adlar yalnızca
gösterim içindir. Kategori ile ekip aynı sözlükten türer: ekip, kategoriden deterministik
olarak bulunur; bağımsız ve çelişebilen iki tahmin üretilmez.
"""

from enum import StrEnum


class Role(StrEnum):
    REQUESTER = "requester"
    TECHNICIAN = "technician"
    ADMIN = "admin"


class TicketStatus(StrEnum):
    NEW = "new"
    NEEDS_REVIEW = "needs_review"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class Category(StrEnum):
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    IT_NETWORK = "it_network"
    CLEANING = "cleaning"
    OTHER = "other"


class MissingInfo(StrEnum):
    LOCATION = "location"
    DETAIL = "detail"
    CONTACT = "contact"
    TIMING = "timing"


class TeamCode(StrEnum):
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    IT = "it"
    CLEANING = "cleaning"
    GENERAL = "general"


ROLE_LABELS = {
    Role.REQUESTER: "Talep sahibi",
    Role.TECHNICIAN: "Teknik görevli",
    Role.ADMIN: "Yönetici",
}

STATUS_LABELS = {
    TicketStatus.NEW: "Yeni",
    TicketStatus.NEEDS_REVIEW: "İnceleme bekliyor",
    TicketStatus.ASSIGNED: "Atandı",
    TicketStatus.IN_PROGRESS: "İşlemde",
    TicketStatus.RESOLVED: "Çözüldü",
    TicketStatus.CLOSED: "Kapatıldı",
}

PRIORITY_LABELS = {
    Priority.LOW: "Düşük",
    Priority.NORMAL: "Normal",
    Priority.HIGH: "Yüksek",
}

CATEGORY_LABELS = {
    Category.ELECTRICAL: "Elektrik",
    Category.PLUMBING: "Su/Tesisat",
    Category.IT_NETWORK: "İnternet/BT",
    Category.CLEANING: "Temizlik",
    Category.OTHER: "Diğer",
}

MISSING_INFO_LABELS = {
    MissingInfo.LOCATION: "Konum eksik",
    MissingInfo.DETAIL: "Açıklama yetersiz",
    MissingInfo.CONTACT: "İletişim bilgisi eksik",
    MissingInfo.TIMING: "Ne zaman başladığı belirtilmemiş",
}

TEAM_NAMES = {
    TeamCode.ELECTRICAL: "Elektrik Ekibi",
    TeamCode.PLUMBING: "Su/Tesisat Ekibi",
    TeamCode.IT: "BT Ekibi",
    TeamCode.CLEANING: "Temizlik Ekibi",
    TeamCode.GENERAL: "Genel Bakım Ekibi",
}

# Kategori → varsayılan ekip. Tek doğruluk kaynağı; ekip tahmini ayrıca yapılmaz.
CATEGORY_DEFAULT_TEAM = {
    Category.ELECTRICAL: TeamCode.ELECTRICAL,
    Category.PLUMBING: TeamCode.PLUMBING,
    Category.IT_NETWORK: TeamCode.IT,
    Category.CLEANING: TeamCode.CLEANING,
    Category.OTHER: TeamCode.GENERAL,
}
