"""Karar worker'ı: bekleyen karar işlerini veritabanından alır, stratejiyi çalıştırır, kaydeder.

Kullanım (services/api içinde):
  .\\.venv\\Scripts\\python.exe -m app.worker            # sürekli çalışır (Ctrl+C ile durur)
  .\\.venv\\Scripts\\python.exe -m app.worker --once     # kuyruk boşalana dek işler, çıkar

API'den ayrı bir süreçtir; API çalışmasa da, worker durup yeniden başlasa da iş kaybolmaz
(durum veritabanındadır). Yalnızca ücretsiz stratejileri (rule_based, mock_*) çalıştırır ve hiçbir
API anahtarı okumaz. Bir işte üç aşama vardır ve model çağrısı SIRASINDA veritabanı kilidi
tutulmaz: (A) kısa okuma, (B) sağlayıcı çağrısı, (C) tek işlemde kayıt. Ayrıntı:
app/services/decisions.py.
"""

import argparse
import os
import socket
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.decision.contract import BudgetExhausted, DecisionUnavailable
from app.decision.registry import build_free_strategy
from app.domain.decision_jobs import JobOutcome
from app.services import decisions

SessionFactory = Callable[[], Session]
StrategyBuilder = Callable[[str], object]

# İş düzeyinde yeniden deneme (yalnızca beklenmeyen hatalar); sağlayıcı retry'ı stratejinin içinde.
RETRY_BASE_S = 30
RETRY_MAX_S = 300

# Veritabanına ulaşılamayınca (Docker yeniden başlıyor, bağlantı koptu) worker çökmez: üstel
# beklemeyle yeniden dener. Bu bir işin başarısızlığı değil altyapı kesintisidir; iş hakkı
# harcanmaz.
DB_OUTAGE_MAX_WAIT_S = 30.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


def make_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:6]}"[:100]


def _backoff(attempt: int) -> timedelta:
    return timedelta(seconds=min(RETRY_BASE_S * 2 ** (attempt - 1), RETRY_MAX_S))


def _provider_failure_outcome(failure: DecisionUnavailable) -> JobOutcome:
    return JobOutcome.FAILED_PROVIDER


def run_claimed(
    session_factory: SessionFactory,
    claim: decisions.JobClaim,
    *,
    build_strategy: StrategyBuilder = build_free_strategy,
    clock: Callable[[], datetime] = _utcnow,
    unexpected_retry_delay: Callable[[int], timedelta | None] = _backoff,
    provider_outcome: Callable[[DecisionUnavailable], JobOutcome] = _provider_failure_outcome,
) -> None:
    """Alınmış (kiralanmış) bir işi A/B/C aşamalarıyla işler. Worker ve canlı demo (HTTP isteği
    içinde, tek denemelik) aynı kodu kullanır; karar motoru kopyalanmaz.

    `unexpected_retry_delay(deneme)`: beklenmeyen hatada işin ne kadar sonra yeniden kuyruğa
    alınacağı (None = yeniden denenmez, kalıcı başarısız). `provider_outcome`: sağlayıcı kalıcı
    hata verince işin sonucu (varsayılan FAILED_PROVIDER; demo "belirsiz"i ayırır)."""
    # A) Kısa okuma: talep artık uygun değilse model hiç çağrılmaz.
    with session_factory() as db:
        job_input = decisions.begin_job(db, claim)
    if job_input is None:  # talep silinmiş; iş de silinmiş olmalı
        return
    if job_input.skip is not None:
        with session_factory() as db:
            decisions.complete_job_skipped(db, claim, job_input.skip, clock())
        return

    # B) Sağlayıcı çağrısı: açık veritabanı oturumu/kilidi YOK.
    try:
        strategy = build_strategy(claim.strategy)
        decision = strategy.decide(job_input.data)  # type: ignore[attr-defined]
    except DecisionUnavailable as failure:
        # Sınırlı retry bitti: kalıcı hata. Talep korunur ve insana verilir; denemelerin
        # maliyeti kaydedilir. Sessizce başka sağlayıcıya geçilmez.
        with session_factory() as db:
            decisions.fail_or_retry_job(
                db,
                claim,
                outcome=provider_outcome(failure),
                error=str(failure),
                calls=failure.calls,
                now=clock(),
                retry_delay=None,
            )
        return
    except BudgetExhausted as stop:
        # Harcama sınırı: istek GÖNDERİLMEDİ. Yeniden denenmez; o ana dek yapılmış çağrıların
        # kaydı korunur.
        with session_factory() as db:
            decisions.fail_or_retry_job(
                db,
                claim,
                outcome=JobOutcome.BUDGET_EXHAUSTED,
                error="budget_exhausted",
                calls=stop.calls,
                now=clock(),
                retry_delay=None,
            )
        return
    except (
        Exception
    ) as exc:  # beklenmeyen hata: yalnızca tür kaydedilir (ayrıntıda kullanıcı verisi olabilir)
        with session_factory() as db:
            decisions.fail_or_retry_job(
                db,
                claim,
                outcome=JobOutcome.FAILED_ERROR,
                error=type(exc).__name__,
                calls=(),
                now=clock(),
                retry_delay=unexpected_retry_delay(claim.attempt),
            )
        return

    # C) Tek işlemde kayıt. Kira kaybedildiyse veya aynı iş başka yerde tamamlandıysa hiçbir şey
    # yazılmaz (çift karar/olay yok).
    with session_factory() as db:
        try:
            decisions.complete_job_with_decision(db, claim, decision, clock())
        except IntegrityError:
            db.rollback()


