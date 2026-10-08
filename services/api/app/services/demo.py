"""Canlı demo (portföy demosu): ziyaretçi oturumları, tek denemelik Jev kararı ve veri saklama.

Bu modül canlı demonun iş kurallarını toplar; karar motorunu KOPYALAMAZ: iş kaydı, kira ile alma,
A/B/C aşamaları ve talebe uygulama `services/decisions.py` ve `worker.run_claimed` içindeki mevcut
kodla yapılır. Ücretsiz barındırma (sürekli çalışan ayrı worker yok) için en küçük güvenilir
değişiklik: karar işi talebi açan işlemde KALICI olarak kaydedilir, sonra aynı HTTP isteği içinde,
süre sınırıyla, tek denemelik çalıştırılır. HTTP yanıtından sonra bellekte çalışan arka plan görevi
YOKTUR; süreç ölürse durum veritabanındadır.

Tekrar gönderme ve belirsizlik (Jev'de idempotency anahtarı ve "başarısız istek faturalanır mı"
belgelenmemiştir; "tam olarak bir kez" garantisi VERİLMEZ):
- Aynı ziyaretçi aynı metni (normalleştirilmiş özetle) tekrar gönderirse yeni talep ve yeni ücretli
  çağrı açılmaz; var olan talebin durumu döner (yenileme, çift tıklama, bağlantı kopması).
- İş `pending→running` geçişiyle ATOMİK alınır; bir işi yalnızca bir istek çalıştırır.
- Tek deneme, retry yok. Zaman aşımı/ağ hatası/çalışırken süreç ölümü: istek sağlayıcıya gitmiş
  olabilir → sonuç "belirsiz" kaydedilir, otomatik yeniden GÖNDERİLMEZ, maliyet en kötü bedelle
  sayılır.
"""

import hashlib
import hmac
import json
import os
import secrets
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import worker
from app.config import Settings
from app.decision import pg_budget
from app.decision.budget import BudgetedProvider
from app.decision.contract import CallStatus, DecisionInput, DecisionUnavailable, StrategyName
from app.decision.factory import jev_provider_from_settings
from app.decision.jev import JevProvider
from app.decision.mock import MockProvider
from app.decision.pg_budget import PgBudgetGuard
from app.decision.pricing import MOCK_JEV
from app.decision.retry import RetryPolicy
from app.decision.strategies import ProviderStrategy
from app.domain.decision_jobs import JobOutcome, JobStatus
from app.domain.vocabulary import Role
from app.errors import AppError, not_found
from app.models import Decision, DecisionJob, DemoRequest, ModelCall, Ticket, User
from app.schemas import TicketCreate
from app.schemas_demo import (
    DESCRIPTION_MAX,
    LOCATION_MAX,
    TITLE_MAX,
    DemoDecisionInfo,
    DemoDecisionRequest,
    DemoDecisionResult,
    DemoDecisionSummary,
    DemoJudgment,
    DemoLimits,
    DemoState,
    DemoStatus,
    DemoTimings,
    DemoUsage,
)
from app.security import create_access_token
from app.services import decisions
from app.services import tickets as ticket_service

# Demo işinin strateji adı: yalnızca jev_only (Anthropic ve hibrit canlı demoda YOKTUR).
DEMO_STRATEGY = "jev_only"
# Geçerli bir Argon2 özeti değildir: parola ile giriş HİÇBİR koşulda doğrulanamaz. Ziyaretçi
# yalnızca oturum açıldığında verilen kısa ömürlü belirteçle erişir.
NO_PASSWORD = "!demo"
# Eşzamanlı çağrı sınırını işlem düzeyinde sıraya sokan danışma kilidi anahtarı (PgBouncer işlem
# modunda da çalışır: kilit işlemin sonunda kendiliğinden bırakılır).
CONCURRENCY_LOCK_KEY = 7_340_001
# Süresi dolan ziyaretçileri tek seferde değil, sınırlı partilerle sil.
PURGE_BATCH = 100
# Bütçede bundan az kalmışsa demo "bütçe doldu" sayılır. En büyük girdi (4 baytlık karakterlerle
# bile) ve soru şemasıyla tek çağrının üst sınırından büyüktür (testle doğrulanır).
MIN_CALL_RESERVE = Decimal("0.0005")
PRICE_NOTE = (
    "Jev (jev-1.13.0): 0,042 USD / 1 milyon GİRDİ tokenı; çıktı tokenları ücretsiz. "
    "Ücret, Jev'in yanıtta bildirdiği kullanımdan hesaplanır; bildirilmezse bilinmez."
)

