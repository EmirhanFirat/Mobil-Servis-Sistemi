from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import Settings, get_settings

# Kısıt adları öngörülebilir olsun; Alembic migration'ları bu adlara güvenir.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_engine(settings: Settings) -> Engine:
    """Bağlantı üst süreli motor: veritabanı kapalıyken istek asılı kalmaz, hızla hata verir."""
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.database_connect_timeout_s},
    )


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings())


def get_db() -> Iterator[Session]:
    """İstek başına oturum. Yazma işlemleri servis fonksiyonlarında açıkça commit edilir."""
    with Session(get_engine()) as session:
        yield session
