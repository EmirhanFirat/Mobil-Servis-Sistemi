from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.vocabulary import TEAM_NAMES, TeamCode
from app.models import Team

API_ROOT = Path(__file__).resolve().parents[1]


def test_migrationlar_modellerle_tutarli_sapma_yok(db_engine: Engine, test_database_url: str):
    config = Config(str(API_ROOT / "alembic.ini"))
    config.attributes["url"] = test_database_url

    # Modellerde migration'a yansıtılmamış bir değişiklik varsa check hata verir.
    command.check(config)


def test_0003_asagi_yukari_veriyi_korur_ve_yeni_sonuclari_eski_degere_cevirir(
    db_engine: Engine, test_database_url: str
):
    """0003'ten 0002'ye inip tekrar çıkmak: mevcut kullanıcı ve talepler silinmez; yalnızca canlı
    demoya özgü iki iş sonucu (eski kısıtta olmayan) eski en yakın değere çevrilir."""
    config = Config(str(API_ROOT / "alembic.ini"))
    config.attributes["url"] = test_database_url
    with db_engine.begin() as conn:
        conn.execute(
            text(
                "insert into users (id, username, display_name, password_hash, role, is_demo) "
                "values ('00000000-0000-0000-0000-0000000000a1', 'gercek', 'Gerçek', 'h', "
                "'requester', false), "
                "('00000000-0000-0000-0000-0000000000a2', 'ziyaretci-1', 'Z', '!demo', "
                "'requester', true)"
            )
        )
        conn.execute(
            text(
                "insert into tickets (id, title, description, location, created_by_id, status, "
                "priority) values ('00000000-0000-0000-0000-0000000000b1', 'T', 'D', 'L', "
                "'00000000-0000-0000-0000-0000000000a2', 'new', 'normal')"
            )
        )
        conn.execute(
            text(
                "insert into decision_jobs (id, ticket_id, strategy, status, outcome) values "
                "('00000000-0000-0000-0000-0000000000c1', "
                "'00000000-0000-0000-0000-0000000000b1', 'jev_only', 'failed', "
                "'provider_uncertain')"
            )
        )
    try:
        command.downgrade(config, "0002")
        with db_engine.connect() as conn:
            tables = set(
                conn.scalars(text("select tablename from pg_tables where schemaname = 'public'"))
            )
            columns = set(
                conn.scalars(
                    text(
                        "select column_name from information_schema.columns "
                        "where table_name = 'users'"
                    )
                )
            )
            outcome = conn.scalar(
                text("select outcome from decision_jobs where strategy = 'jev_only'")
            )
            users = conn.scalar(text("select count(*) from users"))
        assert not {"budgets", "budget_entries", "demo_requests"} & tables
        assert not {"is_demo", "demo_ip_hash"} & columns
        assert outcome == "failed_provider"  # eski kısıtta olmayan değer en yakınına çevrildi
        assert users == 2  # kullanıcılar silinmedi
    finally:
        command.upgrade(config, "head")
        with db_engine.begin() as conn:
            conn.execute(text("TRUNCATE ticket_events, tickets, users RESTART IDENTITY CASCADE"))

    with db_engine.connect() as conn:
        tables = set(
            conn.scalars(text("select tablename from pg_tables where schemaname='public'"))
        )
    assert {"budgets", "budget_entries", "demo_requests"} <= tables


def test_migration_dogrudan_adresi_havuzlu_adrese_tercih_eder(test_database_url: str):
    """TALEPAKIS_MIGRATION_DATABASE_URL verilirse alembic onu kullanır (Neon: havuzsuz bağlantı)."""
    import os
    import subprocess
    import sys

    env = {
        **os.environ,
        # Havuzlu adres bozuk: yalnızca migration adresi kullanılırsa komut başarılı olur.
        "TALEPAKIS_DATABASE_URL": "postgresql+psycopg://u:p@127.0.0.1:1/yok",
        "TALEPAKIS_MIGRATION_DATABASE_URL": test_database_url,
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "0003" in result.stdout + result.stderr


def test_ekipler_sozlukle_ayni_migrationla_gelir(db_engine: Engine):
    with Session(db_engine) as session:
        teams = {team.code: team.name for team in session.scalars(select(Team))}

    assert teams == {code.value: name for code, name in TEAM_NAMES.items()}
    assert set(teams) == {code.value for code in TeamCode}


def test_enum_alanlari_veritabaninda_da_kisitli(db_engine: Engine):
    # Uygulamayı atlayıp geçersiz değer yazmaya çalış: CHECK kısıtı reddetmeli.
    with pytest.raises(IntegrityError), db_engine.begin() as conn:
        conn.execute(
            text(
                "insert into users (id, username, display_name, password_hash, role) "
                "values (gen_random_uuid(), 'x', 'X', 'h', 'superuser')"
            )
        )
