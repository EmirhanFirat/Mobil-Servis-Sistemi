import pytest
from sqlalchemy import func, select

from app import seed
from app.config import get_settings
from app.domain.vocabulary import Priority, TicketStatus
from app.models import Ticket, TicketEvent, User


def test_demo_verisi_hazirlanir_ve_tekrar_calistirmak_guvenlidir(db):
    assert seed.seed_users(db) == len(seed.DEMO_USERS)
    assert seed.seed_tickets(db) == 4

    assert seed.seed_users(db) == 0
    assert seed.seed_tickets(db) == 0
    assert db.scalar(select(func.count()).select_from(User)) == len(seed.DEMO_USERS)
    assert db.scalar(select(func.count()).select_from(Ticket)) == 4


def test_ornek_talepler_farkli_durumlari_ve_olay_gecmisini_gosterir(db):
    seed.seed_users(db)
    seed.seed_tickets(db)

    tickets = db.scalars(select(Ticket).order_by(Ticket.number)).all()

    assert [t.status for t in tickets] == [
        TicketStatus.NEW,
        TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.RESOLVED,
    ]
    assert tickets[1].priority is Priority.HIGH
    assert tickets[1].team.code == "electrical" and tickets[1].assignee.username == "elektrik.usta"
    assert db.scalar(select(func.count()).select_from(TicketEvent)) > 10


def test_demo_kullanicilari_giris_yapabilir_ve_rolleri_dogru(api, db):
    seed.seed_users(db)

    for username, _, role, _ in seed.DEMO_USERS:
        response = api.post(
            "/auth/login", json={"username": username, "password": seed.DEMO_PASSWORD}
        )
        assert response.status_code == 200, username
        assert response.json()["user"]["role"] == role.value


def test_uretim_ortaminda_demo_verisi_yuklenmez(monkeypatch):
    monkeypatch.setenv("TALEPAKIS_ENVIRONMENT", "production")
    monkeypatch.setenv("TALEPAKIS_SECRET_KEY", "k" * 40)
    get_settings.cache_clear()
    try:
        with pytest.raises(SystemExit, match="üretim"):
            seed.main()
    finally:
        get_settings.cache_clear()
