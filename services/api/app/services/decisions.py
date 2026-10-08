"""Karar işi hattı: kuyruğa alma, kira ile iş alma, model kararını kaydetme ve talebe uygulama.

İlkeler (AGENTS.md "Mimari ilkeler"):
- İş, talebi açan işlemde kaydedilir (`enqueue_job`); model çalışmasa da talep kaybolmaz.
- İşi worker alır: `FOR UPDATE SKIP LOCKED` ve kira (`locked_until`). Worker çökerse süresi dolan
  iş yeniden alınır; deneme hakkı bitince iş başarısız sayılır ve talep insana verilir.
- Model çağrısı SIRASINDA veritabanı kilidi tutulmaz: önce kısa bir okuma, sonra (kilitsiz)
  sağlayıcı çağrısı, sonunda tek işlemde kayıt. Sonuç kaydedilirken talep satırı kilitlenir ve
  uygunluk yeniden denetlenir.
- Karar yalnızca talep hâlâ "new" ve hiçbir insan değişikliği yokken talebe UYGULANIR. Aksi hâlde
  karar yine saklanır (araştırma ve yönetici görünürlüğü için) ama uygulanmaz; insan düzeltmesi
  asla ezilmez. İlk model kararı (`decisions`) hiçbir zaman değiştirilmez veya silinmez.
- Aynı iş iki kez tamamlanamaz (kira + `decisions.job_id` tekilliği): çift olay ve çift atama yok.
- Model kararı yalnızca ÖNERİDİR: ekip kategoriden deterministik kuralla bulunur (routing.py),
  görevli seçimi insanındır. Olay verisine inceleme nedenleri (enjeksiyon şüphesi vb.) konmaz;
  onlar yalnızca yönetici görünümündedir.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.decision.contract import CallRecord, Decision, DecisionInput
from app.decision.routing import Route, route_decision
from app.decision.serialize import judgment_to_dict
from app.domain.decision_jobs import (
    HUMAN_CHANGE_EVENT_KINDS,
    ApplyOutcome,
    JobOutcome,
    JobStatus,
)
from app.domain.vocabulary import TicketStatus
from app.models import Decision as DecisionRecord
from app.models import DecisionJob, ModelCall, Team, Ticket, TicketEvent
from app.schemas import DecisionJobOut, DecisionOut, DecisionPanel, JudgmentOut

_ERROR_LIMIT = 300


@dataclass(frozen=True)
class JobClaim:
    """Worker'ın aldığı işin kimliği ve kira bilgisi (tamamlarken kira sahipliği doğrulanır)."""

    job_id: UUID
    ticket_id: UUID
    strategy: str
    attempt: int
    worker_id: str


@dataclass(frozen=True)
class JobInput:
    """Sağlayıcıya gidecek asgari veri; ya da modelin hiç çağrılmaması gerektiği."""

    data: DecisionInput
    skip: JobOutcome | None


# --- Kuyruğa alma ---


def enqueue_job(
    db: Session, ticket: Ticket, strategy: str, *, max_attempts: int = 3
) -> DecisionJob:
    """Talebi açan işleme eklenir (commit çağıranındır): talep ve iş birlikte kaydolur veya
    birlikte geri alınır."""
    db.flush()  # ticket.id için
    job = DecisionJob(
        ticket_id=ticket.id,
        strategy=strategy,
        status=JobStatus.PENDING,
        max_attempts=max_attempts,
    )
    db.add(job)
    return job


# --- Uygunluk ---


def _untouched(ticket: Ticket) -> ApplyOutcome | None:
    """Karar bu talebe uygulanabilir mi? None = evet; aksi hâlde neden."""
    if ticket.status is not TicketStatus.NEW:
        return ApplyOutcome.SKIPPED_NOT_NEW
    if any(event.kind in HUMAN_CHANGE_EVENT_KINDS for event in ticket.events):
        return ApplyOutcome.SKIPPED_HUMAN_EDIT
    return None


# --- İş alma (kira) ---