UNCERTAIN_CALL_STATUSES = frozenset({CallStatus.TIMEOUT, CallStatus.UNAVAILABLE})

ProviderFactory = Callable[[Settings], JevProvider]
RunStatus = str  # "ran" | "busy" | "not_pending"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def default_provider_factory(settings: Settings) -> JevProvider:
    return jev_provider_from_settings(settings, timeout_s=settings.demo_jev_timeout_s)


# --- Saklama süresi ---


def purge_expired(db: Session, settings: Settings, now: datetime) -> int:
    """Saklama süresi (`demo_retention_hours`) dolan ZİYARETÇİ hesaplarını ve tüm verilerini siler;
    silinen hesap sayısını döndürür.

    Yalnızca `is_demo` bayrağı olan hesaplar silinir: gerçek kullanıcılar, seed hesapları ve yerel
    E2E kayıtları (bayrak False) HİÇBİR koşulda silinmez. Talepler silinince olaylar, karar işleri,
    kararlar, model çağrıları ve demo istekleri veritabanı düzeyinde (CASCADE) silinir; bütçe
    kayıtları kalır (kişisel veri/metin içermez, yalnızca tutarlar) ve işe bağlantısı boşalır.
    """
    cutoff = now - timedelta(hours=settings.demo_retention_hours)
    ids = list(
        db.scalars(
            select(User.id)
            .where(User.is_demo.is_(True), User.created_at < cutoff)
            .order_by(User.created_at)
            .limit(PURGE_BATCH)
        )
    )
    if not ids:
        return 0
    db.execute(delete(Ticket).where(Ticket.created_by_id.in_(ids)))
    db.execute(delete(User).where(User.id.in_(ids), User.is_demo.is_(True)))
    db.commit()
    return len(ids)


# --- Kullanılabilirlik ve durum ---


@dataclass(frozen=True)
class Availability:
    available: bool
    reason: str | None  # herkese açık, kaba neden: disabled | not_configured | budget_exhausted
    provider: str | None
    model: str | None
    is_mock: bool


def availability(db: Session, settings: Settings) -> Availability:
    """Demo şu an gerçek karar üretebilir mi? Açık olmayan = kapalı: anahtar, ücretli çağrı izni ve
    onaylı bütçe kapsamı birlikte yoksa canlı çağrı yapılmaz."""
    if not settings.demo_enabled:
        return Availability(False, "disabled", None, None, False)
    if settings.demo_provider == "mock":
        return Availability(True, None, "mock-jev", MOCK_JEV.model, True)
    if not settings.paid_model_calls_enabled or settings.jev_api_key is None:
        return Availability(False, "not_configured", "jev", settings.jev_model, False)
    budget = pg_budget.status(db, settings.demo_budget_id)
    if budget is None:
        return Availability(False, "not_configured", "jev", settings.jev_model, False)
    if budget.remaining_usd < MIN_CALL_RESERVE:
        return Availability(False, "budget_exhausted", "jev", settings.jev_model, False)
    return Availability(True, None, "jev", settings.jev_model, False)


def limits(settings: Settings) -> DemoLimits:
    return DemoLimits(
        title_max=TITLE_MAX,
        description_max=DESCRIPTION_MAX,
        location_max=LOCATION_MAX,
        decisions_per_session=settings.demo_max_decisions_per_session,
        session_minutes=settings.demo_session_minutes,
    )


def probe_status(db: Session, settings: Settings) -> DemoStatus:
    """Hazırlık isteği: veritabanını uyandırır ve süresini ölçer; model çağrısı YAPMAZ."""
    import time

    started = time.perf_counter()
    db.execute(text("select 1"))
    database_ms = round((time.perf_counter() - started) * 1000)
    state = availability(db, settings)
    return DemoStatus(
        database_ready=True,
        database_ms=database_ms,
        enabled=state.available,
        reason=state.reason,  # type: ignore[arg-type]
        provider=state.provider,
        model=state.model,
        is_mock=state.is_mock,
        limits=limits(settings),
        retention_hours=settings.demo_retention_hours,
    )


