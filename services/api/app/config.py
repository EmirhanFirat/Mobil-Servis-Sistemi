from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.domain.decision_jobs import DECISION_OFF, FREE_STRATEGY_NAMES

# Yalnızca yerel geliştirme içindir. Üretimde farklı ve güçlü bir değer zorunludur.
DEV_SECRET_KEY = "dev-only-insecure-secret-key-change-me-0123456789"
# docker-compose.yml'deki geliştirme veritabanının parolası; üretimde kullanılamaz.
DEV_DATABASE_PASSWORD = "talepakis"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _database_host(database_url: str) -> str | None:
    """Veritabanı adresindeki ana makine adı (ayrıştırılamazsa/unix soketinde None)."""
    try:
        return make_url(database_url).host
    except ArgumentError:
        return None


class Settings(BaseSettings):
    """Uygulama ayarları. Değerler TALEPAKIS_ önekli ortam değişkenlerinden veya .env'den gelir."""

    model_config = SettingsConfigDict(env_prefix="TALEPAKIS_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    # Varsayılan değer yalnızca docker-compose.yml'deki geliştirme veritabanına uyar.
    # "localhost" yerine 127.0.0.1: Windows'ta localhost önce IPv6'yı dener ve ~8 sn bekler.
    database_url: str = "postgresql+psycopg://talepakis:talepakis@127.0.0.1:5432/talepakis"
    # Veritabanına bağlanırken en çok beklenecek süre (sn). psycopg'un varsayılanı Windows'ta ~130
    # sn sürer: veritabanı kapalıyken her istek dakikalarca asılı kalır ve istemci "sunucu zamanında
    # yanıt vermedi" der. Kısa tutulur ki istek açık bir 503 (database_unavailable) ile bitsin.
    database_connect_timeout_s: int = Field(default=5, ge=1, le=60)
    # Havuzlayıcılı sunucusuz veritabanı (Neon `-pooler` adresi, PgBouncer işlem modu): sunucu
    # tarafı hazır ifadeler kapatılır ve bağlantı havuzu küçük tutulur (ücretsiz katman sınırlı).
    database_pooled: bool = False
    database_pool_size: int = Field(default=5, ge=1, le=20)
    database_max_overflow: int = Field(default=2, ge=0, le=20)
    # Migration için DOĞRUDAN (havuzsuz) adres; boşsa `database_url` kullanılır. Neon, şema
    # değişikliklerinin havuzlayıcı üzerinden değil doğrudan bağlantıyla yapılmasını önerir.
    migration_database_url: str | None = None

    # Model karşılaştırma sayfasının okuduğu deney klasörü (yalnızca okunur). Boşsa depo kökündeki
    # evaluation/runs kullanılır. Deney dosyaları Git'e girmez; yerelde çalıştırmayla oluşur.
    experiments_dir: Path | None = None

    # Oturum belirteçlerini imzalar. Mobil uygulamaya veya depoya asla konmaz.
    secret_key: SecretStr = SecretStr(DEV_SECRET_KEY)
    access_token_minutes: int = 480

    # Giriş denemesi sınırı (süreç belleğinde; bkz. app/hardening.py). Başarısız denemeler sayılır:
    # aynı IP + aynı hesap, aynı hesap (tüm IP'ler) ve aynı IP (tüm hesaplar) için ayrı sınırlar.
    login_pair_limit: int = Field(default=5, ge=1, le=1000)
    login_account_limit: int = Field(default=20, ge=1, le=10000)
    login_ip_limit: int = Field(default=40, ge=1, le=10000)
    login_window_seconds: int = Field(default=900, ge=1, le=86400)

    # İstek gövdesi üst sınırı (bayt). En büyük meşru istek ~4 KB'lık talep metnidir.
    max_request_body_bytes: int = Field(default=65536, ge=1024, le=10_000_000)

    # İstemci IP'si. Boşsa doğrudan bağlantının adresi kullanılır. Ters vekilin ardında (ör. Render)
    # bu adres vekilin adresidir ve tüm ziyaretçiler tek IP görünür. Başlık adı verilirse değer o
    # başlıktan alınır: virgüllü listede (X-Forwarded-For) SAĞDAN `trusted_proxy_hops`'uncu girdi
    # (güvendiğimiz vekilin eklediği; istemcinin sola ekleyebildikleri yok sayılır). Başlık
    # sağlayıcı tarafından belgelenmemişse (Render) doğrulanmadan açılmamalıdır.
    client_ip_header: str | None = None
    trusted_proxy_hops: int = Field(default=1, ge=1, le=5)

    # --- Canlı demo (portföy demosu). Varsayılan KAPALI; ücretli çağrılar ayrıca onay ister. ---
    demo_enabled: bool = False
    # "jev": gerçek Jev (yalnızca jev_only; Anthropic ve hibrit demoda yoktur). "mock": yalnızca
    # yerel deneme için; sonuç açıkça MOCK etiketlenir ve üretimde kabul edilmez.
    demo_provider: Literal["jev", "mock"] = "jev"
    # Demo için PostgreSQL'deki bütçe kapsamı. Değerlendirme deneylerinin dosya defterinden
    # bağımsızdır; tutarı `python -m app.manage create-budget` ile ELLE (onaydan sonra) tanımlanır.
    demo_budget_id: str = Field(default="canli-demo", pattern=r"^[a-z0-9][a-z0-9._-]{1,58}$")
    demo_jev_timeout_s: float = Field(default=15.0, ge=1, le=30)
    demo_session_minutes: int = Field(default=180, ge=5, le=1440)
    demo_max_decisions_per_session: int = Field(default=5, ge=1, le=50)
    demo_max_concurrent_calls: int = Field(default=2, ge=1, le=20)
    demo_max_sessions_per_day: int = Field(default=300, ge=1, le=100_000)
    demo_max_decisions_per_day: int = Field(default=500, ge=1, le=100_000)
    # IP sınırı yalnızca doğru IP'nin bilindiği (`client_ip_header` doğrulandı) durumda açılmalıdır;
    # aksi hâlde tüm ziyaretçiler tek IP sayılır ve kota herkes için tükenir.
    demo_ip_limits_enabled: bool = False
    demo_max_sessions_per_ip_hour: int = Field(default=5, ge=1, le=1000)
    demo_max_decisions_per_ip_hour: int = Field(default=20, ge=1, le=1000)
    # Ziyaretçi hesabı ve talepleri bu süre sonra silinir (yalnızca is_demo hesapları).
    demo_retention_hours: int = Field(default=72, ge=1, le=720)

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

    # Karar motoru: talep açılırken kaydedilen karar işinin stratejisi ("off" = iş kaydetme).
    # Yalnızca ücretsiz stratejiler (rule_based, mock_*) seçilebilir; gerçek Jev/LLM stratejileri
    # harcama koruması olmadan ürün akışına bağlanmaz. Worker: `python -m app.worker`.
    decision_strategy: str = "rule_based"
    decision_job_max_attempts: int = 3
    decision_job_lease_seconds: int = 120
    worker_poll_seconds: float = 2.0

    # Tarayıcıdan API'ye erişebilen kaynaklar: yönetici paneli (5173) ve mobil uygulamanın web
    # önizlemesi (8081). Yalnızca geliştirme varsayılanıdır; üretimde ortam değişkeniyle verilir.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
    ]

    @model_validator(mode="after")
    def _gecerli_karar_stratejisi(self) -> "Settings":
        allowed = (*FREE_STRATEGY_NAMES, DECISION_OFF)
        if self.decision_strategy not in allowed:
            raise ValueError(
                f"TALEPAKIS_DECISION_STRATEGY şunlardan biri olmalı: {', '.join(allowed)} "
                "(gerçek Jev/LLM stratejileri ürün akışına henüz bağlı değil)."
            )
        if self.decision_job_max_attempts < 1 or self.decision_job_lease_seconds < 1:
            raise ValueError("Karar işi deneme sayısı ve kira süresi en az 1 olmalı.")
        return self

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

    @model_validator(mode="after")
    def _dev_anahtari_yalniz_yerel_veritabaniyla(self) -> "Settings":
        """TALEPAKIS_ENVIRONMENT unutulursa varsayılan 'development' kalır; o zaman herkesçe bilinen
        anahtarla imzalanan belirteçler sahte yönetici girişine izin verir. Uzak (yerel olmayan) bir
        veritabanına bağlanan süreç bu anahtarla BAŞLAMAZ."""
        if self.secret_key.get_secret_value() == DEV_SECRET_KEY:
            host = _database_host(self.database_url)
            if host is not None and host not in LOOPBACK_HOSTS:
                raise ValueError(
                    "Geliştirme gizli anahtarı yalnızca yerel veritabanıyla kullanılabilir. "
                    "Uzak veritabanı için TALEPAKIS_SECRET_KEY tanımla (ve üretimde "
                    "TALEPAKIS_ENVIRONMENT=production ver)."
                )
        return self

    @model_validator(mode="after")
    def _uretimde_guvenli_kaynaklar_ve_veritabani(self) -> "Settings":
        if self.environment != "production":
            return self
        for origin in self.cors_origins:
            parts = urlsplit(origin)
            if parts.scheme != "https" or not parts.hostname or parts.hostname in LOOPBACK_HOSTS:
                raise ValueError(
                    "Üretimde TALEPAKIS_CORS_ORIGINS yalnızca https:// adreslerini içermeli "
                    f"(yerel adres ve '*' olamaz); geçersiz: {origin!r}."
                )
        try:
            password = make_url(self.database_url).password
        except ArgumentError as exc:
            raise ValueError("TALEPAKIS_DATABASE_URL ayrıştırılamadı.") from exc
        if not password or password == DEV_DATABASE_PASSWORD:
            raise ValueError(
                "Üretimde TALEPAKIS_DATABASE_URL geliştirme veritabanı parolasını (veya boş "
                "parolayı) kullanamaz."
            )
        if self.demo_enabled and self.demo_provider != "jev":
            # Mock sonuçlar herkese açık demoda "gerçek Jev" gibi görünmesin.
            raise ValueError("Üretimde TALEPAKIS_DEMO_PROVIDER yalnızca 'jev' olabilir.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
