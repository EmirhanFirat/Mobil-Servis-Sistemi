import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app import __version__
from app.config import DEV_SECRET_KEY, Settings, get_settings
from app.db import get_db

STRONG_KEY = "k" * 40


def test_health_servisin_ayakta_oldugunu_soyler(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "talepakis-api",
        "version": __version__,
        "environment": "development",
    }


def test_health_ayarlardaki_ortami_gosterir(app: FastAPI, client: TestClient):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, environment="test")

    assert client.get("/health").json()["environment"] == "test"


def test_ready_veritabani_calisiyorsa_200(api: TestClient):
    response = api.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_ready_veritabani_yoksa_503(app: FastAPI, client: TestClient):
    class KopukOturum:
        def execute(self, *args, **kwargs):
            raise OperationalError("select 1", {}, Exception("baglanti yok"))

    app.dependency_overrides[get_db] = lambda: KopukOturum()

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}


def test_ayarlar_onekli_ortam_degiskenlerinden_okunur(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TALEPAKIS_ENVIRONMENT", "production")
    monkeypatch.setenv("TALEPAKIS_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    monkeypatch.setenv("TALEPAKIS_SECRET_KEY", STRONG_KEY)

    settings = Settings(_env_file=None)

    assert settings.environment == "production"
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/x"
    assert settings.secret_key.get_secret_value() == STRONG_KEY


def test_gecersiz_ortam_degeri_reddedilir(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TALEPAKIS_ENVIRONMENT", "canli")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("zayif", [DEV_SECRET_KEY, "kisa-anahtar"])
def test_uretimde_zayif_veya_varsayilan_anahtar_reddedilir(zayif: str):
    with pytest.raises(ValidationError, match="TALEPAKIS_SECRET_KEY"):
        Settings(_env_file=None, environment="production", secret_key=zayif)


def test_gelistirmede_varsayilan_anahtar_kabul_edilir():
    assert Settings(_env_file=None).secret_key.get_secret_value() == DEV_SECRET_KEY


def test_sozluk_ucu_kodlari_ve_turkce_adlari_dondurur(client: TestClient):
    body = client.get("/meta/vocabulary").json()

    assert {item["code"] for item in body["statuses"]} == {
        "new", "needs_review", "assigned", "in_progress", "resolved", "closed",
    }  # fmt: skip
    assert {"code": "in_progress", "label": "İşlemde"} in body["statuses"]
    assert body["category_default_team"]["electrical"] == "electrical"
    assert body["category_default_team"]["other"] == "general"
