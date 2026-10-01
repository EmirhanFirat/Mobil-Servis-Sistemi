"""Talep durum geçişleri: kim, hangi durumdan hangisine geçebilir.

Kurallar tek bir tabloda ve saf Python'dadır; veritabanına ve HTTP'ye bağlı değildir. Model
çıktısı hiçbir geçişi veya erişimi tek başına yetkilendiremez.

Bir kullanıcı bir talep üzerinde üç "sıfattan" biriyle işlem yapar:
- OWNER: talebi açan kişi (rolü ne olursa olsun)
- TECHNICIAN: teknik görevli rolünde ve talebin ekibinin üyesi
- ADMIN: yönetici rolü

Yeni/İnceleme bekliyor → Atandı geçişi bu tabloda yoktur; ekip bilgisi gerektirdiği için
"atama" işlemiyle (services/tickets.assign_ticket) yapılır.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.vocabulary import Role, TicketStatus

S = TicketStatus


class Capacity(StrEnum):
    OWNER = "owner"
    TECHNICIAN = "technician"
    ADMIN = "admin"


C = Capacity

# (nereden, nereye) -> bu geçişi yapabilecek sıfatlar
TRANSITIONS: dict[tuple[TicketStatus, TicketStatus], frozenset[Capacity]] = {
    (S.NEW, S.NEEDS_REVIEW): frozenset({C.ADMIN}),
    (S.NEW, S.CLOSED): frozenset({C.OWNER, C.ADMIN}),
    (S.NEEDS_REVIEW, S.CLOSED): frozenset({C.OWNER, C.ADMIN}),
    (S.ASSIGNED, S.IN_PROGRESS): frozenset({C.TECHNICIAN, C.ADMIN}),
    (S.ASSIGNED, S.NEEDS_REVIEW): frozenset({C.TECHNICIAN, C.ADMIN}),
    (S.ASSIGNED, S.CLOSED): frozenset({C.ADMIN}),
    (S.IN_PROGRESS, S.RESOLVED): frozenset({C.TECHNICIAN, C.ADMIN}),
    (S.IN_PROGRESS, S.ASSIGNED): frozenset({C.TECHNICIAN, C.ADMIN}),
    (S.IN_PROGRESS, S.CLOSED): frozenset({C.ADMIN}),
    (S.RESOLVED, S.CLOSED): frozenset({C.OWNER, C.ADMIN}),
    (S.RESOLVED, S.IN_PROGRESS): frozenset({C.OWNER, C.ADMIN}),
}

# Yönetici ekibi (yeniden) atayabilir; kapanmış ve çözülmüş talepler yeniden atanmaz.
ASSIGNABLE_STATUSES = frozenset({S.NEW, S.NEEDS_REVIEW, S.ASSIGNED, S.IN_PROGRESS})

# Yönetici alan düzeltmesi (öncelik, kategori, eksik bilgi) yapabilir; kapalı talepte yapamaz.
EDITABLE_STATUSES = frozenset(set(TicketStatus) - {S.CLOSED})


@dataclass(frozen=True)
class Actor:
    id: UUID
    role: Role
    team_ids: frozenset[UUID]


@dataclass(frozen=True)
class TicketState:
    status: TicketStatus
    created_by_id: UUID
    team_id: UUID | None
    assignee_id: UUID | None


def capacities(actor: Actor, ticket: TicketState) -> set[Capacity]:
    result: set[Capacity] = set()
    if ticket.created_by_id == actor.id:
        result.add(C.OWNER)
    if actor.role is Role.ADMIN:
        result.add(C.ADMIN)
    if (
        actor.role is Role.TECHNICIAN
        and ticket.team_id is not None
        and ticket.team_id in actor.team_ids
    ):
        result.add(C.TECHNICIAN)
    return result


def can_view(actor: Actor, ticket: TicketState) -> bool:
    """Talebi görebilir mi? Sahibi, ekibin görevlisi veya yönetici."""
    return bool(capacities(actor, ticket))


def _technician_may_act(actor: Actor, ticket: TicketState, target: TicketStatus) -> bool:
    """Yalnızca TECHNICIAN sıfatı için ek bağlam kuralları (OWNER ve ADMIN bunlardan muaf)."""
    if ticket.status is S.ASSIGNED and target is S.IN_PROGRESS:
        # Başka görevliye atanmış işi üstlenemez.
        return ticket.assignee_id in (None, actor.id)
    if ticket.status is S.IN_PROGRESS and target in (S.RESOLVED, S.ASSIGNED):
        # İşlemdeki işi yalnızca üstlenen görevli çözer veya kuyruğa geri bırakır.
        return ticket.assignee_id == actor.id
    return True


def allowed_transitions(actor: Actor, ticket: TicketState) -> set[TicketStatus]:
    held = capacities(actor, ticket)
    allowed: set[TicketStatus] = set()
    for (source, target), who in TRANSITIONS.items():
        if source is not ticket.status:
            continue
        for capacity in held & who:
            if capacity is C.TECHNICIAN and not _technician_may_act(actor, ticket, target):
                continue
            if (
                capacity is C.ADMIN
                and source is S.ASSIGNED
                and target is S.IN_PROGRESS
                and ticket.assignee_id is None
            ):
                # İşlemdeki her talebin bir sorumlusu olmalı; yönetici önce görevli atar.
                continue
            allowed.add(target)
    return allowed


def can_assign(actor: Actor, ticket: TicketState) -> bool:
    return actor.role is Role.ADMIN and ticket.status in ASSIGNABLE_STATUSES


def can_edit_fields(actor: Actor, ticket: TicketState) -> bool:
    return actor.role is Role.ADMIN and ticket.status in EDITABLE_STATUSES
