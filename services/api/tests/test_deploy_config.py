"""Ücretsiz barındırma (Render + Neon) için yapılandırma: veritabanı motoru, istemci IP'si, demo
ayarları. Veritabanı gerektirmez."""

import pytest
from pydantic import ValidationError
from starlette.requests import Request

import app.db as app_db
from app.config import Settings
from app.hardening import client_ip

PROD_DB = "postgresql+psycopg://uygulama:guclu-parola-9@ep-x-pooler.neon.tech:5432/talepakis"


def production(**overrides) -> Settings:
    values = {
        "environment": "production",
        "secret_key": "k" * 40,
        "database_url": PROD_DB,
        "cors_origins": ["https://demo.ornek.com"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


# --- Veritabanı motoru ---


@pytest.fixture
def engine_args(monkeypatch):
    captured: dict = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(app_db, "create_engine", fake_create_engine)
    return captured


def test_havuzlayicili_baglantida_hazir_ifade_kapatilir_ve_havuz_kucuk_tutulur(engine_args):
    app_db.make_engine(
        production(database_pooled=True, database_pool_size=3, database_max_overflow=1)
    )

    assert engine_args["connect_args"]["prepare_threshold"] is None
    assert engine_args["connect_args"]["connect_timeout"] == 5
    assert (engine_args["pool_size"], engine_args["max_overflow"]) == (3, 1)
    assert engine_args["pool_pre_ping"] is True and engine_args["pool_recycle"] == 300


def test_havuzlayicisiz_gelistirmede_varsayilan_havuz_ve_hazir_ifadeler_korunur(engine_args):
    app_db.make_engine(Settings(_env_file=None))

    assert "prepare_threshold" not in engine_args["connect_args"]
    assert "pool_size" not in engine_args  # SQLAlchemy varsayılanı
    assert engine_args["pool_pre_ping"] is True


def test_uretimde_havuzlayicisiz_da_havuz_sinirlidir(engine_args):
    app_db.make_engine(production())

    assert engine_args["pool_size"] == 5 and engine_args["max_overflow"] == 2
    assert "prepare_threshold" not in engine_args["connect_args"]


@pytest.mark.parametrize(
    "field,value",
    [("database_pool_size", 0), ("database_pool_size", 21), ("database_max_overflow", 21)],
)
def test_havuz_ayarlari_sinirlidir(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


# --- İstemci IP'si ---


def request_with(headers: list[tuple[str, str]], peer: str | None = "10.0.0.7") -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        "client": (peer, 5555) if peer else None,
    }
    return Request(scope)


def settings_for(header: str | None, hops: int = 1) -> Settings:
    return Settings(_env_file=None, client_ip_header=header, trusted_proxy_hops=hops)


def test_baslik_verilmediyse_dogrudan_baglanti_adresi_kullanilir():
    request = request_with([("X-Forwarded-For", "1.2.3.4")])

    assert client_ip(request, settings_for(None)) == "10.0.0.7"
    assert client_ip(request) == "10.0.0.7"  # ayar verilmezse de


def test_baglanti_adresi_yoksa_bilinmiyor():
    assert client_ip(request_with([], peer=None)) == "bilinmiyor"


def test_tek_degerli_baslik_kullanilir():
    request = request_with([("CF-Connecting-IP", "203.0.113.5")])

    assert client_ip(request, settings_for("cf-connecting-ip")) == "203.0.113.5"


def test_xff_sagdan_ilk_girdi_vekilin_ekledigidir_istemcinin_soldan_eklediklerine_guvenilmez():
    # İstemci kendi başlığına "6.6.6.6" yazdı; güvendiğimiz vekil gerçek adresi (1.1.1.1) SONA ekledi.
    request = request_with([("X-Forwarded-For", "6.6.6.6, 1.1.1.1")])

    assert client_ip(request, settings_for("x-forwarded-for")) == "1.1.1.1"


def test_iki_guvenilir_vekil_icin_sagdan_ikinci_girdi():
    request = request_with([("X-Forwarded-For", "6.6.6.6, 1.1.1.1, 9.9.9.9")])

    assert client_ip(request, settings_for("x-forwarded-for", hops=2)) == "1.1.1.1"


def test_birden_cok_baslik_satiri_birlestirilir():
    request = request_with([("X-Forwarded-For", "6.6.6.6"), ("X-Forwarded-For", "1.1.1.1")])

    assert client_ip(request, settings_for("x-forwarded-for")) == "1.1.1.1"


def test_beklenenden_az_girdi_varsa_dogrudan_adrese_dusulur():
    request = request_with([("X-Forwarded-For", "1.1.1.1")])

    assert client_ip(request, settings_for("x-forwarded-for", hops=2)) == "10.0.0.7"


@pytest.mark.parametrize("raw", ["", "bilmiyorum", "999.1.1.1", "1.1.1.1:8080", "<script>"])
def test_gecerli_ip_olmayan_baslik_degeri_yok_sayilir(raw):
    request = request_with([("X-Forwarded-For", raw)])

    assert client_ip(request, settings_for("x-forwarded-for")) == "10.0.0.7"


def test_baslik_hic_gelmediyse_dogrudan_adres():
    assert client_ip(request_with([]), settings_for("x-forwarded-for")) == "10.0.0.7"


def test_ipv6_normallestirilir():
    request = request_with([("CF-Connecting-IP", "2001:DB8:0:0:0:0:0:1")])

    assert client_ip(request, settings_for("cf-connecting-ip")) == "2001:db8::1"


# --- Demo ayarları ---


def test_demo_varsayilan_olarak_kapali_ve_ip_siniri_kapali():
    settings = Settings(_env_file=None)

    assert settings.demo_enabled is False
    assert settings.demo_ip_limits_enabled is False  # IP doğrulanmadan sınır uygulanmaz
    assert settings.demo_provider == "jev" and settings.demo_budget_id == "canli-demo"
    assert settings.paid_model_calls_enabled is False
    assert settings.jev_api_key is None and settings.anthropic_api_key is None


def test_uretimde_demo_saglayicisi_mock_olamaz():
    with pytest.raises(ValidationError, match="DEMO_PROVIDER"):
        production(demo_enabled=True, demo_provider="mock")


def test_uretimde_demo_jev_ile_acilabilir():
    settings = production(demo_enabled=True, demo_provider="jev")

    assert settings.demo_enabled and settings.demo_provider == "jev"


def test_gelistirmede_mock_demo_saglayicisi_kabul_edilir():
    assert Settings(_env_file=None, demo_enabled=True, demo_provider="mock").demo_provider == "mock"


@pytest.mark.parametrize("budget_id", ["", "A", "Büyük Harf", "x" * 70, "-başında", "bosluk var"])
def test_gecersiz_demo_butce_kimligi_reddedilir(budget_id):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, demo_budget_id=budget_id)


@pytest.mark.parametrize(
    "field,value",
    [
        ("demo_jev_timeout_s", 0.5),
        ("demo_jev_timeout_s", 31),
        ("demo_max_decisions_per_session", 0),
        ("demo_max_concurrent_calls", 0),
        ("demo_max_sessions_per_day", 0),
        ("demo_retention_hours", 0),
        ("demo_session_minutes", 1),
        ("trusted_proxy_hops", 0),
    ],
)
def test_demo_sinirlari_anlamsiz_degerleri_reddeder(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
