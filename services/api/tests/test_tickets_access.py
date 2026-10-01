"""Yetkisiz erişim testleri: başka kullanıcının veya ekibin talebine ulaşılamamalı."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.domain.vocabulary import Role
from app.domain.workflow import can_view
from app.models import Ticket
from app.schemas import AssignRequest
from app.services import tickets as svc


@pytest.fixture
def world(db, make_user, make_ticket, teams):
    """Üç ekibe yayılmış kullanıcılar ve talepler.

    - ayse, burak: talep sahipleri
    - elektrik, tesisat: farklı ekiplerin görevlileri; admin: yönetici
    """
    users = {
        "ayse": make_user("ayse"),
        "burak": make_user("burak"),
        "elektrik": make_user("elektrik.usta", Role.TECHNICIAN, "electrical"),
        "tesisat": make_user("tesisat.usta", Role.TECHNICIAN, "plumbing"),
        "admin": make_user("yonetici", Role.ADMIN),
    }
    t = {
        # ayse'nin yeni (henüz ekibi yok)
        "ayse_yeni": make_ticket(users["ayse"], "Ayşe yeni"),
        # burak'ın elektrik ekibine atanmış
        "burak_elektrik": make_ticket(users["burak"], "Burak elektrik"),
        # ayse'nin tesisat ekibine atanmış
        "ayse_tesisat": make_ticket(users["ayse"], "Ayşe tesisat"),
        # görevlinin kendi açtığı talep (başka ekipte)
        "elektrik_kendi": make_ticket(users["elektrik"], "Elektrikçinin kendi talebi"),
    }
    svc.assign_ticket(
        db, users["admin"], t["burak_elektrik"].id, AssignRequest(team_id=teams["electrical"].id)
    )
    svc.assign_ticket(
        db, users["admin"], t["ayse_tesisat"].id, AssignRequest(team_id=teams["plumbing"].id)
    )
    svc.assign_ticket(
        db, users["admin"], t["elektrik_kendi"].id, AssignRequest(team_id=teams["plumbing"].id)
    )
    return users, t


def ids(response) -> set[str]:
    return {item["id"] for item in response.json()["items"]}


def test_talep_sahibi_yalnizca_kendi_taleplerini_listeler(api, auth, world):
    users, t = world

    response = api.get("/tickets", headers=auth(users["ayse"]))

    assert response.status_code == 200
    assert ids(response) == {str(t["ayse_yeni"].id), str(t["ayse_tesisat"].id)}
    assert response.json()["total"] == 2


def test_baskasinin_talebi_404_ve_olmayan_talepten_ayirt_edilemez(api, auth, world):
    users, t = world
    headers = auth(users["ayse"])

    foreign = api.get(f"/tickets/{t['burak_elektrik'].id}", headers=headers)
    missing = api.get(f"/tickets/{uuid4()}", headers=headers)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()  # varlık sızdırılmaz


def test_talep_sahibi_baskasinin_talebinin_durumunu_degistiremez(api, auth, world):
    users, t = world

    response = api.post(
        f"/tickets/{t['burak_elektrik'].id}/transitions",
        json={"to": "closed"},
        headers=auth(users["ayse"]),
    )

    assert response.status_code == 404


def test_talep_sahibi_ata_veya_duzeltemez_yonetici_ucu_kapali(api, auth, world, teams):
    users, t = world
    headers = auth(users["ayse"])
    own, foreign = t["ayse_yeni"].id, t["burak_elektrik"].id
    body = {"team_id": str(teams["it"].id)}

    assert api.post(f"/tickets/{own}/assignment", json=body, headers=headers).status_code == 403
    assert (
        api.patch(f"/tickets/{own}", json={"priority": "high"}, headers=headers).status_code == 403
    )
    # Yönetici olmayan için uç nokta zaten kapalı; talebin varlığı hakkında bilgi vermez.
    assert api.post(f"/tickets/{foreign}/assignment", json=body, headers=headers).status_code == 403
    assert (
        api.patch(f"/tickets/{foreign}", json={"priority": "high"}, headers=headers).status_code
        == 403
    )


def test_servis_katmani_yonetici_olmayana_da_atama_ve_duzeltme_vermez(db, world, teams):
    """HTTP katmanı atlansa bile (ör. başka bir çağıran) servis kuralı korur: çift kilit."""
    from app.errors import AppError
    from app.schemas import TicketPatch

    users, t = world
    ticket_id = t["burak_elektrik"].id

    for actor in (users["elektrik"], users["burak"]):  # ekip görevlisi, talep sahibi
        with pytest.raises(AppError) as assign_error:
            svc.assign_ticket(db, actor, ticket_id, AssignRequest(team_id=teams["it"].id))
        with pytest.raises(AppError) as patch_error:
            svc.patch_ticket(db, actor, ticket_id, TicketPatch(priority="high"))
        assert assign_error.value.status_code == patch_error.value.status_code == 403


def test_gorevli_yalnizca_ekibinin_ve_kendi_acti_gi_talepleri_gorur(api, auth, world):
    users, t = world

    elektrik = api.get("/tickets", headers=auth(users["elektrik"]))
    tesisat = api.get("/tickets", headers=auth(users["tesisat"]))

    # Elektrikçi: elektrik ekibinin talebi + kendi açtığı talep
    assert ids(elektrik) == {str(t["burak_elektrik"].id), str(t["elektrik_kendi"].id)}
    # Tesisatçı: tesisat ekibinin iki talebi (ayse_tesisat, elektrik_kendi)
    assert ids(tesisat) == {str(t["ayse_tesisat"].id), str(t["elektrik_kendi"].id)}


def test_gorevli_ekibine_dusmemis_yeni_talebi_goremez(api, auth, world):
    users, t = world

    response = api.get(f"/tickets/{t['ayse_yeni'].id}", headers=auth(users["elektrik"]))

    assert response.status_code == 404


def test_gorevli_baska_ekibin_talebinde_okuyamaz_ve_gecis_yapamaz(api, auth, world):
    users, t = world
    headers = auth(users["elektrik"])
    foreign = t["ayse_tesisat"].id

    assert api.get(f"/tickets/{foreign}", headers=headers).status_code == 404
    response = api.post(
        f"/tickets/{foreign}/transitions", json={"to": "in_progress"}, headers=headers
    )
    assert response.status_code == 404


def test_gorevli_atama_yapamaz(api, auth, world, teams):
    users, t = world

    response = api.post(
        f"/tickets/{t['burak_elektrik'].id}/assignment",
        json={"team_id": str(teams["it"].id)},
        headers=auth(users["elektrik"]),
    )

    assert response.status_code == 403


def test_yonetici_tum_talepleri_gorur(api, auth, world):
    users, t = world

    response = api.get("/tickets", headers=auth(users["admin"]))

    assert ids(response) == {str(ticket.id) for ticket in t.values()}


def test_listeleme_gorunurluk_kurali_alan_kuraliyla_birebir_ayni(api, auth, db, world):
    """SQL süzgeci (liste) ile saf kural (can_view) hiçbir kullanıcı için ayrışmamalı."""
    users, _ = world
    db.expire_all()
    tickets = db.scalars(select(Ticket)).all()

    for user in users.values():
        db.refresh(user)
        actor = svc.to_actor(user)
        expected = {str(ticket.id) for ticket in tickets if can_view(actor, svc.to_state(ticket))}

        listed = ids(api.get("/tickets?limit=100", headers=auth(user)))

        assert listed == expected, user.username
        for ticket in tickets:
            status = api.get(f"/tickets/{ticket.id}", headers=auth(user)).status_code
            assert (status == 200) == (str(ticket.id) in expected), (user.username, ticket.number)


def test_kuyruk_ve_benim_kapsamlari(api, auth, world):
    users, t = world

    queue = api.get("/tickets?scope=queue", headers=auth(users["elektrik"]))
    mine = api.get("/tickets?scope=mine", headers=auth(users["elektrik"]))
    admin_queue = api.get("/tickets?scope=queue", headers=auth(users["admin"]))
    requester_queue = api.get("/tickets?scope=queue", headers=auth(users["ayse"]))

    assert ids(queue) == {str(t["burak_elektrik"].id)}
    assert ids(mine) == {str(t["elektrik_kendi"].id)}
    assert ids(admin_queue) == {
        str(t["burak_elektrik"].id),
        str(t["ayse_tesisat"].id),
        str(t["elektrik_kendi"].id),
    }  # ekibe düşmüş olanlar
    assert ids(requester_queue) == set()


def test_durum_suzgeci_ve_sayfalama(api, auth, world):
    users, t = world
    headers = auth(users["admin"])

    new_only = api.get("/tickets?status=new", headers=headers)
    assert ids(new_only) == {str(t["ayse_yeni"].id)}

    page1 = api.get("/tickets?limit=2&offset=0", headers=headers).json()
    page2 = api.get("/tickets?limit=2&offset=2", headers=headers).json()
    assert page1["total"] == page2["total"] == 4
    assert len(page1["items"]) == len(page2["items"]) == 2
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})
    # En yeni önce
    numbers = [i["number"] for i in page1["items"]] + [i["number"] for i in page2["items"]]
    assert numbers == sorted(numbers, reverse=True)


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=101", "offset=-1", "status=bilinmeyen", "scope=hepsi"]
)
def test_gecersiz_sorgu_parametreleri_422(api, auth, world, query):
    users, _ = world

    assert api.get(f"/tickets?{query}", headers=auth(users["admin"])).status_code == 422


def test_gecersiz_talep_kimligi_422(api, auth, world):
    users, _ = world

    assert api.get("/tickets/1", headers=auth(users["admin"])).status_code == 422


def test_baska_kullanicilara_gosterilen_kisi_bilgisi_asgari(api, auth, world):
    users, t = world

    detail = api.get(f"/tickets/{t['ayse_yeni'].id}", headers=auth(users["ayse"])).json()

    assert set(detail["created_by"]) == {"id", "display_name", "role"}


UNAUTHENTICATED = [
    ("GET", "/tickets"),
    ("POST", "/tickets"),
    ("GET", f"/tickets/{uuid4()}"),
    ("POST", f"/tickets/{uuid4()}/transitions"),
    ("POST", f"/tickets/{uuid4()}/assignment"),
    ("PATCH", f"/tickets/{uuid4()}"),
    ("GET", "/admin/users"),
    ("POST", "/admin/users"),
    ("PATCH", f"/admin/users/{uuid4()}"),
    ("GET", "/admin/teams"),
    ("PUT", f"/admin/teams/{uuid4()}/members/{uuid4()}"),
    ("DELETE", f"/admin/teams/{uuid4()}/members/{uuid4()}"),
    ("GET", "/auth/me"),
]


@pytest.mark.parametrize(("method", "path"), UNAUTHENTICATED)
def test_kimliksiz_istekler_401(api, method, path):
    response = api.request(method, path, json={})

    assert response.status_code == 401