def claim_next_job(
    db: Session, *, worker_id: str, now: datetime, lease: timedelta
) -> JobClaim | None:
    """Sıradaki işi alır. Başka worker'ın kilitlediği satırlar atlanır (SKIP LOCKED); kira süresi
    dolmuş 'running' işler (çöken worker) yeniden alınır."""
    while True:
        job = db.scalar(
            select(DecisionJob)
            .where(
                or_(
                    and_(DecisionJob.status == JobStatus.PENDING, DecisionJob.run_after <= now),
                    and_(DecisionJob.status == JobStatus.RUNNING, DecisionJob.locked_until < now),
                )
            )
            .order_by(DecisionJob.run_after, DecisionJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            db.rollback()
            return None
        if job.status is JobStatus.RUNNING and job.attempts >= job.max_attempts:
            # Önceki worker'lar kayboldu ve deneme hakkı bitti: iş başarısız, talep insana.
            _fail_job(db, job, JobOutcome.FAILED_WORKER_LOST, "worker_lost", now)
            db.commit()
            continue
        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.locked_by = worker_id
        job.locked_until = now + lease
        claim = JobClaim(job.id, job.ticket_id, job.strategy, job.attempts, worker_id)
        db.commit()
        return claim


def _owned_job(db: Session, claim: JobClaim) -> DecisionJob | None:
    """Kira hâlâ bu worker'da ise işi kilitleyerek getirir; kaybedilmişse None."""
    return db.scalar(
        select(DecisionJob)
        .where(
            DecisionJob.id == claim.job_id,
            DecisionJob.status == JobStatus.RUNNING,
            DecisionJob.locked_by == claim.worker_id,
            DecisionJob.attempts == claim.attempt,
        )
        .with_for_update()
    )


# --- Aşama A: kısa okuma ---


def begin_job(db: Session, claim: JobClaim) -> JobInput | None:
    """Sağlayıcıya gidecek veriyi okur (kilit tutmaz). Talep yoksa None. Talep artık uygun
    değilse model HİÇ çağrılmaz (gereksiz ücret ve gecikme yok)."""
    ticket = db.scalar(
        select(Ticket).options(selectinload(Ticket.events)).where(Ticket.id == claim.ticket_id)
    )
    if ticket is None:
        return None
    skip = None
    reason = _untouched(ticket)
    if reason is ApplyOutcome.SKIPPED_NOT_NEW:
        skip = JobOutcome.SKIPPED_NOT_NEW
    elif reason is ApplyOutcome.SKIPPED_HUMAN_EDIT:
        skip = JobOutcome.SKIPPED_HUMAN_EDIT
    data = DecisionInput(
        title=ticket.title, description=ticket.description, location=ticket.location
    )
    db.rollback()  # okuma bitti; işlem açık kalmasın
    return JobInput(data, skip)


# --- Aşama C: tek işlemde kayıt ---


def _model_call_row(call: CallRecord, job_id: UUID, decision_id: UUID | None) -> ModelCall:
    return ModelCall(
        id=call.call_id,
        job_id=job_id,
        decision_id=decision_id,
        strategy=call.strategy,
        provider=call.provider,
        model=call.model,
        prompt_version=call.prompt_version,
        questions=[q.value for q in call.questions],
        status=call.status,
        attempt=call.attempt,
        started_at=call.started_at,
        duration_ms=call.duration_ms,
        provider_duration_ms=call.provider_duration_ms,
        input_tokens=call.input_tokens,
        output_tokens=call.output_tokens,
        usage_estimated=call.usage_estimated,
        cost_usd=call.cost_usd,
        request_id=call.request_id,
        error=None if call.error is None else call.error[:_ERROR_LIMIT],
        is_mock=call.is_mock,
    )


def _finish(job: DecisionJob, status: JobStatus, outcome: JobOutcome, now: datetime) -> None:
    job.status = status
    job.outcome = outcome
    job.finished_at = now
    job.locked_by = None
    job.locked_until = None


def _add_event(ticket: Ticket, kind: str, **data: object) -> None:
    """Sistem olayı (actor yok). None değerler atılır."""
    clean = {key: value for key, value in data.items() if value is not None}
    ticket.events.append(TicketEvent(actor_id=None, kind=kind, data=clean))


def _apply(db: Session, ticket: Ticket, decision: Decision) -> None:
    """Kararı talebe uygular. Yalnızca 'new' ve dokunulmamış taleplerde çağrılır."""
    route = route_decision(decision)
    if decision.category is not None:
        ticket.category = decision.category
    if decision.priority is not None:
        ticket.priority = decision.priority
    ticket.missing_info = sorted(item.value for item in decision.missing_info)

    team = None
    if route.route is Route.TEAM_QUEUE and route.team_code is not None:
        team = db.scalar(select(Team).where(Team.code == route.team_code.value))
    if team is not None:
        # Ekip kuyruğu: ekip kategoriden deterministik bulunur; görevli seçimi insanındır.
        ticket.team_id = team.id
        ticket.status = TicketStatus.ASSIGNED
        ticket.review_required = False
    else:
        ticket.status = TicketStatus.NEEDS_REVIEW
        ticket.review_required = True

    _add_event(
        ticket,
        "decision_applied",
        decision_id=str(decision.decision_id),
        strategy=decision.strategy.value,
        is_mock=decision.is_mock,
        category=ticket.category.value if ticket.category else None,
        priority=ticket.priority.value,
        missing_info=ticket.missing_info,
        status=ticket.status.value,
        team=team.code if team else None,
    )


def complete_job_with_decision(
    db: Session, claim: JobClaim, decision: Decision, now: datetime
) -> ApplyOutcome | None:
    """Kararı, çağrı kayıtlarını ve (uygunsa) talep güncellemesini TEK işlemde yazar. Kira
    kaybedilmişse hiçbir şey yazılmaz ve None döner (işi başka worker yeniden yapacaktır)."""
    job = _owned_job(db, claim)
    if job is None:
        db.rollback()
        return None
    ticket = db.scalar(select(Ticket).where(Ticket.id == job.ticket_id).with_for_update())
    if ticket is None:  # talep silinmiş (iş de silinirdi); yine de güvenli çık
        db.rollback()
        return None

    outcome = _untouched(ticket) or ApplyOutcome.APPLIED
    db.add(
        DecisionRecord(
            id=decision.decision_id,
            job_id=job.id,
            ticket_id=ticket.id,
            strategy=decision.strategy,
            category=decision.category,
            priority=decision.priority,
            missing_info=[item.value for item in decision.missing_info],
            review_required=decision.review_required,
            review_reasons=list(decision.review_reasons),
            judgments=[judgment_to_dict(j) for j in decision.judgments],
            providers=list(decision.providers),
            model_versions=list(decision.model_versions),
            is_mock=decision.is_mock,
            applied_outcome=outcome,
            applied_at=now if outcome is ApplyOutcome.APPLIED else None,
        )
    )
    db.flush()  # model_calls bu satıra bağlanır
    for call in decision.calls:
        db.add(_model_call_row(call, job.id, decision.decision_id))
    if outcome is ApplyOutcome.APPLIED:
        _apply(db, ticket, decision)
    _finish(job, JobStatus.SUCCEEDED, JobOutcome.DECIDED, now)
    job.last_error = None
    db.commit()
    return outcome


def complete_job_skipped(db: Session, claim: JobClaim, skip: JobOutcome, now: datetime) -> bool:
    """Model hiç çağrılmadan işi kapatır (talep artık uygun değil)."""
    job = _owned_job(db, claim)
    if job is None:
        db.rollback()
        return False
    _finish(job, JobStatus.SUCCEEDED, skip, now)
    db.commit()
    return True


def _fail_job(
    db: Session, job: DecisionJob, outcome: JobOutcome, error: str, now: datetime
) -> None:
    """İşi kalıcı başarısız yapar. Talep korunur: hâlâ uygunsa insan incelemesine alınır ve
    görünür bir hata olayı yazılır; insan dokunmuşsa talebe hiç dokunulmaz."""
    _finish(job, JobStatus.FAILED, outcome, now)
    job.last_error = error[:_ERROR_LIMIT]
    ticket = db.scalar(
        select(Ticket)
        .options(selectinload(Ticket.events))
        .where(Ticket.id == job.ticket_id)
        .with_for_update()
    )
    if ticket is None or _untouched(ticket) is not None:
        return
    ticket.status = TicketStatus.NEEDS_REVIEW
    ticket.review_required = True
    _add_event(ticket, "decision_failed", strategy=job.strategy, reason=outcome.value)


def fail_or_retry_job(
    db: Session,
    claim: JobClaim,
    *,
    outcome: JobOutcome,
    error: str,
    calls: tuple[CallRecord, ...],
    now: datetime,
    retry_delay: timedelta | None,
) -> str | None:
    """Başarısız denemeyi kaydeder. `retry_delay` verilmiş ve hak kalmışsa işi yeniden kuyruğa
    alır ('retry'); aksi hâlde kalıcı başarısız yapar ('failed'). Kira kaybedilmişse None.
    Başarısız denemelerin çağrı kayıtları (maliyet) her durumda saklanır."""
    job = _owned_job(db, claim)
    if job is None:
        db.rollback()
        return None
    for call in calls:
        db.add(_model_call_row(call, job.id, None))
    if retry_delay is not None and job.attempts < job.max_attempts:
        job.status = JobStatus.PENDING
        job.run_after = now + retry_delay
        job.locked_by = None
        job.locked_until = None
        job.last_error = error[:_ERROR_LIMIT]
        db.commit()
        return "retry"
    _fail_job(db, job, outcome, error, now)
    db.commit()
    return "failed"


def fail_stale_job(
    db: Session, job_id: UUID, *, outcome: JobOutcome, error: str, now: datetime
) -> bool:
    """Kira süresi dolmuş 'running' işi kalıcı başarısız yapar (ör. süreç çağrı sırasında
    öldü). Talep korunur: hâlâ uygunsa insana verilir ve görünür bir hata olayı yazılır. İş
    yeniden ÇALIŞTIRILMAZ (istek sağlayıcıya gitmiş olabilir; otomatik yeniden gönderme yok).
    Değiştirdiyse True; iş zaten bitmiş/çalışıyorsa False."""
    job = db.scalar(
        select(DecisionJob)
        .where(
            DecisionJob.id == job_id,
            DecisionJob.status == JobStatus.RUNNING,
            DecisionJob.locked_until < now,
        )
        .with_for_update()
    )
    if job is None:
        db.rollback()
        return False
    _fail_job(db, job, outcome, error, now)
    db.commit()
    return True


# --- Yönetici görünümü ---


def _money(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


def get_panel(db: Session, ticket_id: UUID) -> DecisionPanel:
    """Yönetici için: talebin son karar işi ve son kararı (kaynak, mock mu, maliyet)."""
    job = db.scalar(
        select(DecisionJob)
        .where(DecisionJob.ticket_id == ticket_id)
        .order_by(DecisionJob.created_at.desc())
        .limit(1)
    )
    record = db.scalar(
        select(DecisionRecord)
        .where(DecisionRecord.ticket_id == ticket_id)
        .order_by(DecisionRecord.created_at.desc())
        .limit(1)
    )
    decision = None
    if record is not None:
        calls = db.scalars(select(ModelCall).where(ModelCall.job_id == record.job_id)).all()
        known = [call.cost_usd for call in calls if call.cost_usd is not None]
        decision_job = db.get(DecisionJob, record.job_id)
        decision = DecisionOut(
            id=record.id,
            strategy=record.strategy,
            job_strategy=decision_job.strategy if decision_job is not None else None,
            is_mock=record.is_mock,
            providers=list(record.providers),
            model_versions=list(record.model_versions),
            category=record.category,
            priority=record.priority,
            missing_info=list(record.missing_info),
            review_required=record.review_required,
            review_reasons=list(record.review_reasons),
            applied_outcome=record.applied_outcome,
            applied_at=record.applied_at,
            created_at=record.created_at,
            judgments=[JudgmentOut.model_validate(item) for item in record.judgments],
            calls_total=len(calls),
            cost_known_usd=_money(sum(known, Decimal(0))) if calls else None,
            calls_with_unknown_cost=len(calls) - len(known),
        )
    return DecisionPanel(
        job=None if job is None else DecisionJobOut.model_validate(job), decision=decision
    )
