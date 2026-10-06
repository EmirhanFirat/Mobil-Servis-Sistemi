"""Üretim sertleştirmesi (DB'siz): ayar doğrulamaları, güvenlik başlıkları, belge uçlarının kapanması,
istek gövdesi sınırı ve giriş sınırlayıcısının kendisi. Sınırlayıcının girişe bağlanışı
tests/test_login_throttle.py içindedir."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.config import DEV_SECRET_KEY, Settings, get_settings
from app.hardening import API_CSP, BodyLimitMiddleware, LoginThrottle
from app.main import create_app

STRONG_KEY = "k" * 40
PROD_DB = "postgresql+psycopg://uygulama:guclu-parola-9@db.ornek.com:5432/talepakis"
PROD_ORIGINS = '["https://panel.ornek.com"]'


def production_settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "secret_key": STRONG_KEY,
        "database_url": PROD_DB,
        "cors_origins": ["https://panel.ornek.com"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


# --- Ayar doğrulamaları -----------------------------------------------------------------------


def test_uretim_ayarlari_gecerliyse_kabul_edilir():
    settings = production_settings()

    assert settings.environment == "production"
    assert settings.cors_origins == ["https://panel.ornek.com"]


@pytest.mark.parametrize(
    "origin",
    [
        "http://panel.ornek.com",  # https değil
        "https://localhost:5173",  # yerel adres
        "https://127.0.0.1",
        "https://[::1]:5173",
        "*",
        "panel.ornek.com",  # şema yok
        "https://",  # ana makine yok
    ],
)
def test_uretimde_guvensiz_cors_kaynagi_reddedilir(origin: str):
    with pytest.raises(ValidationError, match="TALEPAKIS_CORS_ORIGINS"):
        production_settings(cors_origins=[origin])


def test_uretimde_varsayilan_yerel_cors_listesi_reddedilir():
    """CORS açıkça verilmezse geliştirme varsayılanı (localhost) üretimde kabul edilmez."""
    with pytest.raises(ValidationError, match="TALEPAKIS_CORS_ORIGINS"):
        Settings(
            _env_file=None, environment="production", secret_key=STRONG_KEY, database_url=PROD_DB
        )


def test_gelistirmede_yerel_cors_varsayilani_kabul_edilir():
    assert "http://localhost:5173" in Settings(_env_file=None).cors_origins


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://talepakis:talepakis@db.ornek.com:5432/talepakis",  # geliştirme parolası
        "postgresql+psycopg://uygulama@db.ornek.com:5432/talepakis",  # parolasız
    ],
)
def test_uretimde_gelistirme_veya_bos_veritabani_parolasi_reddedilir(url: str):
    with pytest.raises(ValidationError, match="TALEPAKIS_DATABASE_URL"):
        production_settings(database_url=url)


def test_uretimde_ayrilamayan_veritabani_adresi_reddedilir():
    with pytest.raises(ValidationError, match="ayrıştırılamadı"):
        production_settings(database_url="bu bir adres değil")


@pytest.mark.parametrize("host", ["db.ornek.com", "10.0.0.5", "talepakis-db.internal", "db"])
def test_gelistirme_anahtari_uzak_veritabaniyla_baslamaz(host: str):
    """TALEPAKIS_ENVIRONMENT unutulduysa bile herkesçe bilinen anahtarla uzak veritabanına bağlanılamaz."""
    url = f"postgresql+psycopg://u:p@{host}:5432/x"

    with pytest.raises(ValidationError, match="yalnızca yerel veritabanıyla"):
        Settings(_env_file=None, database_url=url)  # ortam varsayılanı: development


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
def test_gelistirme_anahtari_yerel_veritabaniyla_calisir(host: str):
    settings = Settings(_env_file=None, database_url=f"postgresql+psycopg://u:p@{host}:5432/x")

    assert settings.secret_key.get_secret_value() == DEV_SECRET_KEY


def test_ozel_anahtarla_uzak_veritabani_serbest():
    settings = Settings(_env_file=None, database_url=PROD_DB, secret_key=STRONG_KEY)

    assert settings.database_url == PROD_DB


@pytest.mark.parametrize(
    "field,value",
    [
        ("login_pair_limit", 0),
        ("login_account_limit", 0),
        ("login_ip_limit", 0),
        ("login_window_seconds", 0),
        ("max_request_body_bytes", 10),
    ],
)
def test_sinir_ayarlari_anlamsiz_degerleri_reddeder(field: str, value: int):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


# --- Güvenlik başlıkları ve belge uçları ------------------------------------------------------


@pytest.fixture
def production_client(monkeypatch: pytest.MonkeyPatch):
    """`create_app` ve uç noktalar ayarları ortamdan (önbellekli) okur; üretim ayarlarıyla ayrı bir
    uygulama kurar. Önbellek test bitince temizlenir: yoksa üretim ayarları sonraki testlere sızar."""
    monkeypatch.setenv("TALEPAKIS_ENVIRONMENT", "production")
    monkeypatch.setenv("TALEPAKIS_SECRET_KEY", STRONG_KEY)
    monkeypatch.setenv("TALEPAKIS_DATABASE_URL", PROD_DB)
    monkeypatch.setenv("TALEPAKIS_CORS_ORIGINS", PROD_ORIGINS)
    get_settings.cache_clear()
    try:
        yield TestClient(create_app())
    finally:
        get_settings.cache_clear()


SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
    "content-security-policy": API_CSP,
}


def test_api_yanitlari_guvenlik_basliklarini_tasir(client: TestClient):
    response = client.get("/health")

    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value
    assert "strict-transport-security" not in response.headers  # geliştirmede HTTPS varsayılmaz


def test_hata_yanitlari_da_guvenlik_basliklarini_tasir(client: TestClient):
    response = client.get("/tickets")  # belirteçsiz: 401

    assert response.status_code == 401
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value


def test_api_csp_hicbir_kaynaga_ve_cercevelemeye_izin_vermez():
    assert "default-src 'none'" in API_CSP
    assert "frame-ancestors 'none'" in API_CSP
    assert "unsafe" not in API_CSP and "*" not in API_CSP


def test_uretimde_hsts_vardir_ve_belge_uclari_kapalidir(production_client: TestClient):
    health = production_client.get("/health")
    assert health.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert production_client.get(path).status_code == 404, path


def test_uretimde_yalnizca_https_panel_kaynagi_cors_alir(production_client: TestClient):
    headers = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }

    panel = production_client.options(
        "/auth/login", headers={**headers, "Origin": "https://panel.ornek.com"}
    )
    local = production_client.options(
        "/auth/login", headers={**headers, "Origin": "http://localhost:5173"}
    )

    assert panel.headers["access-control-allow-origin"] == "https://panel.ornek.com"
    assert "access-control-allow-origin" not in local.headers


def test_gelistirmede_belge_uclari_acik_ve_docs_katı_csp_almaz(client: TestClient):
    assert client.get("/openapi.json").status_code == 200
    docs = client.get("/docs")

    assert docs.status_code == 200
    assert docs.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in docs.headers  # Swagger CDN'den betik yükler


def test_cors_izinli_kaynaga_basliklari_verir_digerine_vermez(client: TestClient):
    allowed = client.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    other = client.options(
        "/auth/login",
        headers={
            "Origin": "https://kotu.ornek.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in other.headers
    assert "access-control-allow-credentials" not in allowed.headers  # çerez yok, Bearer var


def test_cors_ile_gelen_413_de_tarayiciya_anlasilir_gider(client: TestClient):
    response = client.post(
        "/auth/login",
        content=b"x" * 70_000,
        headers={"Origin": "http://localhost:5173", "Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


# --- İstek gövdesi sınırı ---------------------------------------------------------------------


class Item(BaseModel):
    name: str


def limited_app(max_bytes: int = 100) -> TestClient:
    """Gerçek uç noktalar gibi Pydantic gövdesi okuyan küçük bir uygulama."""
    app = FastAPI()
    app.add_middleware(BodyLimitMiddleware, max_bytes=max_bytes)

    @app.post("/item")
    def create(item: Item) -> dict:
        return {"name": item.name}

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    return TestClient(app)


def chunks(*parts: bytes):
    yield from parts


def test_sinir_icindeki_istek_normal_islenir():
    client = limited_app()

    response = client.post("/item", json={"name": "ev"})

    assert response.status_code == 200
    assert response.json() == {"name": "ev"}


def test_bildirilen_uzunluk_asiyorsa_413_ve_istek_hic_okunmaz():
    client = limited_app()

    response = client.post("/item", json={"name": "x" * 500})

    assert response.status_code == 413
    assert response.json() == {"detail": "İstek gövdesi çok büyük.", "code": "payload_too_large"}


def test_parcali_gonderimde_de_sinir_asilinca_413_doner_400_degil():
    """Content-Length olmayan (parçalı) gövde: FastAPI okuma hatasını 400'e çevirirdi."""
    client = limited_app()
    body = json.dumps({"name": "y" * 500}).encode()

    response = client.post(
        "/item",
        content=chunks(body[:150], body[150:300], body[300:]),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


def test_parcali_gonderim_sinirin_altindaysa_gecer():
    client = limited_app()
    body = json.dumps({"name": "kısa"}).encode()

    response = client.post(
        "/item",
        content=chunks(body[:5], body[5:]),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200


def test_sinir_tam_sinirda_gecer_bir_bayt_fazlasinda_reddedilir():
    client = limited_app(max_bytes=40)
    exact = json.dumps({"name": "a" * 28}).encode()  # tam 40 bayt
    assert len(exact) == 40

    ok = client.post("/item", content=exact, headers={"Content-Type": "application/json"})
    over = client.post(
        "/item",
        content=exact + b" ",
        headers={"Content-Type": "application/json"},
    )

    assert ok.status_code == 200
    assert over.status_code == 413


def test_gövdesiz_istekler_sinirdan_etkilenmez():
    assert limited_app(max_bytes=1).get("/ping").json() == {"ok": True}


def test_gercek_uygulamada_asiri_buyuk_gövde_413(client: TestClient):
    response = client.post(
        "/tickets",
        content=b'{"title":"' + b"a" * 100_000 + b'"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


# --- Giriş sınırlayıcısı (saf mantık) ---------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_throttle(clock: Clock, **overrides) -> LoginThrottle:
    values = {"pair_limit": 5, "account_limit": 20, "ip_limit": 40, "window_s": 900}
    values.update(overrides)
    return LoginThrottle(clock=clock, **values)


def fail(throttle: LoginThrottle, n: int, ip: str = "1.1.1.1", user: str = "ayse") -> None:
    for _ in range(n):
        throttle.record_failure(ip, user)


def test_sinira_kadar_deneme_serbest_sinirda_engellenir():
    throttle = make_throttle(Clock())

    fail(throttle, 4)
    assert throttle.retry_after("1.1.1.1", "ayse") == 0
    fail(throttle, 1)

    assert throttle.retry_after("1.1.1.1", "ayse") > 0


def test_engel_suresi_pencere_dolunca_kalkar_ve_kalan_sure_dogru_verilir():
    clock = Clock()
    throttle = make_throttle(clock, pair_limit=2, window_s=100)
    fail(throttle, 1)
    clock.now += 60
    fail(throttle, 1)

    clock.now += 1  # t=61: ilk hata 39 sn sonra düşecek
    assert throttle.retry_after("1.1.1.1", "ayse") == 39
    clock.now += 39  # t=100: ilk hata düştü, sayaç sınırın altına indi
    assert throttle.retry_after("1.1.1.1", "ayse") == 0


def test_sinirin_ustunde_biriken_hatalar_engeli_uzatir():
    clock = Clock()
    throttle = make_throttle(clock, pair_limit=2, window_s=100)
    fail(throttle, 1)  # t=0
    clock.now += 60
    fail(throttle, 1)  # t=60
    clock.now += 10
    fail(throttle, 1)  # t=70 (engelliyken de denenmişse sayılır)

    clock.now += 30  # t=100: yalnızca ilk hata düştü, 2 hata kaldı → hâlâ engelli
    assert throttle.retry_after("1.1.1.1", "ayse") == 60  # ikinci hata t=160'ta düşer


def test_sinirin_cok_ustundeki_birikim_engeli_gereken_olaya_gore_uzatir():
    """Sayaç sınırın 2 üstündeyse yalnızca en eski olay değil, sayacı sınırın altına indirecek kadar
    olay düşmelidir: limit 2, hatalar t=0/10/20 → ilk iki hata düşünce (t=110) engel kalkar."""
    clock = Clock()
    throttle = make_throttle(clock, pair_limit=2, window_s=100)
    fail(throttle, 1)  # t=0
    clock.now += 10
    fail(throttle, 1)  # t=10
    clock.now += 10
    fail(throttle, 1)  # t=20

    clock.now += 10  # t=30
    assert throttle.retry_after("1.1.1.1", "ayse") == 80  # t=10'daki hata t=110'da düşer
    clock.now += 70  # t=100: yalnızca t=0 düştü, 2 hata kaldı → hâlâ engelli
    assert throttle.retry_after("1.1.1.1", "ayse") == 10
    clock.now += 10  # t=110: sayaç 1'e indi
    assert throttle.retry_after("1.1.1.1", "ayse") == 0


def test_baska_ip_ayni_hesapta_cift_sayacindan_etkilenmez():
    throttle = make_throttle(Clock())
    fail(throttle, 5, ip="1.1.1.1")

    assert throttle.retry_after("1.1.1.1", "ayse") > 0
    assert (
        throttle.retry_after("2.2.2.2", "ayse") == 0
    )  # hesabın meşru sahibi başka yerden girebilir


def test_dagitik_deneme_hesap_sayacina_takilir():
    throttle = make_throttle(Clock())
    for i in range(20):
        throttle.record_failure(f"10.0.0.{i}", "ayse")  # her IP yalnızca 1 kez denedi

    assert throttle.retry_after("10.9.9.9", "ayse") > 0  # hesap kimden olursa olsun engelli
    assert throttle.retry_after("10.9.9.9", "burak") == 0


def test_parola_puskurtme_ip_sayacina_takilir():
    throttle = make_throttle(Clock())
    for i in range(40):
        throttle.record_failure("1.1.1.1", f"kullanici{i}")  # her hesaba yalnızca 1 deneme

    assert throttle.retry_after("1.1.1.1", "tamamen.yeni") > 0
    assert throttle.retry_after("2.2.2.2", "tamamen.yeni") == 0


def test_basarili_giris_yalnizca_cift_sayacini_sifirlar():
    throttle = make_throttle(Clock())
    fail(throttle, 4)

    throttle.record_success("1.1.1.1", "ayse")
    fail(throttle, 4)  # çift sayacı sıfırlandığı için 4 daha serbest

    assert throttle.retry_after("1.1.1.1", "ayse") == 0
    # ama hesap sayacı sıfırlanmadı: 8 hata birikti
    fail(throttle, 12, ip="9.9.9.9")
    assert throttle.retry_after("3.3.3.3", "ayse") > 0


def test_kullanici_adi_uydurarak_bellek_sisirilemez():
    clock = Clock()
    throttle = make_throttle(clock)

    for i in range(LoginThrottle.MAX_KEYS * 2):
        throttle.record_failure(f"ip{i % 7}", f"uydurma{i}")

    assert len(throttle._events) <= LoginThrottle.MAX_KEYS


def test_suresi_dolan_anahtarlar_temizlenir():
    clock = Clock()
    throttle = make_throttle(clock, window_s=10)
    fail(throttle, 3)
    clock.now += 11

    assert throttle.retry_after("1.1.1.1", "ayse") == 0
    assert throttle._events == {}


def test_engel_hesabin_var_olup_olmadigina_bakmaz():
    throttle = make_throttle(Clock())
    fail(throttle, 5, user="var.olan")
    fail(throttle, 5, user="hic.olmayan")

    assert throttle.retry_after("1.1.1.1", "var.olan") == throttle.retry_after(
        "1.1.1.1", "hic.olmayan"
    )
