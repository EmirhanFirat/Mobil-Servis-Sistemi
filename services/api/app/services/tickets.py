"""Talep iş mantığı: görünürlük, oluşturma, durum geçişi, atama, yönetici düzeltmesi.

Her yazma işlemi tek bir veritabanı işleminde yapılır ve olay geçmişine (ticket_events) kayıt
düşer. Durum değiştiren işlemler satırı kilitler; iki kişi aynı anda aynı talebi üstlenemez.
"""

from typing import Literal
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select, true
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domain.vocabulary import STATUS_LABELS, Role, TicketStatus
from app.domain.workflow import (
    TRANSITIONS,
    Actor,
    TicketState,
    allowed_transitions,
    can_assign,
    can_edit_fields,
)
from app.errors import AppError, conflict, forbidden, not_found
from app.models import Team, Ticket, TicketEvent, User
from app.schemas import (
    AssignRequest,
    EventOut,
    TicketCreate,
    TicketDetail,
    TicketPatch,
    TicketSummary,
)

Scope = Literal["mine", "queue"]

_SUMMARY_LOAD = (
    joinedload(Ticket.created_by),
    joinedload(Ticket.assignee),
    joinedload(Ticket.team),
)


def to_actor(user: User) -> Actor:
    return Actor(id=user.id, role=user.role, team_ids=frozenset(team.id for team in user.teams))


def to_state(ticket: Ticket) -> TicketState:
    return TicketState(
        status=ticket.status,
        created_by_id=ticket.created_by_id,
        team_id=ticket.team_id,
        assignee_id=ticket.assignee_id,
    )


def _visible(user: User) -> ColumnElement[bool]:
    """Kullanıcının görebileceği talepler; domain.workflow.can_view kuralının SQL karşılığı."""
    if user.role is Role.ADMIN:
        return true()
    clauses = [Ticket.created_by_id == user.id]
    if user.role is Role.TECHNICIAN and user.teams:
        clauses.append(Ticket.team_id.in_([team.id for team in user.teams]))
    return or_(*clauses)


