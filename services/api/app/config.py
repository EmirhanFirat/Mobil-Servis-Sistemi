from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Yalnızca yerel geliştirme içindir. Üretimde farklı ve güçlü bir değer zorunludur.
DEV_SECRET_KEY = "dev-only-insecure-secret-key-change-me-0123456789"


class Settings(BaseSettings):
    """Uygulama ayarları. Değerler TALEPAKIS_ önekli ortam değişkenlerinden veya .env'den gelir."""

    model_config = SettingsConfigDict(env_prefix="TALEPAKIS_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    # Varsayılan değer yalnızca docker-compose.yml'deki geliştirme veritabanına uyar.
    # "localhost" yerine 127.0.0.1: Windows'ta localhost önce IPv6'yı dener ve ~8 sn bekler.
    database_url: str = "postgresql+psycopg://talepakis:talepakis@127.0.0.1:5432/talepakis"

    # Oturum belirteçlerini imzalar. Mobil uygulamaya veya depoya asla konmaz.
    secret_key: SecretStr = SecretStr(DEV_SECRET_KEY)
    access_token_minutes: int = 480

    # Ücretli model çağrıları VARSAYILAN OLARAK KAPALIDIR. Açmadan gerçek Jev/LLM çağrısı yapılamaz
    # (bkz. app/decision/factory.py). Anahtarlar yalnızca burada, ortam değişkeninden okunur;
    # mobil uygulamaya, depoya veya sohbete konmaz.
    paid_model_calls_enabled: bool = False
    jev_api_key: SecretStr | None = None
    jev_base_url: str = "https://api.typesafe.ai"
    jev_model: str = "jev-1.13.0"  # sabitlenmiş sürüm; takma ad (jev-latest) değil
    # Ekonomik LLM (Anthropic). Standart ANTHROPIC_API_KEY ortam değişkeni BİLEREK okunmaz: başka
    # araçlar için tanımlı bir anahtar bu projede kazara ücretli çağrı yapmasın.
    anthropic_api_key: SecretStr | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-haiku-4-5-20251001"  # sabitlenmiş sürüm, takma ad değil

    # Tarayıcıdan API'ye erişebilen kaynaklar: yönetici paneli (5173) ve mobil uygulamanın web
    # önizlemesi (8081). Yalnızca geliştirme varsayılanıdır; üretimde ortam değişkeniyle verilir.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
    ]

    @model_validator(mode="after")
    def _uretimde_guclu_anahtar_iste(self) -> "Settings":
        if self.environment == "production":
            key = self.secret_key.get_secret_value()
            if key == DEV_SECRET_KEY or len(key) < 32:
                raise ValueError(
                    "Üretimde TALEPAKIS_SECRET_KEY için en az 32 karakterlik, "
                    "geliştirme varsayılanından farklı bir değer gerekir."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
