"""Veritabanı ulaşılamazken API ve worker davranışı (veritabanı gerektirmez).

Bağlam: Docker Desktop yeniden başlayınca veritabanı konteyneri kapalı kalıyordu ve giriş isteği
dakikalarca asılı kalıyordu: psycopg'un varsayılan bağlantı bekleme süresi Windows'ta ~130 sn'dir,
istemci 15 sn'de "Sunucu zamanında yanıt vermedi" diyordu. Düzeltme: bağlantıya üst süre + açık 503.
"""

import socket
import threading
import time
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session

from app import worker
from app.config import Settings
from app.db import get_db, make_engine
from app.errors import DATABASE_UNAVAILABLE_CODE, DATABASE_UNAVAILABLE_MESSAGE

SECRET = "hunter2-cok-gizli-parola"


def closed_port() -> int:
    """Hiçbir şeyin dinlemediği bir yerel port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def dead_settings(timeout: int = 1) -> Settings:
    url = f"postgresql+psycopg://talepakis:{SECRET}@127.0.0.1:{closed_port()}/talepakis"
    return Settings(_env_file=None, database_url=url, database_connect_timeout_s=timeout)


class TestConnectTimeout:
    def test_kapali_veritabanina_baglanti_uzun_asili_kalmaz_hizla_hata_verir(self):
        engine = make_engine(dead_settings(timeout=1))
        started = time.perf_counter()

        with pytest.raises(OperationalError):
            engine.connect()

        # Üst süre olmadan psycopg Windows'ta ~130 sn bekler.
        assert time.perf_counter() - started < 15

    def test_ust_sure_ayardan_gelir_ve_motora_connect_args_ile_verilir(self, monkeypatch):
        captured = {}

        def fake_create_engine(url, **kwargs):
            captured.update(url=url, **kwargs)
            return object()

        monkeypatch.setattr("app.db.create_engine", fake_create_engine)

        make_engine(dead_settings(timeout=7))

        assert captured["connect_args"] == {"connect_timeout": 7}
        assert captured["pool_pre_ping"] is True

    def test_varsayilan_ust_sure_5_sn(self):
        assert Settings(_env_file=None).database_connect_timeout_s == 5

    @pytest.mark.parametrize("value", [0, -1, 61])
    def test_gecersiz_ust_sure_reddedilir(self, value):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, database_connect_timeout_s=value)


def _app_with_dead_db(app: FastAPI, settings: Settings) -> TestClient:
    engine = make_engine(settings)

    def _session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _session
    return TestClient(app, raise_server_exceptions=False)


class TestDatabaseUnavailableResponse:
    def test_giris_veritabani_yokken_asilmaz_503_ve_acik_kod_doner(self, app):
        client = _app_with_dead_db(app, dead_settings(timeout=1))
        started = time.perf_counter()

        response = client.post("/auth/login", json={"username": "ayse", "password": "x"})

        assert time.perf_counter() - started < 15  # istemcinin 15 sn zaman aşımından kısa
        assert response.status_code == 503
        assert response.json() == {
            "detail": DATABASE_UNAVAILABLE_MESSAGE,
            "code": DATABASE_UNAVAILABLE_CODE,
        }
        assert response.headers["retry-after"] == "5"

    def test_yanit_ve_baslik_baglanti_bilgisi_ya_da_parola_sizdirmaz(self, app):
        client = _app_with_dead_db(app, dead_settings(timeout=1))

        response = client.post("/auth/login", json={"username": "ayse", "password": "x"})

        everything = response.text + str(dict(response.headers))
        assert SECRET not in everything
        assert "127.0.0.1" not in everything and "postgresql" not in everything

    def test_saglik_ucu_hazir_degil_der_ve_asilmaz(self, app):
        client = _app_with_dead_db(app, dead_settings(timeout=1))
        started = time.perf_counter()

        response = client.get("/health/ready")

        assert time.perf_counter() - started < 15
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable", "database": "unavailable"}

    def test_surec_ayakta_ucu_veritabanina_bagli_degildir(self, app):
        client = _app_with_dead_db(app, dead_settings(timeout=1))

        assert client.get("/health").status_code == 200

    def test_veritabani_disindaki_hatalar_503e_cevrilmez(self, app):
        def boom() -> None:
            raise RuntimeError("kod hatası")

        app.add_api_route("/__hata", boom)
        client = TestClient(app, raise_server_exceptions=False)

        assert client.get("/__hata").status_code == 500

    @pytest.mark.parametrize(
        "error",
        [
            OperationalError("select 1", {}, Exception(f"password={SECRET} host=10.1.2.3")),
            PoolTimeoutError("QueuePool limit of size 5 overflow 10 reached"),
        ],
        ids=["baglanti_hatasi", "havuz_zaman_asimi"],
    )
    def test_iki_veritabani_hata_turu_de_ayni_503_yaniti_verir(self, app, error):
        def boom() -> None:
            raise error

        app.add_api_route("/__db", boom)
        response = TestClient(app, raise_server_exceptions=False).get("/__db")

        assert response.status_code == 503
        assert response.json()["code"] == DATABASE_UNAVAILABLE_CODE
        assert SECRET not in response.text and "10.1.2.3" not in response.text


class _Stop:
    """threading.Event benzeri: bekleme sürelerini kaydeder, belirli sayıda bekleme sonrası durur."""

    def __init__(self, stop_after_waits: int):
        self.waits: list[float] = []
        self._limit = stop_after_waits

    def is_set(self) -> bool:
        return len(self.waits) >= self._limit

    def wait(self, seconds: float) -> bool:
        self.waits.append(seconds)
        return self.is_set()


def _run(monkeypatch, steps, stop, poll_seconds=2.0):
    """`steps`: process_next'in sırayla vereceği sonuçlar (Exception örneği fırlatılır)."""
    queue = list(steps)

    def fake(*_args, **_kwargs):
        step = queue.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    monkeypatch.setattr(worker, "process_next", fake)
    return worker.run_forever(
        lambda: None,
        worker_id="test",
        lease=None,
        poll_seconds=poll_seconds,
        stop=stop,  # type: ignore[arg-type]
    )