def list_tickets(
    db: Session,
    user: User,
    *,
    scope: Scope | None,
    statuses: list[TicketStatus] | None,
    limit: int,
    offset: int,
) -> tuple[list[Ticket], int]:
    conditions = [_visible(user)]
    if scope == "mine":
        conditions.append(Ticket.created_by_id == user.id)
    elif scope == "queue":
        if user.role is Role.ADMIN:
            conditions.append(Ticket.team_id.is_not(None))
        else:
            conditions.append(Ticket.team_id.in_([team.id for team in user.teams]))
    if statuses:
        conditions.append(Ticket.status.in_(statuses))

    total = db.scalar(select(func.count()).select_from(Ticket).where(*conditions)) or 0
    tickets = db.scalars(
        select(Ticket)
        .where(*conditions)
        .options(*_SUMMARY_LOAD)
        .order_by(Ticket.created_at.desc(), Ticket.number.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(tickets), total


def get_visible_ticket(db: Session, user: User, ticket_id: UUID, *, lock: bool = False) -> Ticket:
    """Talebi getirir. Görme yetkisi yoksa 'yok' gibi davranır (404); varlığı sızdırılmaz."""
    stmt = select(Ticket).where(Ticket.id == ticket_id, _visible(user))
    if lock:
        stmt = stmt.with_for_update(of=Ticket)
    else:
        stmt = stmt.options(
            *_SUMMARY_LOAD, selectinload(Ticket.events).joinedload(TicketEvent.actor)
        )
    ticket = db.scalar(stmt)
    if ticket is None:
        raise not_found("Talep bulunamadı.")
    return ticket


def _add_event(ticket: Ticket, actor: User | None, kind: str, **data: object) -> None:
    clean = {key: value for key, value in data.items() if value is not None}
    ticket.events.append(TicketEvent(actor_id=actor.id if actor else None, kind=kind, data=clean))


def _add_assignee_event(ticket: Ticket, actor: User, old: User | None, new: User | None) -> None:
    """Görevli değişimi. Adlar o anki görüntü olarak saklanır; ad değişse geçmiş bozulmaz."""
    _add_event(
        ticket,
        actor,
        "assignee_changed",
        **{
            "from": str(old.id) if old else None,
            "from_name": old.display_name if old else None,
            "to": str(new.id) if new else None,
            "to_name": new.display_name if new else None,
        },
    )


def create_ticket(db: Session, user: User, data: TicketCreate) -> Ticket:
    ticket = Ticket(
        title=data.title,
        description=data.description,
        location=data.location,
        created_by_id=user.id,
        status=TicketStatus.NEW,
        missing_info=[],
    )
    _add_event(ticket, user, "created")
    db.add(ticket)
    db.commit()
    return ticket


def transition_ticket(
    db: Session, user: User, ticket_id: UUID, to: TicketStatus, note: str | None
) -> Ticket:
    ticket = get_visible_ticket(db, user, ticket_id, lock=True)
    old = ticket.status

    if to not in allowed_transitions(to_actor(user), to_state(ticket)):
        if (old, to) in TRANSITIONS:
            # Geçiş bu durumda tanımlı ama bu kullanıcı veya bağlam için değil.
            raise forbidden("Bu geçişi yapma yetkin yok.")
        raise conflict(
            "invalid_transition",
            f"'{STATUS_LABELS[old]}' durumundan '{STATUS_LABELS[to]}' durumuna geçilemez.",
        )

    previous_assignee = ticket.assignee  # değişiklikten önce; olay adı anlık görüntü olarak saklar
    ticket.status = to
    if to is TicketStatus.NEEDS_REVIEW:
        ticket.review_required = True
        ticket.assignee_id = None
    elif old is TicketStatus.NEEDS_REVIEW:
        ticket.review_required = False
    if (
        old is TicketStatus.ASSIGNED
        and to is TicketStatus.IN_PROGRESS
        and ticket.assignee_id is None
    ):
        ticket.assignee_id = user.id  # görevli işi üstlenir
    if old is TicketStatus.IN_PROGRESS and to is TicketStatus.ASSIGNED:
        ticket.assignee_id = None  # iş kuyruğa geri bırakıldı

    _add_event(ticket, user, "status_changed", **{"from": old.value, "to": to.value, "note": note})
    if ticket.assignee_id != (previous_assignee.id if previous_assignee else None):
        # Görevli ya temizlendi ya da işi üstlenen kullanıcı oldu.
        _add_assignee_event(
            ticket, user, previous_assignee, user if ticket.assignee_id == user.id else None
        )
    db.commit()
    return ticket


def assign_ticket(db: Session, user: User, ticket_id: UUID, data: AssignRequest) -> Ticket:
    ticket = get_visible_ticket(db, user, ticket_id, lock=True)
    if not can_assign(to_actor(user), to_state(ticket)):
        if user.role is not Role.ADMIN:
            raise forbidden("Atama yalnızca yöneticiler içindir.")
        raise conflict("not_assignable", "Çözülmüş veya kapatılmış talep yeniden atanamaz.")

    team = db.get(Team, data.team_id)
    if team is None:
        raise AppError(422, "invalid_team", "Ekip bulunamadı.")

    assignee = None
    if data.assignee_id is not None:
        assignee = db.scalar(
            select(User).options(selectinload(User.teams)).where(User.id == data.assignee_id)
        )
        valid = (
            assignee is not None
            and assignee.is_active
            and assignee.role is Role.TECHNICIAN
            and any(t.id == team.id for t in assignee.teams)
        )
        if not valid:
            raise AppError(
                422,
                "invalid_assignee",
                "Görevli, seçilen ekibin aktif bir teknik görevlisi olmalı.",
            )

    old_team = db.get(Team, ticket.team_id) if ticket.team_id else None
    old_assignee = ticket.assignee
    old_assignee_id = old_assignee.id if old_assignee else None
    new_assignee_id = assignee.id if assignee else None
    old_status = ticket.status

    if (
        old_status is TicketStatus.ASSIGNED
        and ticket.team_id == team.id
        and old_assignee_id == new_assignee_id
    ):
        return ticket  # değişiklik yok; olay üretme (tekrar çağrı güvenli)

    ticket.team_id = team.id
    ticket.assignee_id = new_assignee_id
    ticket.status = TicketStatus.ASSIGNED
    ticket.review_required = False

    if old_team is None or old_team.id != team.id:
        _add_event(
            ticket,
            user,
            "team_changed",
            **{"from": old_team.code if old_team else None, "to": team.code, "note": data.note},
        )
    if old_assignee_id != new_assignee_id:
        _add_assignee_event(ticket, user, old_assignee, assignee)
    if old_status is not TicketStatus.ASSIGNED:
        _add_event(
            ticket,
            user,
            "status_changed",
            **{"from": old_status.value, "to": TicketStatus.ASSIGNED.value},
        )
    db.commit()
    return ticket


def patch_ticket(db: Session, user: User, ticket_id: UUID, patch: TicketPatch) -> Ticket:
    ticket = get_visible_ticket(db, user, ticket_id, lock=True)
    if not can_edit_fields(to_actor(user), to_state(ticket)):
        if user.role is not Role.ADMIN:
            raise forbidden("Düzeltme yalnızca yöneticiler içindir.")
        raise conflict("not_editable", "Kapatılmış talep düzeltilemez.")

    fields = patch.model_fields_set
    if ("priority" in fields and patch.priority is None) or (
        "missing_info" in fields and patch.missing_info is None
    ):
        raise AppError(422, "invalid_field", "Öncelik ve eksik bilgi boş bırakılamaz.")

    if "priority" in fields and patch.priority != ticket.priority:
        _add_event(
            ticket,
            user,
            "field_changed",
            field="priority",
            **{"from": ticket.priority.value, "to": patch.priority.value, "note": patch.note},
        )
        ticket.priority = patch.priority
    if "category" in fields:
        new_category = patch.category
        if new_category != ticket.category:
            _add_event(
                ticket,
                user,
                "field_changed",
                field="category",
                **{
                    "from": ticket.category.value if ticket.category else None,
                    "to": new_category.value if new_category else None,
                    "note": patch.note,
                },
            )
            ticket.category = new_category
    if "missing_info" in fields:
        new_labels = sorted({item.value for item in patch.missing_info or []})
        if new_labels != sorted(ticket.missing_info):
            _add_event(
                ticket,
                user,
                "field_changed",
                field="missing_info",
                **{"from": sorted(ticket.missing_info), "to": new_labels, "note": patch.note},
            )
            ticket.missing_info = new_labels
    db.commit()
    return ticket


def to_summary(ticket: Ticket) -> TicketSummary:
    return TicketSummary.model_validate(ticket)


def to_detail(ticket: Ticket, user: User) -> TicketDetail:
    actor = to_actor(user)
    state = to_state(ticket)
    allowed = allowed_transitions(actor, state)
    return TicketDetail(
        **TicketSummary.model_validate(ticket).model_dump(),
        description=ticket.description,
        allowed_transitions=[status for status in TicketStatus if status in allowed],
        can_assign=can_assign(actor, state),
        can_edit=can_edit_fields(actor, state),
        events=[EventOut.model_validate(event) for event in ticket.events],
    )
