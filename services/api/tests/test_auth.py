from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app import security
from app.config import Settings
from app.domain.vocabulary import Role

GENERIC_ERROR = "Kullanıcı adı veya parola hatalı."


def login(api: TestClient, username: str, password: str):
    return api.post("/auth/login", json={"username": username, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_dogru_bilgilerle_giris_belirtec_ve_kullanici_doner(api, make_user, password):
    make_user("ayse", Role.REQUESTER)

    response = login(api, "ayse", password)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["username"] == "ayse"
    assert body["user"]["role"] == "requester"
    assert "password" not in response.text.lower()


def test_kullanici_adi_buyuk_kucuk_harfe_duyarsiz(api, make_user, password):
    make_user("ayse")

    assert login(api, "  AYSE ", password).status_code == 200


def test_yanlis_parola_ile_olmayan_kullanici_ayni_yaniti_alir(api, make_user, password):
    make_user("ayse")

    wrong_password = login(api, "ayse", "yanlis-parola")
    unknown_user = login(api, "yok.kimse", password)

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json()["detail"] == GENERIC_ERROR


def test_olmayan_kullanicida_da_parola_maliyeti_odenir(api, make_user, password, monkeypatch):
    """Süre farkı hesabı ele vermesin: sahte kontrol yalnızca olmayan kullanıcıda çalışır."""
    from app.services import accounts

    calls = []
    monkeypatch.setattr(accounts, "burn_password_check", lambda pw: calls.append(pw))
    make_user("ayse")

    login(api, "yok.kimse", "x")
    login(api, "ayse", "yanlis")

    assert calls == ["x"]


def test_devre_disi_hesap_giris_yapamaz_ve_mesaj_ayni(api, make_user, password):
    make_user("pasif", is_active=False)

    response = login(api, "pasif", password)

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_ERROR


def test_eksik_alan_422(api):
    assert api.post("/auth/login", json={"username": "ayse"}).status_code == 422


def test_belirtecle_me_calisir(api, make_user, password):
    make_user("ayse")
    token = login(api, "ayse", password).json()["access_token"]

    response = api.get("/auth/me", headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["username"] == "ayse"


def test_belirtecsiz_istek_401_ve_bearer_basligi(api):
    response = api.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_bozuk_belirtec_reddedilir(api):
    assert api.get("/auth/me", headers=bearer("bu.bir.token-degil")).status_code == 401


def test_baska_anahtarla_imzalanmis_belirtec_reddedilir(api, make_user):
    user = make_user("ayse")
    forged = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(UTC) + timedelta(hours=1)},
        "saldirganin-anahtari-en-az-32-karakter-uzunlukta",
        algorithm="HS256",
    )

    assert api.get("/auth/me", headers=bearer(forged)).status_code == 401


def test_imzasiz_none_algoritmali_belirtec_reddedilir(api, make_user):
    user = make_user("ayse")
    unsigned = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(UTC) + timedelta(hours=1)},
        key=None,
        algorithm="none",
    )

    assert api.get("/auth/me", headers=bearer(unsigned)).status_code == 401


def test_suresi_dolmus_belirtec_reddedilir(api, make_user, settings: Settings):
    user = make_user("ayse")
    expired = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(UTC) - timedelta(seconds=5)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )

    response = api.get("/auth/me", headers=bearer(expired))

    assert response.status_code == 401


def test_suresiz_belirtec_reddedilir(api, make_user, settings: Settings):
    user = make_user("ayse")
    no_exp = jwt.encode(
        {"sub": str(user.id)}, settings.secret_key.get_secret_value(), algorithm="HS256"
    )

    assert api.get("/auth/me", headers=bearer(no_exp)).status_code == 401


def test_giris_sonrasi_devre_disi_birakilan_kullanicinin_belirteci_gecersiz(
    api, make_user, auth, db
):
    user = make_user("ayse")
    headers = auth(user)
    assert api.get("/auth/me", headers=headers).status_code == 200

    user.is_active = False
    db.commit()

    assert api.get("/auth/me", headers=headers).status_code == 401


def test_rol_belirtecten_degil_veritabanindan_okunur(api, make_user, auth, db):
    user = make_user("ayse", Role.REQUESTER)
    headers = auth(user)  # belirteç rol bilgisi taşımaz
    assert api.get("/admin/users", headers=headers).status_code == 403

    user.role = Role.ADMIN
    db.commit()

    assert api.get("/admin/users", headers=headers).status_code == 200


def test_silinmis_kullanicinin_belirteci_reddedilir(api, make_user, auth, db):
    user = make_user("ayse")
    headers = auth(user)
    db.delete(user)
    db.commit()

    assert api.get("/auth/me", headers=headers).status_code == 401


def test_parola_ozeti_dogrulanir_ve_bozuk_ozet_hata_firlatmaz():
    digest = security.hash_password("gizli-parola")

    assert digest != "gizli-parola"
    assert security.verify_password(digest, "gizli-parola")
    assert not security.verify_password(digest, "baska-parola")
    assert not security.verify_password("bu-bir-ozet-degil", "gizli-parola")


def test_ayni_parola_iki_kez_farkli_ozet_uretir():
    assert security.hash_password("ayni") != security.hash_password("ayni")


@pytest.mark.parametrize("sub", ["uuid-degil", ""])
def test_gecersiz_sub_iceren_belirtec_reddedilir(api, settings: Settings, sub: str):
    token = jwt.encode(
        {"sub": sub, "exp": datetime.now(UTC) + timedelta(hours=1)},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )

    assert api.get("/auth/me", headers=bearer(token)).status_code == 401