# --- Ziyaretçi oturumu ---


def ip_hash(ip: str, settings: Settings) -> str:
    """IP'nin anahtarlı (HMAC) özeti: ham IP saklanmaz, yalnızca sınır sayımında karşılaştırılır."""
    key = settings.secret_key.get_secret_value().encode("utf-8")
    return hmac.new(key, ip.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session(
    db: Session, settings: Settings, ip: str, now: datetime | None = None
) -> tuple[User, str]:
    """Yeni ziyaretçi: parolasız, REQUESTER rollü, kısa ömürlü belirteçli ayrı bir kullanıcı. Her
    ziyaretçi yalnızca kendi taleplerini görür (mevcut yetkilendirme kuralları)."""
    now = now or _utcnow()
    state = availability(db, settings)
    if not state.available:
        raise AppError(503, "demo_unavailable", "Canlı demo şu anda kullanılamıyor.")
    purge_expired(db, settings, now)

    since_day = now - timedelta(hours=24)
    today = db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.is_demo.is_(True), User.created_at >= since_day)
    )
    if (today or 0) >= settings.demo_max_sessions_per_day:
        raise AppError(
            429,
            "demo_capacity",
            "Demo bugünkü ziyaretçi kapasitesine ulaştı. Yarın tekrar dene.",
            headers={"Retry-After": "3600"},
        )
    digest = None
    if settings.demo_ip_limits_enabled:
        digest = ip_hash(ip, settings)
        recent = db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.is_demo.is_(True),
                User.demo_ip_hash == digest,
                User.created_at >= now - timedelta(hours=1),
            )
        )
        if (recent or 0) >= settings.demo_max_sessions_per_ip_hour:
            raise AppError(
                429,
                "demo_ip_limit",
                "Bu bağlantıdan çok fazla demo oturumu açıldı. Bir saat sonra tekrar dene.",
                headers={"Retry-After": "3600"},
            )

    user = User(
        username=f"ziyaretci-{secrets.token_hex(6)}",
        display_name="Ziyaretçi",
        password_hash=NO_PASSWORD,
        role=Role.REQUESTER,
        is_demo=True,
        demo_ip_hash=digest,
    )
    db.add(user)
    db.commit()
    token = create_access_token(
        user.id, settings, password_hash=user.password_hash, minutes=settings.demo_session_minutes
    )
    return user, token


# --- Talep kaydı (tekrar gönderme anahtarı, sınırlar) ---


