import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import __version__
from app.config import Settings, get_settings


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


def test_ayarlar_onekli_ortam_degiskenlerinden_okunur(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TALEPAKIS_ENVIRONMENT", "production")
    monkeypatch.setenv("TALEPAKIS_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")

    settings = Settings(_env_file=None)

    assert settings.environment == "production"
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/x"


def test_gecersiz_ortam_degeri_reddedilir(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TALEPAKIS_ENVIRONMENT", "canli")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
