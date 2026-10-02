from datetime import UTC, datetime
from decimal import Decimal
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
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.decision.contract import CallStatus, StrategyName
from app.domain.decision_jobs import ApplyOutcome, JobOutcome, JobStatus
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


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DecisionJob(Base):
    """Bir talep için karar işi. Talep açılırken AYNI işlemde kaydedilir; ayrı bir worker işler.

    Kalıcı durum (pending/running/succeeded/failed) ve kira (locked_by/locked_until) sayesinde
    worker çökse veya yeniden başlasa iş kaybolmaz; kira süresi dolan 'running' iş yeniden alınır.
    Bir talep için aynı anda en çok bir açık (pending/running) iş olabilir.
    """

    __tablename__ = "decision_jobs"
    __table_args__ = (
        _in_check("status", JobStatus),
        _in_check("outcome", JobOutcome),
        Index("ix_decision_jobs_status_run_after", "status", "run_after"),
        Index("ix_decision_jobs_ticket_id", "ticket_id"),
        Index(
            "uq_decision_jobs_open_ticket",
            "ticket_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    # Kayıt defterindeki çalıştırılacak strateji adı (rule_based, mock_hybrid, ...).
    strategy: Mapped[str] = mapped_column(String(30))
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus), default=JobStatus.PENDING)
    outcome: Mapped[JobOutcome | None] = mapped_column(_enum(JobOutcome))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
    locked_by: Mapped[str | None] = mapped_column(String(100))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Kısa hata kodu/özeti; kullanıcı metni veya sağlayıcı yanıt gövdesi içermez.
    last_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Decision(Base):
    """Karar motorunun İLK ve değişmeyen tahmini. Talebin güncel alanları ayrıdır: insan
    düzeltmesi olay geçmişine yazılır, bu kayıt hiçbir zaman ezilmez ve otomatik "gerçek etiket"
    sayılmaz. Sağlayıcıya özgü olasılık/güven değerleri `judgments` içinde, karar alanlarından
    ayrı saklanır."""

    __tablename__ = "decisions"
    __table_args__ = (
        _in_check("strategy", StrategyName),
        _in_check("category", Category),
        _in_check("priority", Priority),
        _in_check("applied_outcome", ApplyOutcome),
        Index("ix_decisions_ticket_id", "ticket_id"),
        # Her iş için tek karar: aynı iş iki kez tamamlanamaz (çift uygulama/olay önlenir).
        Index("uq_decisions_job_id", "job_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)  # Decision.decision_id (sözleşme)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("decision_jobs.id", ondelete="CASCADE"))
    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    strategy: Mapped[StrategyName] = mapped_column(_enum(StrategyName))
    category: Mapped[Category | None] = mapped_column(_enum(Category))
    priority: Mapped[Priority | None] = mapped_column(_enum(Priority))
    missing_info: Mapped[list[str]] = mapped_column(JSONB, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean)
    review_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    judgments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    providers: Mapped[list[str]] = mapped_column(JSONB, default=list)
    model_versions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_mock: Mapped[bool] = mapped_column(Boolean)
    applied_outcome: Mapped[ApplyOutcome] = mapped_column(_enum(ApplyOutcome))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelCall(Base):
    """Bir sağlayıcı çağrısı denemesi (başarılı veya başarısız). Retry ve fallback dahil her deneme
    ayrı satırdır; toplam maliyet bu satırların toplamıdır. cost_usd NULL = maliyet bilinmiyor
    (sıfır değil)."""

    __tablename__ = "model_calls"
    __table_args__ = (
        _in_check("status", CallStatus),
        _in_check("strategy", StrategyName),
        Index("ix_model_calls_job_id", "job_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)  # CallRecord.call_id
    job_id: Mapped[UUID] = mapped_column(ForeignKey("decision_jobs.id", ondelete="CASCADE"))
    decision_id: Mapped[UUID | None] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"))
    strategy: Mapped[StrategyName] = mapped_column(_enum(StrategyName))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(100))
    questions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[CallStatus] = mapped_column(_enum(CallStatus))
    attempt: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    provider_duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    usage_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    request_id: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(String(300))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
