"""Yönetici işlemleri: kullanıcı yönetimi ve ekip üyelikleri."""

import pytest
from sqlalchemy import select

from app.domain.vocabulary import Role
from app.models import User


@pytest.fixture
def people(make_user):
    return {
        "admin": make_user("yonetici", Role.ADMIN),
        "ayse": make_user("ayse"),
        "elektrik": make_user("elektrik.usta", Role.TECHNICIAN, "electrical"),
        "tesisat": make_user("tesisat.usta", Role.TECHNICIAN, "plumbing"),
    }


NEW_USER = {"username": "yeni.kisi", "display_name": "Yeni Kişi", "password": "gizli-parola-1"}


def login(api, username, password):
    return api.post("/auth/login", json={"username": username, "password": password})


@pytest.mark.parametrize("who", ["ayse", "elektrik"])
def test_yonetici_olmayan_hicbir_yonetim_ucuna_giremez(api, auth, people, teams, who):
    headers = auth(people[who])
    team, user = teams["electrical"].id, people["tesisat"].id
    calls = [
        ("GET", "/admin/users", None),
        ("POST", "/admin/users", NEW_USER),
        ("PATCH", f"/admin/users/{user}", {"is_active": False}),
        ("GET", "/admin/teams", None),
        ("PUT", f"/admin/teams/{team}/members/{user}", None),
        ("DELETE", f"/admin/teams/{team}/members/{user}", None),
    ]
    for method, path, body in calls:
        response = api.request(method, path, json=body, headers=headers)
        assert response.status_code == 403, (method, path)


def test_yonetici_kullanici_olusturur_ve_kullanici_giris_yapar(api, auth, people):
    response = api.post("/admin/users", json=NEW_USER, headers=auth(people["admin"]))

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "yeni.kisi" and body["role"] == "requester" and body["is_active"]
    assert "password" not in response.text.lower()
    assert login(api, "yeni.kisi", NEW_USER["password"]).status_code == 200


def test_parola_veritabaninda_ozet_olarak_saklanir(api, auth, people, db):
    api.post("/admin/users", json=NEW_USER, headers=auth(people["admin"]))

    stored = db.scalar(select(User.password_hash).where(User.username == "yeni.kisi"))

    assert stored != NEW_USER["password"]
    assert stored.startswith("$argon2")


def test_kullanici_adi_kucuk_harfe_cevrilir_ve_tekrar_edilemez(api, auth, people):
    headers = auth(people["admin"])
    first = api.post("/admin/users", json={**NEW_USER, "username": "Yeni.Kisi"}, headers=headers)
    again = api.post("/admin/users", json=NEW_USER, headers=headers)

    assert first.json()["username"] == "yeni.kisi"
    assert again.status_code == 409
    assert again.json()["code"] == "username_taken"


@pytest.mark.parametrize(
    "bad",
    [
        {"username": "ab"},
        {"username": "boşluk var"},
        {"username": "x" * 51},
        {"password": "kisa"},
        {"role": "superuser"},
        {"display_name": " "},
    ],
)
def test_gecersiz_kullanici_bilgisi_422(api, auth, people, bad):
    response = api.post("/admin/users", json={**NEW_USER, **bad}, headers=auth(people["admin"]))

    assert response.status_code == 422


def test_kullanicilar_listelenir_ekipleriyle(api, auth, people):
    response = api.get("/admin/users", headers=auth(people["admin"]))

    assert response.status_code == 200
    by_name = {u["username"]: u for u in response.json()}
    assert set(by_name) == {"yonetici", "ayse", "elektrik.usta", "tesisat.usta"}
    assert [t["code"] for t in by_name["elektrik.usta"]["teams"]] == ["electrical"]


def test_kullanici_rolu_degistirilir_ve_pasife_alinir(api, auth, people):
    headers = auth(people["admin"])
    ayse = people["ayse"].id

    promoted = api.patch(f"/admin/users/{ayse}", json={"role": "technician"}, headers=headers)
    deactivated = api.patch(f"/admin/users/{ayse}", json={"is_active": False}, headers=headers)

    assert promoted.json()["role"] == "technician"
    assert deactivated.json()["is_active"] is False
    assert login(api, "ayse", "test-parola-123").status_code == 401  # pasif hesap giremez