def process_next(
    session_factory: SessionFactory,
    *,
    worker_id: str,
    lease: timedelta,
    build_strategy: StrategyBuilder = build_free_strategy,
    clock: Callable[[], datetime] = _utcnow,
) -> bool:
    """Sıradaki işi işler. İş bulunduysa True (başarılı olması gerekmez), kuyruk boşsa False."""
    with session_factory() as db:
        claim = decisions.claim_next_job(db, worker_id=worker_id, now=clock(), lease=lease)
    if claim is None:
        return False
    run_claimed(session_factory, claim, build_strategy=build_strategy, clock=clock)
    return True


def run_forever(
    session_factory: SessionFactory,
    *,
    worker_id: str,
    lease: timedelta,
    poll_seconds: float,
    stop: threading.Event,
    build_strategy: StrategyBuilder = build_free_strategy,
    clock: Callable[[], datetime] = _utcnow,
) -> int:
    """Durdurulana dek sürekli işler. İşlenen iş sayısını döndürür.

    Veritabanına ulaşılamazsa (OperationalError, havuz zaman aşımı) çökmez: bir mesaj yazıp üstel
    beklemeyle (en çok DB_OUTAGE_MAX_WAIT_S) yeniden dener, veritabanı dönünce kaldığı yerden
    sürer. Başka beklenmeyen hatalar (kod hatası) gizlenmez, yukarı çıkar."""
    processed = 0
    outage = 0  # ardışık veritabanı ulaşılamazlığı sayısı
    while not stop.is_set():
        try:
            handled = process_next(
                session_factory,
                worker_id=worker_id,
                lease=lease,
                build_strategy=build_strategy,
                clock=clock,
            )
        except (OperationalError, PoolTimeoutError) as error:
            outage += 1
            wait = min(max(poll_seconds, 1.0) * 2**outage, DB_OUTAGE_MAX_WAIT_S)
            print(
                f"Veritabanına ulaşılamıyor ({type(error).__name__}); {wait:.0f} sn sonra "
                "yeniden denenecek. Docker'daki veritabanı çalışıyor mu? (docker compose up -d db)",
                flush=True,
            )
            stop.wait(wait)
            continue
        if outage:
            print("Veritabanına yeniden ulaşıldı; çalışmaya devam ediliyor.", flush=True)
            outage = 0
        if handled:
            processed += 1
        else:
            stop.wait(poll_seconds)
    return processed


def drain(
    session_factory: SessionFactory,
    *,
    worker_id: str,
    lease: timedelta,
    build_strategy: StrategyBuilder = build_free_strategy,
    clock: Callable[[], datetime] = _utcnow,
    max_jobs: int | None = None,
) -> int:
    """Kuyruk boşalana (veya `max_jobs`a) dek işler; işlenen iş sayısını döndürür."""
    processed = 0
    while max_jobs is None or processed < max_jobs:
        if not process_next(
            session_factory,
            worker_id=worker_id,
            lease=lease,
            build_strategy=build_strategy,
            clock=clock,
        ):
            break
        processed += 1
    return processed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.worker", description=__doc__)
    parser.add_argument("--once", action="store_true", help="Kuyruk boşalana dek işle ve çık")
    parser.add_argument("--poll-seconds", type=float, default=None)
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = get_engine()
    worker_id = make_worker_id()
    lease = timedelta(seconds=settings.decision_job_lease_seconds)

    def session_factory() -> Session:
        return Session(engine)

    if args.once:
        try:
            count = drain(session_factory, worker_id=worker_id, lease=lease)
        except (OperationalError, PoolTimeoutError) as error:
            print(
                f"Veritabanına ulaşılamıyor ({type(error).__name__}). "
                "Docker'daki veritabanı çalışıyor mu? (docker compose up -d db)"
            )
            return 1
        print(f"{count} karar işi işlendi.")
        return 0

    poll = args.poll_seconds if args.poll_seconds is not None else settings.worker_poll_seconds
    stop = threading.Event()
    print(f"Karar worker'ı çalışıyor ({worker_id}); durdurmak için Ctrl+C.")
    try:
        run_forever(session_factory, worker_id=worker_id, lease=lease, poll_seconds=poll, stop=stop)
    except KeyboardInterrupt:
        # İşlenmekte olan iş varsa kira süresi dolunca başka worker (veya bu) yeniden alır.
        stop.set()
        print("Durduruldu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
