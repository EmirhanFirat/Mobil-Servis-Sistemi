from uuid import uuid4

import pytest

from app.domain import vocabulary as v
from app.domain.vocabulary import Role, TicketStatus
from app.domain.workflow import (
    TRANSITIONS,
    Actor,
    TicketState,
    allowed_transitions,
    can_assign,
    can_edit_fields,
    can_view,
)

S = TicketStatus
TEAM = uuid4()
OTHER_TEAM = uuid4()


def actor(role: Role, *teams) -> Actor:
    return Actor(id=uuid4(), role=role, team_ids=frozenset(teams))


def ticket(
    status: TicketStatus, owner: Actor, team=TEAM, assignee: Actor | None = None
) -> TicketState:
    return TicketState(
        status=status,
        created_by_id=owner.id,
        team_id=team,
        assignee_id=assignee.id if assignee else None,
    )


@pytest.fixture
def owner() -> Actor:
    return actor(Role.REQUESTER)


@pytest.fixture
def admin() -> Actor:
    return actor(Role.ADMIN)


@pytest.fixture
def tech() -> Actor:
    return actor(Role.TECHNICIAN, TEAM)


def test_tablodaki_tum_durumlar_gecerli_ve_kapali_talepten_cikis_yok():
    for source, target in TRANSITIONS:
        assert isinstance(source, TicketStatus) and isinstance(target, TicketStatus)
        assert source is not S.CLOSED
        assert source is not target


def test_yeni_atandi_gecisi_tabloda_yok_atama_islemiyle_yapilir(admin, owner):
    assert (S.NEW, S.ASSIGNED) not in TRANSITIONS
    assert (S.NEEDS_REVIEW, S.ASSIGNED) not in TRANSITIONS
    assert S.ASSIGNED not in allowed_transitions(admin, ticket(S.NEW, owner, team=None))


def test_talep_sahibi_yeni_talebi_yalnizca_kapatabilir(owner):
    assert allowed_transitions(owner, ticket(S.NEW, owner, team=None)) == {S.CLOSED}


def test_talep_sahibi_isi_baslatamaz_ve_cozemez(owner):
    assert allowed_transitions(owner, ticket(S.ASSIGNED, owner)) == set()
    assert allowed_transitions(owner, ticket(S.IN_PROGRESS, owner)) == set()


def test_talep_sahibi_cozulen_talebi_kapatir_veya_yeniden_acar(owner):
    assert allowed_transitions(owner, ticket(S.RESOLVED, owner)) == {S.CLOSED, S.IN_PROGRESS}


def test_baskasinin_talebinde_sahip_sifati_yok():
    owner, stranger = actor(Role.REQUESTER), actor(Role.REQUESTER)
    assert allowed_transitions(stranger, ticket(S.RESOLVED, owner)) == set()
    assert not can_view(stranger, ticket(S.RESOLVED, owner))


def test_gorevli_ekibinin_atanmis_talebini_baslatabilir(tech, owner):
    assert S.IN_PROGRESS in allowed_transitions(tech, ticket(S.ASSIGNED, owner))


def test_gorevli_baska_ekibin_talebine_dokunamaz(owner):
    outsider = actor(Role.TECHNICIAN, OTHER_TEAM)
    state = ticket(S.ASSIGNED, owner)
    assert allowed_transitions(outsider, state) == set()
    assert not can_view(outsider, state)


def test_gorevli_baska_gorevliye_atanmis_isi_ustlenemez(tech, owner):
    colleague = actor(Role.TECHNICIAN, TEAM)
    state = ticket(S.ASSIGNED, owner, assignee=colleague)
    assert S.IN_PROGRESS not in allowed_transitions(tech, state)
    assert S.IN_PROGRESS in allowed_transitions(colleague, state)


def test_islemdeki_isi_yalnizca_ustlenen_gorevli_cozer(tech, owner):
    colleague = actor(Role.TECHNICIAN, TEAM)
    state = ticket(S.IN_PROGRESS, owner, assignee=tech)
    assert {S.RESOLVED, S.ASSIGNED} <= allowed_transitions(tech, state)
    assert allowed_transitions(colleague, state) == set()


def test_gorevli_yanlis_ekibi_incelemeye_gonderebilir(tech, owner):
    assert S.NEEDS_REVIEW in allowed_transitions(tech, ticket(S.ASSIGNED, owner))


def test_gorevli_talep_sahibi_sifatiyla_kendi_talebini_kapatabilir():
    tech = actor(Role.TECHNICIAN, TEAM)
    state = ticket(S.RESOLVED, tech, team=OTHER_TEAM)
    assert S.CLOSED in allowed_transitions(tech, state)  # OWNER sıfatı, rol önemsiz


def test_yonetici_gorevlisiz_atanmis_talebi_isleme_alamaz(admin, owner):
    assert S.IN_PROGRESS not in allowed_transitions(admin, ticket(S.ASSIGNED, owner))
    worker = actor(Role.TECHNICIAN, TEAM)
    assert S.IN_PROGRESS in allowed_transitions(admin, ticket(S.ASSIGNED, owner, assignee=worker))


@pytest.mark.parametrize("status", [s for s in TicketStatus if s is not S.CLOSED])
def test_yonetici_kapali_olmayan_her_talebi_kapatabilir(admin, owner, status):
    assert S.CLOSED in allowed_transitions(admin, ticket(status, owner))


def test_kapali_talepte_kimse_gecis_yapamaz(admin, tech, owner):
    state = ticket(S.CLOSED, owner)
    for who in (admin, tech, owner):
        assert allowed_transitions(who, state) == set()


def test_atama_ve_duzeltme_yalnizca_yonetici_ve_uygun_durumda(admin, tech, owner):
    for status in (S.NEW, S.NEEDS_REVIEW, S.ASSIGNED, S.IN_PROGRESS):
        assert can_assign(admin, ticket(status, owner))
        assert not can_assign(tech, ticket(status, owner))
        assert not can_assign(owner, ticket(status, owner))
    for status in (S.RESOLVED, S.CLOSED):
        assert not can_assign(admin, ticket(status, owner))
    assert can_edit_fields(admin, ticket(S.RESOLVED, owner))
    assert not can_edit_fields(admin, ticket(S.CLOSED, owner))
    assert not can_edit_fields(owner, ticket(S.NEW, owner))


def test_yonetici_her_talebi_gorur_gorevli_yalnizca_ekibini(admin, tech, owner):
    assert can_view(admin, ticket(S.NEW, owner, team=None))
    assert can_view(tech, ticket(S.ASSIGNED, owner))
    assert not can_view(tech, ticket(S.NEW, owner, team=None))  # ekibe henüz düşmemiş


def test_sozluk_kategorilerin_hepsi_gecerli_bir_ekibe_baglanir():
    assert set(v.CATEGORY_DEFAULT_TEAM) == set(v.Category)
    assert set(v.CATEGORY_DEFAULT_TEAM.values()) <= set(v.TEAM_NAMES)


def test_sozlukteki_her_kod_icin_turkce_ad_var():
    assert set(v.STATUS_LABELS) == set(v.TicketStatus)
    assert set(v.PRIORITY_LABELS) == set(v.Priority)
    assert set(v.CATEGORY_LABELS) == set(v.Category)
    assert set(v.ROLE_LABELS) == set(v.Role)
    assert set(v.MISSING_INFO_LABELS) == set(v.MissingInfo)
    assert set(v.TEAM_NAMES) == set(v.TeamCode)
