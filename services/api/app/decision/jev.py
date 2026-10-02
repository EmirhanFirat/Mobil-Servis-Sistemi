"""Jev adaptörü: ham HTTP ile POST /v1/systemone (docs.typesafe.ai/api.md). SDK kullanılmaz
(bkz. DECISIONS D22). Bu modül kendi başına ağ isteği YAPMAZ; yalnızca bir `JevProvider` örneği
oluşturulup `classify` çağrılırsa istek atılır. Örnek, ücretli çağrılar açık değilse fabrikadan
alınamaz (factory.py).

Güvenlik ve dürüstlük:
- API anahtarı yalnızca Authorization başlığındadır; kayıtlara, hata mesajlarına, repr'a girmez.
- Kullanıcı metni yalnızca `state` verisidir; sorular sabittir (jev_questions.py).
- Hata mesajlarına sunucu yanıt gövdesi konmaz (kullanıcı metnini yansıtabilir); yalnızca kod.
- Kullanım (token) yanıtta yoksa None kalır; uydurulmaz.
"""

import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.decision.contract import (
    CallRecord,
    CallStatus,
    ConfidenceKind,
    DecisionInput,
    Judgment,
    Question,
    StrategyName,
)
from app.decision.jev_questions import PROMPT_VERSION, option_codes, question_definition
from app.decision.pricing import JEV_1_13, PriceEntry
from app.decision.providers import ProviderError, ProviderResult

ENDPOINT = "/v1/systemone"
DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-1.13.0"
# SDK varsayılanı 10 sn (docs.typesafe.ai/sdk/python/api/constants.md).
DEFAULT_TIMEOUT_S = 10.0
PROBABILITY_TOLERANCE = 0.02


class _SchemaError(ValueError):
    """Yanıt belgelenmiş şemaya uymuyor."""


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _SchemaError(f"{name} sayı değil")
    return float(value)


def _unit(value: Any, name: str) -> float:
    number = _number(value, name)
    if not 0.0 <= number <= 1.0:
        raise _SchemaError(f"{name} 0–1 aralığında değil")
    return number


