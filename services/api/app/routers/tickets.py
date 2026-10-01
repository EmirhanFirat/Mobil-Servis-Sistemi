from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.deps import AdminUser, CurrentUser, DbSession
from app.domain.vocabulary import TicketStatus
from app.schemas import (
    AssignRequest,
    TicketCreate,
    TicketDetail,
    TicketList,
    TicketPatch,
    TransitionRequest,
)
from app.services import tickets as svc

router = APIRouter(prefix="/tickets", tags=["talepler"])


@router.post("", response_model=TicketDetail, status_code=201, summary="Yeni talep aç")
def create_ticket(data: TicketCreate, user: CurrentUser, db: DbSession) -> TicketDetail:
    ticket = svc.create_ticket(db, user, data)
    return svc.to_detail(svc.get_visible_ticket(db, user, ticket.id), user)


@router.get("", response_model=TicketList, summary="Görebildiğin talepler")
def list_tickets(
    user: CurrentUser,
    db: DbSession,
    scope: Annotated[
        svc.Scope | None,
        Query(description="mine: açtıklarım, queue: ekip kuyruğum. Boşsa görebildiğin hepsi."),
    ] = None,
    status: Annotated[list[TicketStatus] | None, Query(description="Durum süzgeci")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TicketList:
    tickets, total = svc.list_tickets(
        db, user, scope=scope, statuses=status, limit=limit, offset=offset
    )
    return TicketList(
        items=[svc.to_summary(ticket) for ticket in tickets],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{ticket_id}", response_model=TicketDetail, summary="Talep ayrıntısı ve geçmişi")
def get_ticket(ticket_id: UUID, user: CurrentUser, db: DbSession) -> TicketDetail:
    return svc.to_detail(svc.get_visible_ticket(db, user, ticket_id), user)


@router.post(
    "/{ticket_id}/transitions", response_model=TicketDetail, summary="Talebin durumunu değiştir"
)
def transition_ticket(
    ticket_id: UUID, data: TransitionRequest, user: CurrentUser, db: DbSession
) -> TicketDetail:
    svc.transition_ticket(db, user, ticket_id, data.to, data.note)
    return svc.to_detail(svc.get_visible_ticket(db, user, ticket_id), user)


@router.post(
    "/{ticket_id}/assignment",
    response_model=TicketDetail,
    summary="Talebi ekibe (ve isteğe bağlı görevliye) ata — yönetici",
)
def assign_ticket(
    ticket_id: UUID, data: AssignRequest, admin: AdminUser, db: DbSession
) -> TicketDetail:
    svc.assign_ticket(db, admin, ticket_id, data)
    return svc.to_detail(svc.get_visible_ticket(db, admin, ticket_id), admin)


@router.patch(
    "/{ticket_id}",
    response_model=TicketDetail,
    summary="Öncelik, kategori ve eksik bilgiyi düzelt — yönetici",
)
def patch_ticket(
    ticket_id: UUID, data: TicketPatch, admin: AdminUser, db: DbSession
) -> TicketDetail:
    svc.patch_ticket(db, admin, ticket_id, data)
    return svc.to_detail(svc.get_visible_ticket(db, admin, ticket_id), admin)
