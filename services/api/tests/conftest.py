import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _izole_ortam(monkeypatch):
    """Geliştiricinin kendi TALEPAKIS_* değişkenleri testleri etkilemesin."""
    for ad in [ad for ad in os.environ if ad.startswith("TALEPAKIS_")]:
        monkeypatch.delenv(ad)


@pytest.fixture
def app() -> FastAPI:
    """Ayarları .env dosyasından okumayan uygulama."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
