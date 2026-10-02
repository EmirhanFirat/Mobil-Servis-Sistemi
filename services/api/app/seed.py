"""Yalnızca geliştirme için demo verisi: kullanıcılar, ekip üyelikleri ve örnek talepler.

Kullanım (services/api içinde):  .\\.venv\\Scripts\\python.exe -m app.seed
Üretim ortamında çalışmayı reddeder. Tekrar çalıştırmak güvenlidir: var olanı atlar.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_engine
from app.domain.vocabulary import Category, Priority, Role, TicketStatus
from app.models import Team, TeamMembership, Ticket, User
from app.schemas import AssignRequest, TicketCreate, TicketPatch
from app.security import hash_password
from app.services import tickets as svc

# Yalnızca yerel demo içindir; gerçek hesaplarda kullanma.
DEMO_PASSWORD = "demo-parola-123"

# (kullanıcı adı, görünen ad, rol, ekip kodu)
DEMO_USERS = [
    ("yonetici", "Zeynep Yönetici", Role.ADMIN, None),
    ("elektrik.usta", "Ahmet Elektrik", Role.TECHNICIAN, "electrical"),
    ("tesisat.usta", "Mehmet Tesisat", Role.TECHNICIAN, "plumbing"),
    ("bt.destek", "Elif BT", Role.TECHNICIAN, "it"),
    ("temizlik.gorevli", "Fatma Temizlik", Role.TECHNICIAN, "cleaning"),
    ("genel.bakim", "Ali Genel Bakım", Role.TECHNICIAN, "general"),
    ("ayse", "Ayşe Yılmaz", Role.REQUESTER, None),
    ("burak", "Burak Kaya", Role.REQUESTER, None),
]


def _user(db: Session, username: str) -> User:
    return db.scalars(
        select(User).options(selectinload(User.teams)).where(User.username == username)
    ).one()


def seed_users(db: Session) -> int:
    created = 0
    teams = {team.code: team for team in db.scalars(select(Team))}
    for username, display_name, role, team_code in DEMO_USERS:
        if db.scalar(select(User.id).where(User.username == username)) is not None:
            continue
        user = User(
            username=username,
            display_name=display_name,
            password_hash=hash_password(DEMO_PASSWORD),
            role=role,
        )
        db.add(user)
        db.flush()
        if team_code:
            db.add(TeamMembership(user_id=user.id, team_id=teams[team_code].id))
        created += 1
    db.commit()
    return created


def seed_tickets(db: Session) -> int:
    if db.scalar(select(Ticket.id).limit(1)) is not None:
        return 0
    admin = _user(db, "yonetici")
    ayse, burak = _user(db, "ayse"), _user(db, "burak")
    teams = {team.code: team for team in db.scalars(select(Team))}

    def open_ticket(
        owner: User,
        title: str,
        description: str,
        location: str,
        decision_strategy: str | None = None,
    ) -> Ticket:
        return svc.create_ticket(
            db,
            owner,
            TicketCreate(title=title, description=description, location=location),
            decision_strategy=decision_strategy,
        )

    # 1) Yeni, henüz yönlendirilmemiş: karar işi kuyrukta bekler (worker işleyince yönlendirilir:
    #    `python -m app.worker --once`). Diğer demo talepler elle düzenlendiği için iş açılmaz.
    open_ticket(
        ayse,
        "Lavabo akıtıyor",
        "B blok ikinci kattaki lavabo akıtıyor, su koridora yayılıyor.",
        "B Blok, 2. kat koridor",
        decision_strategy="rule_based",
    )

    # 2) Elektrik ekibine atanmış, yüksek öncelikli
    t2 = open_ticket(
        burak,
        "Prizden kıvılcım çıktı",
        "Odadaki prizden kıvılcım çıktı ve yanık kokusu var. Elektriği kapattım.",
        "A Blok, 114 numaralı oda",
    )
    svc.patch_ticket(
        db, admin, t2.id, TicketPatch(priority=Priority.HIGH, category=Category.ELECTRICAL)
    )
    svc.assign_ticket(
        db,
        admin,
        t2.id,
        AssignRequest(team_id=teams["electrical"].id, assignee_id=_user(db, "elektrik.usta").id),
    )

    # 3) BT ekibinde işlemde
    t3 = open_ticket(
        ayse,
        "Wi-Fi sürekli kopuyor",
        "Akşam saatlerinde yurt Wi-Fi bağlantısı sürekli kopuyor.",
        "C Blok, 3. kat",
    )
    svc.patch_ticket(db, admin, t3.id, TicketPatch(category=Category.IT_NETWORK))
    bt = _user(db, "bt.destek")
    svc.assign_ticket(db, admin, t3.id, AssignRequest(team_id=teams["it"].id, assignee_id=bt.id))
    svc.transition_ticket(
        db, bt, t3.id, TicketStatus.IN_PROGRESS, "Erişim noktasını kontrol ediyorum."
    )

    # 4) Çözülmüş, talep sahibinin onayını bekliyor
    t4 = open_ticket(
        burak,
        "Koridor çöp kutuları taştı",
        "Üçüncü kat koridordaki çöp kutuları iki gündür boşaltılmadı.",
        "A Blok, 3. kat koridor",
    )
    svc.patch_ticket(
        db, admin, t4.id, TicketPatch(priority=Priority.LOW, category=Category.CLEANING)
    )
    cleaner = _user(db, "temizlik.gorevli")
    svc.assign_ticket(
        db, admin, t4.id, AssignRequest(team_id=teams["cleaning"].id, assignee_id=cleaner.id)
    )
    svc.transition_ticket(db, cleaner, t4.id, TicketStatus.IN_PROGRESS, None)
    svc.transition_ticket(db, cleaner, t4.id, TicketStatus.RESOLVED, "Kutular boşaltıldı.")
    return 4


def main() -> None:
    if get_settings().environment == "production":
        raise SystemExit("Demo verisi üretim ortamında yüklenmez.")
    with Session(get_engine()) as db:
        users = seed_users(db)
        tickets = seed_tickets(db)
    print(f"Demo verisi hazır: {users} kullanıcı, {tickets} talep eklendi.")
    print(
        f"Giriş: kullanıcı adı yonetici / ayse / burak / elektrik.usta ..., parola: {DEMO_PASSWORD}"
    )


if __name__ == "__main__":
    main()
