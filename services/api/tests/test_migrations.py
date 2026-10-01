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
