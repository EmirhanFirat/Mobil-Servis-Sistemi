from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Uygulama ayarları. Değerler TALEPAKIS_ önekli ortam değişkenlerinden veya .env'den gelir."""

    model_config = SettingsConfigDict(env_prefix="TALEPAKIS_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    # Varsayılan değer yalnızca docker-compose.yml'deki geliştirme veritabanına uyar.
    database_url: str = "postgresql+psycopg://talepakis:talepakis@localhost:5432/talepakis"


@lru_cache
def get_settings() -> Settings:
    return Settings()
