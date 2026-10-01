import os
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, selectinload

from app import security
from app.config import Settings, get_settings
from app.db import get_db
from app.domain.vocabulary import Role
from app.main import create_app
from app.models import Team, TeamMembership, Ticket, User
from app.schemas import TicketCreate
from app.services import tickets as ticket_service

API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_NAME = "talepakis_test"
TEST_PASSWORD = "test-parola-123"

# Testler yüzlerce parola özeti üretir; maliyeti düşük bir Argon2 örneği kullan.
security._hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest.fixture(autouse=True)
def _izole_ortam(monkeypatch):
    """Geliştiricinin kendi TALEPAKIS_* değişkenleri testleri etkilemesin."""
    for ad in [ad for ad in os.environ if ad.startswith("TALEPAKIS_")]:
        monkeypatch.delenv(ad)


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture
def password() -> str:
    return TEST_PASSWORD


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """Ayarları .env dosyasından okumayan uygulama (veritabanı gerektirmez)."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# --- Veritabanı: her test oturumunda sıfırdan kurulan ayrı bir test veritabanı ---


def _admin_conninfo(settings: Settings) -> dict:
    url = make_url(settings.database_url)
    return {
        "host": url.host,
        "port": url.port,
        "user": url.username,
        "password": url.password,
        "dbname": url.database,
        "autocommit": True,
        "connect_timeout": 5,
    }


@pytest.fixture(scope="session")
def test_database_url() -> str:
    base = Settings(_env_file=None)
    # Geliştirme veritabanına yanlışlıkla dokunulmasın: ad her zaman sabit test adıdır.
    url = make_url(base.database_url).set(database=TEST_DB_NAME)
    assert url.database == TEST_DB_NAME

    try:
        with psycopg.connect(**_admin_conninfo(base)) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    except psycopg.OperationalError as exc:
        pytest.exit(
            "PostgreSQL'e bağlanılamadı. Docker Desktop açık mı? Önce: docker compose up -d db\n"
            f"Ayrıntı: {exc}",
            returncode=2,
        )

    rendered = url.render_as_string(hide_password=False)
    config = Config(str(API_ROOT / "alembic.ini"))
    config.attributes["url"] = rendered
    command.upgrade(config, "head")
    return rendered


@pytest.fixture(scope="session")
def db_engine(test_database_url: str) -> Iterator[Engine]:
    engine = create_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine: Engine) -> Iterator[Session]:
    """Test verisi hazırlamak için oturum. Test bitince kullanıcı/talep tabloları boşaltılır."""
    with Session(db_engine) as session:
        yield session
    with db_engine.begin() as conn:
        # Ekipler başvuru verisidir (migration ile gelir); boşaltılmaz.
        conn.execute(
            text(
                "TRUNCATE ticket_events, tickets, team_memberships, users RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def api(app: FastAPI, db_engine: Engine, db: Session) -> TestClient:
    """Gerçek veritabanına bağlı istemci. Her istek kendi oturumunu açar (üretimdeki gibi)."""

    def _session() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_db] = _session
    return TestClient(app)


@pytest.fixture
def teams(db: Session) -> dict[str, Team]:
    return {team.code: team for team in db.scalars(select(Team))}


@pytest.fixture
def make_user(db: Session, teams: dict[str, Team]) -> Callable[..., User]:
    def _make(
        username: str,
        role: Role = Role.REQUESTER,
        team: str | list[str] | None = None,
        *,
        is_active: bool = True,
    ) -> User:
        user = User(
            username=username,
            display_name=username.replace(".", " ").title(),
            password_hash=security.hash_password(TEST_PASSWORD),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.flush()
        team_codes = [team] if isinstance(team, str) else (team or [])
        for code in team_codes:
            db.add(TeamMembership(user_id=user.id, team_id=teams[code].id))
        db.commit()
        return db.scalar(select(User).options(selectinload(User.teams)).where(User.id == user.id))

    return _make


@pytest.fixture
def make_ticket(db: Session) -> Callable[..., Ticket]:
    def _make(owner: User, title: str = "Lavabo akıtıyor", **fields) -> Ticket:
        data = TicketCreate(
            title=title,
            description=fields.pop("description", "Su koridora yayılıyor."),
            location=fields.pop("location", "B Blok, 2. kat"),
        )
        return ticket_service.create_ticket(db, owner, data)

    return _make


@pytest.fixture
def auth(settings: Settings) -> Callable[[User], dict[str, str]]:
    def _headers(user: User) -> dict[str, str]:
        token = security.create_access_token(user.id, settings)
        return {"Authorization": f"Bearer {token}"}

    return _headers
