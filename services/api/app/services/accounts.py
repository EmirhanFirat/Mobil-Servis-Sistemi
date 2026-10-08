"""Kullanıcı, giriş ve ekip üyeliği işlemleri."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.domain.vocabulary import Role, TicketStatus
from app.errors import AppError, conflict, not_found, unauthorized
from app.models import Team, TeamMembership, Ticket, User
from app.schemas import UserCreate, UserPatch
from app.security import burn_password_check, hash_password, verify_password

_OPEN_STATUSES = (TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS)


def authenticate(db: Session, username: str, password: str) -> User:
    """Kullanıcı adı/parola doğrular. Hata mesajı ve süre hesabın var olup olmadığını ele vermez."""
    user = db.scalar(
        select(User).options(selectinload(User.teams)).where(User.username == username)
    )
    if user is None:
        burn_password_check(password)
    elif verify_password(user.password_hash, password) and user.is_active and not user.is_demo:
        return user
    raise unauthorized("Kullanıcı adı veya parola hatalı.")


def list_users(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .options(selectinload(User.teams))
            .order_by(User.display_name, User.username)
        )
    )


def create_user(db: Session, data: UserCreate) -> User:
    user = User(
        username=data.username,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict("username_taken", "Bu kullanıcı adı zaten kullanılıyor.") from None
    return get_user(db, user.id)


def get_user(db: Session, user_id: UUID) -> User:
    user = db.scalar(select(User).options(selectinload(User.teams)).where(User.id == user_id))
    if user is None:
        raise not_found("Kullanıcı bulunamadı.")
    return user


def patch_user(db: Session, admin: User, user_id: UUID, patch: UserPatch) -> User:
    user = get_user(db, user_id)
    if user.id == admin.id and (
        patch.is_active is False or (patch.role is not None and patch.role is not Role.ADMIN)
    ):
        raise conflict(
            "self_lockout",
            "Kendi hesabını devre dışı bırakamaz veya yönetici rolünden çıkaramazsın.",
        )
    if patch.display_name is not None:
        user.display_name = patch.display_name
    if patch.role is not None:
        user.role = patch.role
    if patch.is_active is not None:
        user.is_active = patch.is_active
    db.commit()
    return get_user(db, user_id)


def list_teams(db: Session) -> list[Team]:
    return list(db.scalars(select(Team).options(selectinload(Team.members)).order_by(Team.name)))


def _get_team(db: Session, team_id: UUID) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise not_found("Ekip bulunamadı.")
    return team


def add_member(db: Session, team_id: UUID, user_id: UUID) -> None:
    team = _get_team(db, team_id)
    user = get_user(db, user_id)
    if user.role is not Role.TECHNICIAN:
        raise AppError(422, "not_technician", "Yalnızca teknik görevliler ekibe üye olabilir.")
    if db.get(TeamMembership, (user.id, team.id)) is None:
        db.add(TeamMembership(user_id=user.id, team_id=team.id))
        db.commit()


def remove_member(db: Session, team_id: UUID, user_id: UUID) -> None:
    team = _get_team(db, team_id)
    membership = db.get(TeamMembership, (user_id, team.id))
    if membership is None:
        return
    has_open_work = db.scalar(
        select(Ticket.id)
        .where(
            Ticket.team_id == team.id,
            Ticket.assignee_id == user_id,
            Ticket.status.in_(_OPEN_STATUSES),
        )
        .limit(1)
    )
    if has_open_work is not None:
        raise conflict(
            "has_open_tickets",
            "Bu görevlinin ekipte açık işi var. Önce taleplerini başka bir görevliye ata.",
        )
    db.delete(membership)
    db.commit()
