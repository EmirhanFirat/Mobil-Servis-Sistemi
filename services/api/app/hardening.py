"""Üretim sertleştirmesi: giriş denemesi sınırı, güvenlik başlıkları ve istek gövdesi sınırı.

Üçü de tek süreçlik, bağımlılıksız çözümlerdir. Sınırlayıcı sayaçları süreç belleğindedir:
birden çok API süreci çalıştırılırsa her süreç kendi sayacını tutar (efektif sınır süreç sayısıyla
çarpılır); o durumda ters vekil (reverse proxy) düzeyinde de oran sınırı kullanılmalıdır.
"""

import ipaddress
import json
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings, get_settings

# --- Giriş denemesi sınırlayıcı -------------------------------------------------------------


class LoginThrottle:
    """Başarısız girişleri üç anahtarla sayar; sınırı aşan anahtar pencere dolana dek engellenir.

    - (IP, kullanıcı adı) çifti: tek kaynaktan tek hesaba deneme (en sıkı sınır),
    - kullanıcı adı: dağıtık denemeyle tek hesaba saldırı (daha gevşek: yöneticiyi dışarıdan
      kilitlemek için tek IP yetmesin),
    - IP: tek kaynaktan çok hesaba parola püskürtme.

    Engel sırasında doğru parola da reddedilir (yoksa saldırgan engel süresince denemeye devam eder)
    ve parola doğrulaması hiç çalıştırılmaz (Argon2 CPU'sunu tüketme saldırısını da yavaşlatır).
    Engel kararı hesabın var olup olmadığına bakmaz; yanıt ve süre hesabı ele vermez.
    """

    MAX_KEYS = 10_000

    def __init__(
        self,
        *,
        pair_limit: int,
        account_limit: int,
        ip_limit: int,
        window_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._pair_limit = pair_limit
        self._account_limit = account_limit
        self._ip_limit = ip_limit
        self._window = window_s
        self._clock = clock
        self._events: dict[tuple[str, ...], deque[float]] = {}
        self._lock = threading.Lock()

    def _limits(self, ip: str, username: str) -> list[tuple[tuple[str, ...], int]]:
        return [
            (("pair", ip, username), self._pair_limit),
            (("account", username), self._account_limit),
            (("ip", ip), self._ip_limit),
        ]

    def _prune(self, key: tuple[str, ...], now: float) -> deque[float] | None:
        events = self._events.get(key)
        if events is None:
            return None
        while events and now - events[0] >= self._window:
            events.popleft()
        if not events:
            del self._events[key]
            return None
        return events

    def retry_after(self, ip: str, username: str) -> int:
        """Engelliyse kalan saniye (en az 1), değilse 0."""
        now = self._clock()
        wait = 0.0
        with self._lock:
            for key, limit in self._limits(ip, username):
                events = self._prune(key, now)
                if events is not None and len(events) >= limit:
                    # Engel, sayaç sınırın altına inene dek (en eski gereksiz olay düşene dek)
                    # sürer.
                    lifts_at = events[len(events) - limit] + self._window
                    wait = max(wait, lifts_at - now)
        return max(1, math.ceil(wait)) if wait > 0 else 0

    def record_failure(self, ip: str, username: str) -> None:
        now = self._clock()
        with self._lock:
            if len(self._events) >= self.MAX_KEYS:
                self._evict(now)
            for key, _ in self._limits(ip, username):
                self._events.setdefault(key, deque()).append(now)

    def record_success(self, ip: str, username: str) -> None:
        """Başarılı giriş yalnızca o (IP, kullanıcı) çiftini sıfırlar; hesap/IP sayaçları kalır."""
        with self._lock:
            self._events.pop(("pair", ip, username), None)

    def _evict(self, now: float) -> None:
        """Kullanıcı adı uydurarak belleği şişirmeye karşı anahtar sayısını sınırlı tut."""
        for key in list(self._events):
            self._prune(key, now)
        overflow = len(self._events) - (self.MAX_KEYS * 9 // 10)
        if overflow > 0:
            oldest = sorted(self._events, key=lambda k: self._events[k][0])[:overflow]
            for key in oldest:
                del self._events[key]


@lru_cache
def _login_throttle(pair: int, account: int, ip: int, window: int) -> LoginThrottle:
    return LoginThrottle(pair_limit=pair, account_limit=account, ip_limit=ip, window_s=window)


def get_login_throttle(settings: Annotated[Settings, Depends(get_settings)]) -> LoginThrottle:
    return _login_throttle(
        settings.login_pair_limit,
        settings.login_account_limit,
        settings.login_ip_limit,
        settings.login_window_seconds,
    )


LoginThrottleDep = Annotated[LoginThrottle, Depends(get_login_throttle)]


def client_ip(request: Request, settings: Settings | None = None) -> str:
    """İstemci adresi.

    Varsayılan: doğrudan bağlantının adresi. Ters vekilin ardında bu vekilin adresidir (tüm
    ziyaretçiler tek IP görünür). `client_ip_header` verilirse değer o başlıktan alınır; virgüllü
    listede (X-Forwarded-For) SAĞDAN `trusted_proxy_hops`'uncu girdi kullanılır: güvendiğimiz
    vekilin eklediği girdidir, istemcinin sola ekleyebildikleri yok sayılır (sahte başlıkla IP
    değiştirilemez). Başlık yok, beklenenden kısa veya geçerli bir IP değilse doğrudan adrese
    düşülür; asla başlıktaki ham metne güvenilmez.
    """
    peer = request.client.host if request.client else "bilinmiyor"
    header = settings.client_ip_header if settings is not None else None
    if not header:
        return peer
    parts = [
        part.strip()
        for value in request.headers.getlist(header)
        for part in value.split(",")
        if part.strip()
    ]
    if len(parts) < settings.trusted_proxy_hops:
        return peer
    candidate = parts[-settings.trusted_proxy_hops]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return peer


# --- Güvenlik başlıkları --------------------------------------------------------------------

# API yalnızca JSON döner: hiçbir kaynak yüklenmesine, çerçeveye alınmaya veya forma izin verilmez.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
# Swagger arayüzü (yalnızca geliştirmede açık) CDN'den betik yüklediği için katı CSP uygulanmaz.
_DOCS_PATHS = ("/docs", "/redoc")


class SecurityHeadersMiddleware:
    """Her yanıta güvenlik başlıklarını ekler. HSTS yalnızca üretimde (HTTPS arkasında) eklenir."""

    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                # Oturum ve kişisel veri içeren yanıtlar ara belleklerde saklanmasın.
                headers.setdefault("Cache-Control", "no-store")
                if not path.startswith(_DOCS_PATHS):
                    headers.setdefault("Content-Security-Policy", API_CSP)
                if self.hsts:
                    headers.setdefault(
                        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_with_headers)


# --- İstek gövdesi sınırı -------------------------------------------------------------------

_TOO_LARGE_BODY = json.dumps(
    {"detail": "İstek gövdesi çok büyük.", "code": "payload_too_large"}, ensure_ascii=False
).encode("utf-8")


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Sınırı aşan istek gövdesini 413 ile reddeder; gövde belleğe alınmadan kesilir.

    `Content-Length` sınırı aşıyorsa istek hiç okunmaz; yoksa (parçalı gönderim) okunan bayt
    sayılır.
    FastAPI gövde okuma hatalarını 400'e çevirdiği için, sınır aşılmışsa uygulamanın yanıtı 413 ile
    değiştirilir.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        state = {"received": 0, "exceeded": False, "responded": False, "app_started": False}

        async def respond_too_large() -> None:
            if state["responded"]:
                return
            state["responded"] = True
            await send(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(_TOO_LARGE_BODY)).encode()),
                        (b"connection", b"close"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": _TOO_LARGE_BODY})

        if declared is not None and declared > self.max_bytes:
            await respond_too_large()
            return

        async def limited_receive() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                state["received"] += len(message.get("body", b""))
                if state["received"] > self.max_bytes:
                    state["exceeded"] = True
                    raise _BodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            if state["exceeded"]:
                await respond_too_large()
                return
            if message["type"] == "http.response.start":
                state["app_started"] = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            if not state["app_started"]:
                await respond_too_large()


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None
