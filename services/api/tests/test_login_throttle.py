"""Giriş ucunda kaba kuvvet koruması (gerçek veritabanıyla). Sınırlayıcının saf mantığı
tests/test_hardening.py içindedir."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.vocabulary import Role
from app.hardening import LoginThrottle, get_login_throttle
from app.services import accounts


@pytest.fixture
def settings() -> Settings:
    """Küçük sınırlar: çift 3, hesap 6, IP 10 başarısız deneme."""
    return Settings(_env_file=None, login_pair_limit=3, login_account_limit=6, login_ip_limit=10)


def login(client: TestClient, username: str, password: str):
    return client.post("/auth/login", json={"username": username, "password": password})


def fail(client: TestClient, username: str, times: int) -> None:
    for _ in range(times):
        assert login(client, username, "yanlis-parola").status_code == 401


def other_ip(api: TestClient, ip: str) -> TestClient:
    return TestClient(api.app, client=(ip, 50000))


def test_sinira_kadar_hatali_giris_401_sinirdan_sonra_429(api, make_user, password):
    make_user("ayse")

    fail(api, "ayse", 3)
    blocked = login(api, "ayse", "yanlis-parola")

    assert blocked.status_code == 429
    body = blocked.json()
    assert body["code"] == "too_many_attempts"
    assert "dakika" in body["detail"]
    assert 1 <= int(blocked.headers["retry-after"]) <= 900


def test_engelliyken_dogru_parola_da_reddedilir(api, make_user, password):
    make_user("ayse")
    fail(api, "ayse", 3)

    response = login(api, "ayse", password)

    assert response.status_code == 429
    assert "access_token" not in response.text


def test_engel_hesabin_var_olup_olmadigini_ele_vermez(api, make_user, password):
    make_user("ayse")
    fail(api, "ayse", 3)
    fail(api, "hic.olmayan", 3)

    existing = login(api, "ayse", password)
    missing = login(api, "hic.olmayan", password)

    assert existing.status_code == missing.status_code == 429
    assert existing.json() == missing.json()


def test_engelliyken_parola_dogrulamasi_hic_calismaz(api, make_user, monkeypatch):
    make_user("ayse")
    fail(api, "ayse", 3)
    calls = []
    monkeypatch.setattr(accounts, "verify_password", lambda *a: calls.append(a) or True)
    monkeypatch.setattr(accounts, "burn_password_check", lambda *a: calls.append(a))

    assert login(api, "ayse", "herhangi").status_code == 429

    assert calls == []  # Argon2 maliyeti ödenmez: engel, CPU tüketme saldırısını da yavaşlatır


def test_basarili_giris_cift_sayacini_sifirlar(api, make_user, password):
    make_user("ayse")

    fail(api, "ayse", 2)
    assert login(api, "ayse", password).status_code == 200
    fail(api, "ayse", 2)  # sayaç sıfırlandığı için yeniden 2 hata serbest

    assert login(api, "ayse", password).status_code == 200


def test_baska_ip_ayni_hesaba_girebilir(api, make_user, password):
    make_user("ayse")
    fail(api, "ayse", 3)  # testclient IP'si engelli

    assert login(api, "ayse", password).status_code == 429
    assert login(other_ip(api, "203.0.113.9"), "ayse", password).status_code == 200


def test_dagitik_deneme_hesap_sayacina_takilir(api, make_user, password):
    make_user("ayse")
    fail(other_ip(api, "203.0.113.1"), "ayse", 3)
    fail(other_ip(api, "203.0.113.2"), "ayse", 3)  # 6 hata: hesap sınırı doldu

    third_ip = login(other_ip(api, "203.0.113.3"), "ayse", password)

    assert third_ip.status_code == 429


def test_parola_puskurtme_ip_sayacina_takilir(api, make_user, password):
    make_user("ayse")
    for i in range(10):
        assert login(api, f"kullanici{i}", "yanlis-parola").status_code == 401

    assert login(api, "ayse", password).status_code == 429  # aynı IP, hiç denenmemiş gerçek hesap


def test_gecersiz_govde_deneme_sayilmaz(api, make_user, password):
    make_user("ayse")
    for _ in range(12):
        assert api.post("/auth/login", json={"username": "ayse"}).status_code == 422

    assert login(api, "ayse", password).status_code == 200


def test_devre_disi_hesabin_dogru_parolayla_denemeleri_de_sayilir(api, make_user, password):
    make_user("pasif", Role.REQUESTER, is_active=False)

    fail_codes = [login(api, "pasif", password).status_code for _ in range(3)]

    assert fail_codes == [401, 401, 401]
    assert login(api, "pasif", password).status_code == 429


def test_engel_suresi_dolunca_giris_yeniden_calisir(api, make_user, password):
    class Clock:
        now = 5000.0

        def __call__(self) -> float:
            return self.now

    clock = Clock()
    throttle = LoginThrottle(pair_limit=3, account_limit=6, ip_limit=10, window_s=900, clock=clock)
    api.app.dependency_overrides[get_login_throttle] = lambda: throttle
    make_user("ayse")
    fail(api, "ayse", 3)
    assert login(api, "ayse", password).status_code == 429

    clock.now += 901

    assert login(api, "ayse", password).status_code == 200


def test_engel_diger_uclari_etkilemez(api, make_user, password, auth):
    user = make_user("ayse")
    token_headers = auth(user)
    fail(api, "ayse", 3)

    assert api.get("/auth/me", headers=token_headers).status_code == 200  # var olan oturum sürer
    assert api.get("/health").status_code == 200
