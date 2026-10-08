"""Canlı demo uçları (portföy demosu). Varsayılan KAPALI (`TALEPAKIS_DEMO_ENABLED`).

- `GET /demo/status`: hazırlık isteği; veritabanını uyandırır ve süresini ölçer, model çağrısı
  YAPMAZ.
- `POST /demo/session`: parolasız, kısa ömürlü, ayrı bir ziyaretçi oturumu (REQUESTER; yalnızca
  kendi taleplerini görür).
- `POST /demo/decisions`: talebi ve karar işini kalıcı kaydeder, sonra aynı istek içinde tek
  denemelik Jev kararını çalıştırır. Aynı metin tekrar gelirse ikinci çağrı açılmaz.
- `GET /demo/decisions[/{id}]`: yalnızca OKUR; hiçbir koşulda model çağrısı başlatmaz.
"""

import threading
import time
from collections.abc import Callable
from time import perf_counter
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession, SettingsDep
from app.errors import forbidden
from app.hardening import client_ip
from app.models import User
from app.schemas_demo import (
    DemoDecisionRequest,
    DemoDecisionResult,
    DemoDecisionSummary,
    DemoSessionOut,
    DemoStatus,
)
from app.services import demo

router = APIRouter(prefix="/demo", tags=["demo"])

# Hazırlık isteği herkese açıktır; veritabanını her çağrıda yoklamak hem havuzu hem ücretsiz
# veritabanının uyanık kalma süresini gereksiz tüketir. Sonuç kısa süre önbelleğe alınır.
STATUS_CACHE_SECONDS = 15.0
_status_cache: tuple[float, DemoStatus] | None = None
_status_lock = threading.Lock()

BUSY_MESSAGE = (
    "Demo şu anda başka isteklerle meşgul. Talebin kaydedildi; birkaç saniye sonra aynı "
    "talebi yeniden gönder."
)


def clear_status_cache() -> None:
    global _status_cache
    with _status_lock:
        _status_cache = None


def get_provider_factory() -> demo.ProviderFactory:
    """Jev sağlayıcısını kuran fonksiyon. Testler bunu sahte HTTP taşıyıcılı olanla değiştirir."""
    return demo.default_provider_factory


def get_demo_visitor(user: CurrentUser) -> User:
    if not user.is_demo:
        raise forbidden("Bu uç yalnızca demo ziyaretçi oturumları içindir.")
    return user


DemoVisitor = Annotated[User, Depends(get_demo_visitor)]
ProviderFactoryDep = Annotated[demo.ProviderFactory, Depends(get_provider_factory)]


def _session_factory(db: Session) -> Callable[[], Session]:
    """İş aşamaları kendi kısa oturumlarını açar (sağlayıcı çağrısı sırasında bağlantı/kilit yok);
    istek oturumuyla AYNI veritabanına bağlanır."""
    bind = db.get_bind()
    return lambda: Session(bind)


@router.get("/status", response_model=DemoStatus, summary="Hazırlık: model çağrısı YAPMAZ")
def demo_status(db: DbSession, settings: SettingsDep) -> DemoStatus:
    global _status_cache
    with _status_lock:
        cached = _status_cache
    if cached is not None and time.monotonic() - cached[0] < STATUS_CACHE_SECONDS:
        return cached[1]
    try:
        result = demo.probe_status(db, settings)
    except (OperationalError, PoolTimeoutError):
        # Veritabanı (ör. Neon) henüz uyanmadı: API ayakta, veritabanı hazır değil. İstemci
        # kullanıcı kontrollü olarak yeniden dener.
        return DemoStatus(
            database_ready=False,
            database_ms=None,
            enabled=False,
            reason=None,
            provider=None,
            model=None,
            is_mock=False,
            limits=demo.limits(settings),
            retention_hours=settings.demo_retention_hours,
        )
    with _status_lock:
        _status_cache = (time.monotonic(), result)
    return result


@router.post(
    "/session",
    response_model=DemoSessionOut,
    status_code=201,
    summary="Parolasız, kısa ömürlü ziyaretçi oturumu",
)
def open_session(request: Request, db: DbSession, settings: SettingsDep) -> DemoSessionOut:
    _user, token = demo.create_session(db, settings, client_ip(request, settings))
    return DemoSessionOut(
        access_token=token,
        expires_in_s=settings.demo_session_minutes * 60,
        decisions_total=settings.demo_max_decisions_per_session,
        limits=demo.limits(settings),
    )


@router.post(
    "/decisions",
    response_model=DemoDecisionResult,
    summary="Talebi kaydet ve Jev kararını (tek denemelik) üret",
)
def create_decision(
    data: DemoDecisionRequest,
    request: Request,
    response: Response,
    visitor: DemoVisitor,
    db: DbSession,
    settings: SettingsDep,
    provider_factory: ProviderFactoryDep,
) -> DemoDecisionResult:
    started = perf_counter()
    ticket_id, _created = demo.register_request(
        db, settings, visitor, data, ip=client_ip(request, settings)
    )
    outcome = demo.run_if_pending(
        _session_factory(db), settings, ticket_id, provider_factory=provider_factory
    )
    db.expire_all()  # iş aşamaları ayrı oturumlarda yazdı; bu oturumdaki nesneler eskimiş olabilir
    result = demo.result_for(db, settings, visitor, ticket_id)
    result.timings.server_total_ms = round((perf_counter() - started) * 1000)
    if outcome == "busy":
        result.message = BUSY_MESSAGE
    if result.state in ("pending", "running"):
        response.status_code = 202
    return result


@router.get("/decisions", response_model=list[DemoDecisionSummary], summary="Kendi taleplerin")
def list_decisions(visitor: DemoVisitor, db: DbSession) -> list[DemoDecisionSummary]:
    return demo.list_for(db, visitor)


@router.get(
    "/decisions/{ticket_id}",
    response_model=DemoDecisionResult,
    summary="Bir talebin sonucu (yalnızca okur; çağrı başlatmaz)",
)
def get_decision(
    ticket_id: UUID, visitor: DemoVisitor, db: DbSession, settings: SettingsDep
) -> DemoDecisionResult:
    result = demo.result_for(db, settings, visitor, ticket_id)
    if result.state == "running" and demo.resolve_stale(_session_factory(db), ticket_id):
        db.expire_all()
        result = demo.result_for(db, settings, visitor, ticket_id)
    return result