def request_key(data: DemoDecisionRequest) -> str:
    """Normalleştirilmiş metin özeti: boşluk ve büyük/küçük harf farkı ayrı talep yaratmaz."""

    def norm(value: str) -> str:
        return " ".join(value.split()).casefold()

    payload = json.dumps(
        [norm(data.title), norm(data.description), norm(data.location)], ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _count_requests(db: Session, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(DemoRequest).where(*conditions)) or 0


def register_request(
    db: Session,
    settings: Settings,
    visitor: User,
    data: DemoDecisionRequest,
    *,
    ip: str,
    now: datetime | None = None,
) -> tuple[UUID, bool]:
    """Talebi ve karar işini TEK işlemde kalıcı kaydeder. (talep_kimliği, yeni_mi).

    Aynı metin aynı ziyaretçiden tekrar gelirse var olan talep döner (yeni ücretli çağrı yok).
    Sınırlar (oturum başına karar, günlük genel, IP, kullanılabilirlik) YENİ talepten önce
    uygulanır."""
    now = now or _utcnow()
    key = request_key(data)
    existing = db.scalar(
        select(DemoRequest).where(DemoRequest.user_id == visitor.id, DemoRequest.request_key == key)
    )
    if existing is not None:
        return existing.ticket_id, False

    state = availability(db, settings)
    if not state.available:
        raise AppError(503, "demo_unavailable", "Canlı demo şu anda kullanılamıyor.")
    if _count_requests(db, DemoRequest.user_id == visitor.id) >= (
        settings.demo_max_decisions_per_session
    ):
        raise AppError(
            429,
            "demo_session_limit",
            f"Bu oturumda en çok {settings.demo_max_decisions_per_session} karar deneyebilirsin. "
            "Yeni bir oturum için sayfayı kapatıp daha sonra tekrar gel.",
        )
    if _count_requests(db, DemoRequest.created_at >= now - timedelta(hours=24)) >= (
        settings.demo_max_decisions_per_day
    ):
        raise AppError(
            429,
            "demo_capacity",
            "Demo bugünkü kapasitesine ulaştı. Yarın tekrar dene.",
            headers={"Retry-After": "3600"},
        )
    digest = None
    if settings.demo_ip_limits_enabled:
        digest = ip_hash(ip, settings)
        if _count_requests(
            db, DemoRequest.ip_hash == digest, DemoRequest.created_at >= now - timedelta(hours=1)
        ) >= (settings.demo_max_decisions_per_ip_hour):
            raise AppError(
                429,
                "demo_ip_limit",
                "Bu bağlantıdan çok fazla karar denendi. Bir saat sonra tekrar dene.",
                headers={"Retry-After": "3600"},
            )

    ticket = ticket_service.create_ticket(
        db,
        visitor,
        TicketCreate(title=data.title, description=data.description, location=data.location),
        decision_strategy=DEMO_STRATEGY,
        decision_max_attempts=1,  # tek deneme: yeniden deneme yok
        commit=False,
    )
    db.add(DemoRequest(user_id=visitor.id, ticket_id=ticket.id, request_key=key, ip_hash=digest))
    try:
        db.commit()
    except IntegrityError:
        # Aynı metin eşzamanlı iki istekle geldi; biri kazandı. Kazananın talebi döner.
        db.rollback()
        winner = db.scalar(
            select(DemoRequest).where(
                DemoRequest.user_id == visitor.id, DemoRequest.request_key == key
            )
        )
        if winner is None:
            raise
        return winner.ticket_id, False
    return ticket.id, True


# --- İşi çalıştırma (HTTP isteği içinde, tek denemelik) ---


class _ClosingStrategy:
    """Stratejiyi çalıştırır, sağlayıcının HTTP istemcisini her durumda kapatır."""

    def __init__(self, strategy: ProviderStrategy, provider: object) -> None:
        self._strategy = strategy
        self._provider = provider

    def decide(self, data: DecisionInput):
        try:
            return self._strategy.decide(data)
        finally:
            close = getattr(self._provider, "close", None)
            if close is not None:
                close()


def make_strategy(
    settings: Settings,
    session_factory: Callable[[], Session],
    job_id: UUID,
    provider_factory: ProviderFactory = default_provider_factory,
) -> _ClosingStrategy | ProviderStrategy:
    """jev_only, TEK deneme (retry yok) ve PostgreSQL bütçe korumasıyla. Anthropic ve hibrit canlı
    demoda kurulamaz. Başarısız olunca sessizce başka sağlayıcıya geçilmez."""
    retry = RetryPolicy(max_attempts=1)
    if settings.demo_provider == "mock":
        return ProviderStrategy(StrategyName.JEV_ONLY, MockProvider("jev"), retry=retry)
    jev = provider_factory(settings)
    guard = PgBudgetGuard(
        session_factory, settings.demo_budget_id, job_id=job_id, price=jev.price, max_attempts=1
    )
    guarded = BudgetedProvider(jev, guard)
    return _ClosingStrategy(ProviderStrategy(StrategyName.JEV_ONLY, guarded, retry=retry), jev)


def _demo_outcome(failure: DecisionUnavailable) -> JobOutcome:
    """Zaman aşımı ve ağ hatasında istek sağlayıcıya gitmiş OLABİLİR: 'belirsiz' (yeniden
    gönderilmez, en kötü bedelle sayılır). Yanıt gelip geçersizse veya sağlayıcı açıkça
    reddettiyse sonuç bellidir: kalıcı hata."""
    last = failure.calls[-1].status if failure.calls else None
    if last in UNCERTAIN_CALL_STATUSES:
        return JobOutcome.PROVIDER_UNCERTAIN
    return JobOutcome.FAILED_PROVIDER


def _worker_id() -> str:
    return f"demo:{socket.gethostname()}:{os.getpid()}"[:100]


def _claim(
    session_factory: Callable[[], Session], job_id: UUID, settings: Settings, now: datetime
) -> decisions.JobClaim | str | None:
    """İşi ATOMİK alır: yalnızca `pending` iş alınır (ikinci istek None görür). Eşzamanlı çağrı
    sınırı aşılmışsa "busy" döner (iş `pending` kalır, kaybolmaz)."""
    lease = timedelta(seconds=settings.demo_jev_timeout_s * 2 + 15)
    with session_factory() as db:
        # Sınır kontrolü ile alma, danışma kilidiyle sıraya sokulur: iki istek aynı anda
        # "boş yer var" görüp sınırı aşamaz.
        db.execute(text("select pg_advisory_xact_lock(:key)"), {"key": CONCURRENCY_LOCK_KEY})
        running = db.scalar(
            select(func.count())
            .select_from(DecisionJob)
            .where(
                DecisionJob.strategy == DEMO_STRATEGY,
                DecisionJob.status == JobStatus.RUNNING,
                DecisionJob.locked_until > now,
            )
        )
        if (running or 0) >= settings.demo_max_concurrent_calls:
            db.rollback()
            return "busy"
        job = db.scalar(select(DecisionJob).where(DecisionJob.id == job_id).with_for_update())
        if job is None or job.status is not JobStatus.PENDING or job.run_after > now:
            db.rollback()
            return None
        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.locked_by = _worker_id()
        job.locked_until = now + lease
        claim = decisions.JobClaim(job.id, job.ticket_id, job.strategy, job.attempts, job.locked_by)
        db.commit()
        return claim


def _latest_job(db: Session, ticket_id: UUID) -> DecisionJob | None:
    return db.scalar(
        select(DecisionJob)
        .where(DecisionJob.ticket_id == ticket_id)
        .order_by(DecisionJob.created_at.desc())
        .limit(1)
    )


def resolve_stale(
    session_factory: Callable[[], Session],
    ticket_id: UUID,
    *,
    clock: Callable[[], datetime] = _utcnow,
) -> bool:
    """Çağrı sırasında ölmüş (kira süresi dolmuş) `running` işi "belirsiz" sonuçla kapatır. Hiçbir
    çağrı BAŞLATMAZ ve yeniden göndermez (istek sağlayıcıya gitmiş olabilir); GET istekleri de
    güvenle kullanabilir. Değiştirdiyse True."""
    now = clock()
    with session_factory() as db:
        job = _latest_job(db, ticket_id)
        if job is None or job.status is not JobStatus.RUNNING:
            return False
        if job.locked_until is None or job.locked_until >= now:
            return False
        job_id = job.id
    with session_factory() as db:
        return decisions.fail_stale_job(
            db,
            job_id,
            outcome=JobOutcome.PROVIDER_UNCERTAIN,
            error="process_lost_during_call",
            now=now,
        )


def run_if_pending(
    session_factory: Callable[[], Session],
    settings: Settings,
    ticket_id: UUID,
    *,
    provider_factory: ProviderFactory = default_provider_factory,
    clock: Callable[[], datetime] = _utcnow,
) -> RunStatus:
    """Talebin karar işi hiç başlamadıysa (`pending`) şimdi çalıştırır; aksi hâlde DOKUNMAZ.

    "ran": bu istek çalıştırdı (sonuç veritabanında). "busy": eşzamanlı çağrı sınırı dolu, iş
    `pending` kaldı (kullanıcı kontrollü yeniden deneme). "not_pending": iş zaten çalışıyor ya da
    bitmiş: tekrar gönderilen istek ikinci bir çağrı BAŞLATMAZ. Çağrı sırasında ölmüş `running`
    iş "belirsiz" kapatılır (`resolve_stale`); yeniden gönderilmez."""
    resolve_stale(session_factory, ticket_id, clock=clock)
    now = clock()
    with session_factory() as db:
        job = _latest_job(db, ticket_id)
        if job is None or job.status is not JobStatus.PENDING:
            return "not_pending"
        job_id = job.id

    claim = _claim(session_factory, job_id, settings, now)
    if claim == "busy":
        return "busy"
    if claim is None:
        return "not_pending"
    assert isinstance(claim, decisions.JobClaim)
    worker.run_claimed(
        session_factory,
        claim,
        build_strategy=lambda _name: make_strategy(
            settings, session_factory, claim.job_id, provider_factory
        ),
        clock=clock,
        unexpected_retry_delay=lambda _attempt: None,  # tek deneme: yeniden kuyruğa alınmaz
        provider_outcome=_demo_outcome,
    )
    return "ran"


# --- Sonuç (ziyaretçiye gösterilen; veritabanından kurulur) ---

_REASON_TEXT = {
    "category_unclear": "Kategori belirsiz kaldı.",
    "priority_unclear": "Aciliyet belirsiz kaldı.",
    "location_missing": "Konum eksik görünüyor.",
    "detail_missing": "Açıklama yetersiz görünüyor.",
    "location_unknown": "Konumun yeterli olup olmadığı belirlenemedi.",
    "detail_unknown": "Açıklamanın yeterli olup olmadığı belirlenemedi.",
    "possible_prompt_injection": (
        "Metinde modele talimat veriyormuş gibi ifadeler algılandı; metin yalnızca veri sayıldı "
        "ve karar insana bırakıldı."
    ),
    "multiple_issues": "Metin birden çok sorun içeriyor.",
}


def explain_reasons(codes: list[str]) -> list[str]:
    explanations = []
    for code in codes:
        if code.startswith("safety:"):
            term = code.removeprefix("safety:")
            explanations.append(
                f"Güvenlik terimi algılandı ('{term}'): öncelik yüksek yapıldı ve insan "
                "incelemesi istendi."
            )
        else:
            explanations.append(_REASON_TEXT.get(code, f"İnceleme nedeni: {code}"))
    return explanations


def state_of(job: DecisionJob | None) -> DemoState:
    if job is None or job.status is JobStatus.PENDING:
        return "pending"
    if job.status is JobStatus.RUNNING:
        return "running"
    if job.status is JobStatus.SUCCEEDED:
        if job.outcome is JobOutcome.DECIDED:
            return "completed"
        return "skipped"  # SKIPPED_NOT_NEW / SKIPPED_HUMAN_EDIT: model hiç çağrılmadı
    if job.outcome is JobOutcome.PROVIDER_UNCERTAIN:
        return "uncertain"
    if job.outcome is JobOutcome.BUDGET_EXHAUSTED:
        return "budget_exhausted"
    return "failed"


_MESSAGES: dict[str, str] = {
    "pending": "Talebin kaydedildi; karar henüz çalıştırılmadı. Birkaç saniye sonra yeniden dene.",
    "running": "Karar şu anda üretiliyor (başka bir istekte). Birkaç saniye sonra tekrar bak.",
    "completed": "Jev kararı üretildi.",
    "skipped": (
        "Talep, karar çalışmadan önce bir insan tarafından değiştirildiği için Jev çağrılmadı; "
        "insanın değişikliği korundu."
    ),
    "failed": (
        "Jev'den geçerli bir karar alınamadı. Talebin kaydedildi ve insan incelemesine "
        "bırakıldı; başka bir sağlayıcıya geçilmedi."
    ),
    "uncertain": (
        "Jev'e gönderilen isteğin sonucu bilinmiyor (zaman aşımı veya bağlantı sorunu). İstek "
        "gönderilmiş olabilir; kopya çağrı açmamak için OTOMATİK yeniden gönderilmedi. Talebin "
        "kaydedildi ve insan incelemesine bırakıldı."
    ),
    "budget_exhausted": (
        "Demo'nun ayrılan bütçesi doldu; istek Jev'e gönderilmedi. Talebin kaydedildi ve insan "
        "incelemesine bırakıldı."
    ),
}


def _decision_info(decision: Decision, calls: list[ModelCall]) -> DemoDecisionInfo:
    judgments = [
        DemoJudgment(
            question=item.get("question", ""),
            answer=item.get("answer"),
            confidence=item.get("confidence"),
            confidence_kind=item.get("confidence_kind"),
            adopted=bool(item.get("adopted", True)),
        )
        for item in decision.judgments
    ]
    return DemoDecisionInfo(
        category=decision.category.value if decision.category else None,
        priority=decision.priority.value if decision.priority else None,
        missing_info=list(decision.missing_info),
        review_required=decision.review_required,
        review_explanations=explain_reasons(list(decision.review_reasons)),
        applied=decision.applied_outcome.value == "applied",
        applied_outcome=decision.applied_outcome.value,
        is_mock=decision.is_mock,
        provider=decision.providers[0] if decision.providers else None,
        model=decision.model_versions[0] if decision.model_versions else None,
        judgments=judgments,
    )


def _usage(calls: list[ModelCall]) -> DemoUsage | None:
    """Çağrı kayıtlarından kullanım ve ücret. Bildirilmeyen değer None'dır (sıfır/tahmin değil)."""
    if not calls:
        return None
    inputs = [c.input_tokens for c in calls]
    outputs = [c.output_tokens for c in calls]
    costs = [c.cost_usd for c in calls]
    known_cost = all(value is not None for value in costs)
    total = sum((c for c in costs if c is not None), Decimal(0))
    return DemoUsage(
        calls=len(calls),
        input_tokens=sum(inputs) if all(v is not None for v in inputs) else None,  # type: ignore[arg-type]
        output_tokens=sum(outputs) if all(v is not None for v in outputs) else None,  # type: ignore[arg-type]
        output_tokens_free=True,
        cost_usd=format(total.normalize(), "f") if known_cost else None,
        cost_basis="provider_usage" if known_cost else "unknown",
        price_note=PRICE_NOTE,
    )


def _timings(job: DecisionJob | None, calls: list[ModelCall]) -> DemoTimings:
    jev_ms = calls[-1].duration_ms if calls else None
    job_ms = None
    if job is not None and job.finished_at is not None:
        job_ms = max(0, round((job.finished_at - job.created_at).total_seconds() * 1000))
    return DemoTimings(jev_call_ms=jev_ms, job_ms=job_ms, server_total_ms=None)


def result_for(
    db: Session, settings: Settings, visitor: User, ticket_id: UUID
) -> DemoDecisionResult:
    """Ziyaretçinin KENDİ talebinin sonucu. Başkasının talebi 'yok' gibi davranır (404)."""
    ticket = db.scalar(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.created_by_id == visitor.id)
    )
    if ticket is None:
        raise not_found("Demo talebi bulunamadı.")
    job = _latest_job(db, ticket.id)
    state = state_of(job)
    record = db.scalar(
        select(Decision).where(Decision.ticket_id == ticket.id).order_by(Decision.created_at.desc())
    )
    calls: list[ModelCall] = []
    if job is not None:
        calls = list(
            db.scalars(
                select(ModelCall).where(ModelCall.job_id == job.id).order_by(ModelCall.started_at)
            )
        )
    used = _count_requests(db, DemoRequest.user_id == visitor.id)
    return DemoDecisionResult(
        ticket_id=ticket.id,
        ticket_number=ticket.number,
        state=state,
        message=_MESSAGES[state],
        title=ticket.title,
        description=ticket.description,
        location=ticket.location,
        ticket_status=ticket.status.value,
        created_at=ticket.created_at,
        decision=_decision_info(record, calls) if record is not None else None,
        usage=_usage(calls),
        timings=_timings(job, calls),
        retry_after_s=5 if state in ("pending", "running") else None,
        decisions_remaining=max(0, settings.demo_max_decisions_per_session - used),
    )


def list_for(db: Session, visitor: User) -> list[DemoDecisionSummary]:
    tickets = db.scalars(
        select(Ticket)
        .where(Ticket.created_by_id == visitor.id)
        .order_by(Ticket.created_at.desc())
        .limit(50)
    ).all()
    summaries = []
    for ticket in tickets:
        summaries.append(
            DemoDecisionSummary(
                ticket_id=ticket.id,
                ticket_number=ticket.number,
                title=ticket.title,
                state=state_of(_latest_job(db, ticket.id)),
                created_at=ticket.created_at,
            )
        )
    return summaries
