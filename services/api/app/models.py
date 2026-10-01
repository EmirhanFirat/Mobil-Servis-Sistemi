from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain.vocabulary import Category, Priority, Role, TicketStatus


def _enum(cls: type[StrEnum]) -> Enum:
    """Metin olarak saklanan enum (PostgreSQL ENUM tipi değil).

    CHECK kısıtını Enum üretmez (Alembic ile çift kısıt çıkarıyor); `_in_check` ile açıkça eklenir.
    """
    return Enum(
        cls,
        native_enum=False,
        create_constraint=False,
        length=20,
        values_callable=lambda e: [member.value for member in e],
    )


def _in_check(column: str, cls: type[StrEnum]) -> CheckConstraint:
    values = ", ".join(f"'{member.value}'" for member in cls)
    return CheckConstraint(f"{column} IN ({values})", name=column)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (_in_check("role", Role),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teams: Mapped[list["Team"]] = relationship(
        secondary="team_memberships", back_populates="members", order_by="Team.name"
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(100))

    members: Mapped[list[User]] = relationship(
        secondary="team_memberships", back_populates="teams", order_by="User.display_name"
    )


class TeamMembership(Base):
    __tablename__ = "team_memberships"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        _in_check("status", TicketStatus),
        _in_check("category", Category),
        _in_check("priority", Priority),
        Index("ix_tickets_created_by_id", "created_by_id"),
        Index("ix_tickets_team_id_status", "team_id", "status"),
        Index("ix_tickets_assignee_id", "assignee_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # Okunur numara (TA-0001). Erişim kararları her zaman id ve yetki kurallarıyla verilir.
    number: Mapped[int] = mapped_column(Integer, Identity(start=1), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(200))
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[TicketStatus] = mapped_column(_enum(TicketStatus), default=TicketStatus.NEW)
    category: Mapped[Category | None] = mapped_column(_enum(Category))
    priority: Mapped[Priority] = mapped_column(_enum(Priority), default=Priority.NORMAL)
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"))
    assignee_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    missing_info: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    review_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])
    team: Mapped[Team | None] = relationship()
    events: Mapped[list["TicketEvent"]] = relationship(
        back_populates="ticket", order_by="TicketEvent.id", cascade="all, delete-orphan"
    )


class TicketEvent(Base):
    """Talep geçmişi: kim, ne zaman, neyi değiştirdi. Kayıtlar eklenir, değiştirilmez."""

    __tablename__ = "ticket_events"
    __table_args__ = (Index("ix_ticket_events_ticket_id", "ticket_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1), primary_key=True)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    # Sistem olayları (ileride karar motoru) için boş olabilir.
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped[Ticket] = relationship(back_populates="events")
    actor: Mapped[User | None] = relationship()