def test_yonetici_kendini_pasife_alamaz_veya_rolunu_dusuremez(api, auth, people):
    headers = auth(people["admin"])
    me = people["admin"].id

    deactivate = api.patch(f"/admin/users/{me}", json={"is_active": False}, headers=headers)
    demote = api.patch(f"/admin/users/{me}", json={"role": "requester"}, headers=headers)
    rename = api.patch(f"/admin/users/{me}", json={"display_name": "Yeni Ad"}, headers=headers)

    assert deactivate.status_code == demote.status_code == 409
    assert deactivate.json()["code"] == "self_lockout"
    assert rename.status_code == 200  # zararsız değişiklik serbest


def test_olmayan_kullanici_guncellenemez_404(api, auth, people):
    response = api.patch(
        "/admin/users/00000000-0000-0000-0000-000000000000",
        json={"is_active": False},
        headers=auth(people["admin"]),
    )

    assert response.status_code == 404


def test_ekipler_uyeleriyle_listelenir_ve_uyede_kullanici_adi_yok(api, auth, people):
    response = api.get("/admin/teams", headers=auth(people["admin"]))

    teams = {t["code"]: t for t in response.json()}
    assert set(teams) == {"electrical", "plumbing", "it", "cleaning", "general"}
    assert [m["display_name"] for m in teams["electrical"]["members"]] == ["Elektrik Usta"]
    assert set(teams["electrical"]["members"][0]) == {"id", "display_name", "role"}
    assert teams["it"]["members"] == []


def test_gorevli_ekibe_eklenir_tekrar_eklemek_zararsiz(api, auth, people, teams):
    headers = auth(people["admin"])
    url = f"/admin/teams/{teams['it'].id}/members/{people['elektrik'].id}"

    assert api.put(url, headers=headers).status_code == 204
    assert api.put(url, headers=headers).status_code == 204  # idempotent

    members = api.get("/admin/teams", headers=headers).json()
    it = next(t for t in members if t["code"] == "it")
    assert [m["display_name"] for m in it["members"]] == ["Elektrik Usta"]


def test_gorevli_olmayan_ekibe_uye_olamaz_422(api, auth, people, teams):
    response = api.put(
        f"/admin/teams/{teams['it'].id}/members/{people['ayse'].id}", headers=auth(people["admin"])
    )

    assert response.status_code == 422
    assert response.json()["code"] == "not_technician"


def test_olmayan_ekip_veya_kullanici_404(api, auth, people, teams):
    headers = auth(people["admin"])
    zero = "00000000-0000-0000-0000-000000000000"

    assert (
        api.put(f"/admin/teams/{zero}/members/{people['elektrik'].id}", headers=headers).status_code
        == 404
    )
    assert (
        api.put(f"/admin/teams/{teams['it'].id}/members/{zero}", headers=headers).status_code == 404
    )


def test_uyelikten_cikarilan_gorevli_ekip_taleplerini_goremez(
    api, auth, people, teams, make_ticket
):
    admin_headers = auth(people["admin"])
    ticket = make_ticket(people["ayse"])
    api.post(
        f"/tickets/{ticket.id}/assignment",
        json={"team_id": str(teams["electrical"].id)},
        headers=admin_headers,
    )
    tech = auth(people["elektrik"])
    assert api.get(f"/tickets/{ticket.id}", headers=tech).status_code == 200

    removed = api.delete(
        f"/admin/teams/{teams['electrical'].id}/members/{people['elektrik'].id}",
        headers=admin_headers,
    )

    assert removed.status_code == 204
    # Yetki üyelikten gelir ve her istekte veritabanından okunur; eski oturum da kapsamı kaybeder.
    assert api.get(f"/tickets/{ticket.id}", headers=tech).status_code == 404


def test_acik_isi_olan_gorevli_ekipten_cikarilamaz(api, auth, people, teams, make_ticket):
    admin_headers = auth(people["admin"])
    ticket = make_ticket(people["ayse"])
    api.post(
        f"/tickets/{ticket.id}/assignment",
        json={"team_id": str(teams["electrical"].id), "assignee_id": str(people["elektrik"].id)},
        headers=admin_headers,
    )
    url = f"/admin/teams/{teams['electrical'].id}/members/{people['elektrik'].id}"

    blocked = api.delete(url, headers=admin_headers)

    assert blocked.status_code == 409
    assert blocked.json()["code"] == "has_open_tickets"

    # İş başka birine/kuyruğa verilince çıkarılabilir
    api.post(f"/tickets/{ticket.id}/transitions", json={"to": "closed"}, headers=admin_headers)
    assert api.delete(url, headers=admin_headers).status_code == 204


def test_uye_olmayani_cikarmak_zararsiz(api, auth, people, teams):
    response = api.delete(
        f"/admin/teams/{teams['it'].id}/members/{people['elektrik'].id}",
        headers=auth(people["admin"]),
    )

    assert response.status_code == 204