def _tokens(usage: Any, field: str) -> int | None:
    value = usage.get(field) if isinstance(usage, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None  # bildirilmedi: uydurulmaz
    return value


def _retry_after(response: httpx.Response) -> float | None:
    """`retry-after-ms` veya `retry-after` (saniye) başlığı; ayrıştırılamazsa None."""
    for header, scale in (("retry-after-ms", 1000.0), ("retry-after", 1.0)):
        raw = response.headers.get(header)
        if raw is None:
            continue
        try:
            value = float(raw) / scale
        except ValueError:
            continue
        if value >= 0:
            return value
    return None


def _status_for(code: int) -> CallStatus:
    if code in (401, 403):
        return CallStatus.AUTH_ERROR
    if code == 408:
        return CallStatus.TIMEOUT
    if code == 429:
        return CallStatus.RATE_LIMITED
    if code >= 500:  # 529 (aşırı yük) dahil
        return CallStatus.UNAVAILABLE
    return CallStatus.BAD_REQUEST  # 400/422/diğer 4xx: bizim isteğimizde hata, yeniden denenmez


class JevProvider:
    name = "jev"
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        price: PriceEntry = JEV_1_13,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key:
            raise ValueError("Jev API anahtarı boş olamaz.")
        self.model = model
        self.price: PriceEntry | None = price
        # Otomatik yeniden deneme yok: retry politikası retry.py'dedir (sınırlı ve kayıtlı).
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_s,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def __repr__(self) -> str:  # anahtar asla görünmez
        return f"JevProvider(model={self.model!r})"

    def close(self) -> None:
        self._client.close()

    # --- istek ---

    def build_request(self, data: DecisionInput, questions: tuple[Question, ...]) -> dict[str, Any]:
        return {
            # Yalnızca karar için gereken alanlar; kullanıcı adı, kimlik, geçmiş gönderilmez.
            "state": {
                "title": data.title,
                "description": data.description,
                "location": data.location,
            },
            "model": self.model,
            "questions": {q.value: question_definition(q) for q in questions},
        }

    # --- yanıt ---

    @staticmethod
    def _judgment(question: Question, answer: Any) -> Judgment:
        if not isinstance(answer, dict):
            raise _SchemaError(f"{question.value} yanıtı nesne değil")
        if question in (Question.CATEGORY, Question.PRIORITY):
            if answer.get("type") != "choice":
                raise _SchemaError(f"{question.value}: tür 'choice' değil")
            options = option_codes(question)
            choice = answer.get("choice")
            if choice not in options:
                raise _SchemaError(f"{question.value}: bilinmeyen seçenek")
            probabilities = answer.get("probabilities")
            if not isinstance(probabilities, dict) or not set(probabilities) <= set(options):
                raise _SchemaError(f"{question.value}: olasılıklar geçersiz")
            parsed = {key: _unit(value, "olasılık") for key, value in probabilities.items()}
            if abs(sum(parsed.values()) - 1.0) > PROBABILITY_TOLERANCE:
                raise _SchemaError(f"{question.value}: olasılıklar 1'e toplanmıyor")
            confidence = _unit(answer.get("confidence"), "confidence")
            return Judgment(
                question,
                choice,
                parsed,
                confidence,
                ConfidenceKind.JEV_CONFIDENCE,
                len(options),
                source="jev",
            )
        if answer.get("type") != "noul":
            raise _SchemaError(f"{question.value}: tür 'noul' değil")
        p_yes = _unit(answer.get("noul"), "noul")
        # Noul için Jev ayrı güven vermez; evet/hayır kenar payını biz türetir, öyle işaretleriz.
        return Judgment(
            question,
            p_yes >= 0.5,
            {"yes": p_yes, "no": 1.0 - p_yes},
            abs(2 * p_yes - 1),
            ConfidenceKind.DERIVED_MARGIN,
            2,
            source="jev",
        )

    # --- çağrı ---

    def classify(
        self, data: DecisionInput, questions: tuple[Question, ...], strategy: StrategyName
    ) -> ProviderResult:
        payload = self.build_request(data, questions)
        started = datetime.now(UTC)
        t0 = time.perf_counter()

        def record(status: CallStatus, **fields: Any) -> CallRecord:
            return CallRecord(
                strategy=strategy,
                provider=self.name,
                model=fields.pop("model", self.model),
                prompt_version=self.prompt_version,
                questions=questions,
                status=status,
                started_at=started,
                duration_ms=max(1, round((time.perf_counter() - t0) * 1000)),
                **fields,
            )

        try:
            response = self._client.post(ENDPOINT, json=payload)
        except httpx.TimeoutException:
            raise ProviderError(
                CallStatus.TIMEOUT,
                "Jev zaman aşımı",
                record(CallStatus.TIMEOUT, error="zaman aşımı"),
            ) from None
        except httpx.TransportError as exc:
            reason = type(exc).__name__  # yalnızca tür; ayrıntı (adres vb.) kayda girmez
            raise ProviderError(
                CallStatus.UNAVAILABLE,
                "Jev'e ulaşılamadı",
                record(CallStatus.UNAVAILABLE, error=f"bağlantı hatası ({reason})"),
            ) from None

        request_id = response.headers.get("x-typesafe-request-id")
        if response.status_code != 200:
            status = _status_for(response.status_code)
            raise ProviderError(
                status,
                f"Jev HTTP {response.status_code}",
                record(status, request_id=request_id, error=f"HTTP {response.status_code}"),
                retry_after=_retry_after(response) if status is CallStatus.RATE_LIMITED else None,
            )

        try:
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
                raise _SchemaError("answers eksik")
            answers = body["answers"]
            judgments = tuple(self._judgment(q, answers.get(q.value)) for q in questions)
        except (ValueError, _SchemaError) as exc:
            detail = str(exc) if isinstance(exc, _SchemaError) else "JSON değil"
            raise ProviderError(
                CallStatus.SCHEMA_ERROR,
                "Jev yanıtı şemaya uymuyor",
                record(CallStatus.SCHEMA_ERROR, request_id=request_id, error=f"şema: {detail}"),
            ) from None

        usage = body.get("usage")
        reported_model = body.get("model")
        call = record(
            CallStatus.OK,
            model=reported_model
            if isinstance(reported_model, str) and reported_model
            else self.model,
            input_tokens=_tokens(usage, "input_tokens"),
            output_tokens=_tokens(usage, "output_tokens"),
            request_id=request_id,
        )
        return ProviderResult(judgments, call)
