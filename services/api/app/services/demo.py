"""Canlı demo (portföy demosu): ziyaretçi oturumları, tek denemelik Jev kararı ve veri saklama.

Bu modül, canlı demonun iş kurallarını toplar; karar motorunu KOPYALAMAZ: iş kaydı, kira ile alma,
A/B/C aşamaları ve talebe uygulama `services/decisions.py` ve `worker.py` içindeki mevcut kodla
yapılır.
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Ticket, User

# Süresi dolan ziyaretçileri tek seferde değil, sınırlı partilerle sil (istek içinde çalışırken
# gecikme ve bellek sınırlı kalsın).
PURGE_BATCH = 100


def purge_expired(db: Session, settings: Settings, now: datetime) -> int:
    """Saklama süresi (`demo_retention_hours`) dolan ZİYARETÇİ hesaplarını ve tüm verilerini siler;
    silinen hesap sayısını döndürür.

    Yalnızca `is_demo` bayrağı olan hesaplar silinir: gerçek kullanıcılar, seed hesapları ve yerel
    E2E kayıtları (bayrak False) HİÇBİR koşulda silinmez. Talepler silinince olaylar, karar işleri,
    kararlar, model çağrıları ve demo istekleri veritabanı düzeyinde (CASCADE) silinir; bütçe
    kayıtları kalır (kişisel veri/metin içermez, yalnızca tutarlar) ve işe bağlantısı boşalır.
    """
    cutoff = now - timedelta(hours=settings.demo_retention_hours)
    ids = list(
        db.scalars(
            select(User.id)
            .where(User.is_demo.is_(True), User.created_at < cutoff)
            .order_by(User.created_at)
            .limit(PURGE_BATCH)
        )
    )
    if not ids:
        return 0
    db.execute(delete(Ticket).where(Ticket.created_by_id.in_(ids)))
    db.execute(delete(User).where(User.id.in_(ids), User.is_demo.is_(True)))
    db.commit()
    return len(ids)
