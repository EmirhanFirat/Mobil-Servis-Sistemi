"""Oturum belirteci parola sürümüne bağlıdır: parola değişince eski belirteçler geçersiz olur."""

from datetime import UTC, datetime, timedelta

import jwt

from app import security
from app.config import Settings


def forge(user_id, settings: Settings, **claims) -> dict[str, str]:
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=5), **claims}
    token = jwt.encode(
        payload, settings.secret_key.get_secret_value(), algorithm=security.JWT_ALGORITHM
    )
    return {"Authorization": f"Bearer {token}"}


def login(api, username: str, password: str) -> str:
    response = api.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_parola_surumu_olmayan_belirtec_reddedilir(api, make_user, settings):
    """Geçerli imzalı ama `pv` taşımayan (eski biçim) belirteç kabul edilmez."""
    user = make_user("ayse")

    assert api.get("/auth/me", headers=forge(user.id, settings)).status_code == 401


def test_yanlis_parola_surumlu_belirtec_reddedilir(api, make_user, settings):
    user = make_user("ayse")

    response = api.get("/auth/me", headers=forge(user.id, settings, pv="0" * 16))

    assert response.status_code == 401


def test_dogru_parola_surumlu_belirtec_calisir(api, make_user, settings):
    user = make_user("ayse")
    headers = forge(user.id, settings, pv=security.password_version(user.password_hash))

    assert api.get("/auth/me", headers=headers).status_code == 200


def test_sayisal_parola_surumu_reddedilir(api, make_user, settings):
    user = make_user("ayse")

    assert api.get("/auth/me", headers=forge(user.id, settings, pv=123)).status_code == 401


def test_parola_degisince_eski_belirtec_gecersiz_olur(api, make_user, password, db):
    user = make_user("ayse")
    old_token = login(api, "ayse", password)
    old = {"Authorization": f"Bearer {old_token}"}
    assert api.get("/auth/me", headers=old).status_code == 200

    user.password_hash = security.hash_password("yepyeni-parola-789")
    db.add(user)
    db.commit()

    assert api.get("/auth/me", headers=old).status_code == 401
    new_token = login(api, "ayse", "yepyeni-parola-789")  # yeni parolayla giriş çalışır
    assert api.get("/auth/me", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200


def test_parola_degisikligi_baska_kullanicinin_belirtecini_etkilemez(api, make_user, password, db):
    ayse = make_user("ayse")
    make_user("burak")
    burak_token = login(api, "burak", password)

    ayse.password_hash = security.hash_password("yepyeni-parola-789")
    db.add(ayse)
    db.commit()

    assert (
        api.get("/auth/me", headers={"Authorization": f"Bearer {burak_token}"}).status_code == 200
    )


def test_belirtec_parola_ozetini_tasimaz(api, make_user, password, settings):
    user = make_user("ayse")
    token = login(api, "ayse", password)

    claims = jwt.decode(
        token, settings.secret_key.get_secret_value(), algorithms=[security.JWT_ALGORITHM]
    )

    assert claims["pv"] == security.password_version(user.password_hash)
    assert len(claims["pv"]) == 16
    assert user.password_hash not in token
    assert user.password_hash[-20:] not in claims["pv"]
    assert set(claims) == {"sub", "pv", "iat", "exp"}


def test_ayni_ozet_ayni_surumu_farkli_ozet_farkli_surumu_verir():
    first = security.hash_password("ayni-parola-123")
    second = security.hash_password("ayni-parola-123")  # tuz farklı: özet farklı

    assert security.password_version(first) == security.password_version(first)
    assert security.password_version(first) != security.password_version(second)