class TestWorkerSurvivesOutage:
    def test_veritabani_yokken_cokmez_ustel_bekler_geri_gelince_surer(self, monkeypatch, capsys):
        down = OperationalError("select", {}, Exception("baglanti reddedildi"))
        stop = _Stop(stop_after_waits=4)

        processed = _run(monkeypatch, [down, down, down, True, False], stop)

        assert processed == 1  # veritabanı dönünce iş işlendi
        assert stop.waits[:3] == [4.0, 8.0, 16.0]  # 2 sn * 2^n, üstel
        out = capsys.readouterr().out
        assert out.count("Veritabanına ulaşılamıyor") == 3
        assert "yeniden ulaşıldı" in out
        assert "baglanti reddedildi" not in out  # sürücü hata metni (parola içerebilir) yazılmaz

    def test_bekleme_ustten_sinirlidir(self, monkeypatch):
        down = OperationalError("select", {}, Exception("x"))
        stop = _Stop(stop_after_waits=10)

        _run(monkeypatch, [down] * 10 + [False], stop)

        assert max(stop.waits) == worker.DB_OUTAGE_MAX_WAIT_S

    def test_havuz_zaman_asimi_da_ayni_sekilde_beklenir(self, monkeypatch):
        stop = _Stop(stop_after_waits=1)

        _run(monkeypatch, [PoolTimeoutError("havuz dolu"), False], stop)

        assert stop.waits == [4.0]

    def test_kod_hatasi_gizlenmez_yukari_cikar(self, monkeypatch):
        with pytest.raises(RuntimeError, match="kod hatası"):
            _run(monkeypatch, [RuntimeError("kod hatası")], _Stop(stop_after_waits=5))

    def test_kesinti_sonrasi_sayac_sifirlanir(self, monkeypatch):
        down = OperationalError("select", {}, Exception("x"))
        stop = _Stop(stop_after_waits=3)

        _run(monkeypatch, [down, True, down, False], stop)

        assert stop.waits[:2] == [4.0, 4.0]  # ikinci kesinti yine 4 sn'den başlar

    def test_tek_seferlik_mod_veritabani_yokken_net_mesajla_1_doner(self, monkeypatch, capsys):
        monkeypatch.setattr(worker, "get_engine", lambda: object())

        def fail(*_a, **_k):
            raise OperationalError("select", {}, Exception("x"))

        monkeypatch.setattr(worker, "drain", fail)

        code = worker.main(["--once"])

        assert code == 1
        assert "Veritabanına ulaşılamıyor" in capsys.readouterr().out

    def test_gercek_event_ile_durdurulabilir(self, monkeypatch):
        stop = threading.Event()
        stop.set()

        assert _run(monkeypatch, [], stop) == 0  # hiç dönmeden çıkar
