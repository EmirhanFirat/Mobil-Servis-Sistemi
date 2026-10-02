"""Ekonomik LLM adaptörü: Anthropic Messages API (varsayılan Claude Haiku 4.5), ham HTTP ile
POST /v1/messages (platform.claude.com/docs/en/api/messages). SDK kullanılmaz: resmî SDK `httpx2`
getirir (bkz. DECISIONS D7) ve kendi yeniden denemesini yapar; burada retry politikası
retry.py'dedir (sınırlı, kayıtlı, maliyeti toplama dahil). Bu modül kendi başına ağ isteği
YAPMAZ; yalnızca bir `AnthropicProvider` örneği oluşturulup `classify` çağrılırsa istek atılır.
Örnek, ücretli çağrılar açık değilse fabrikadan alınamaz (factory.py).

Güvenlik ve dürüstlük (Jev adaptörüyle aynı ilkeler):
- API anahtarı yalnızca `x-api-key` başlığındadır; kayıtlara, hata mesajlarına, repr'a girmez.
- Kullanıcı metni yalnızca kullanıcı mesajında JSON verisi olarak gider; sistem istemi ve araç
  şeması sabittir (llm_prompt.py). `tool_choice` ile `submit_judgments` aracı zorlanır.
- Hata mesajlarına sunucu yanıt gövdesi konmaz (kullanıcı metnini yansıtabilir); yalnızca durum
  kodu ve `error.type` (küçük harf ve alt çizgiden oluşan, sınırlı bir belirteç).
- Yargılardaki güven, modelin KENDİ yazdığı sayıdır (`self_reported`); olasılık verilmez (None).
  Jev güveniyle karşılaştırılamaz.
- Kullanım (token) yanıtta yoksa None kalır; uydurulmaz.
"""

import re
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
from app.decision.http_common import (
    SchemaError,
    reported_tokens,
    retry_after_seconds,
    status_for_http,
    unit,
)
from app.decision.jev_questions import option_codes
from app.decision.llm_prompt import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TOOL_NAME,
    build_tool,
    render_state,
)
from app.decision.pricing import CLAUDE_HAIKU_4_5, PriceEntry
from app.decision.providers import ProviderError, ProviderResult

ENDPOINT = "/v1/messages"
DEFAULT_BASE_URL = "https://api.anthropic.com"
# Sabitlenmiş sürüm (takma ad `claude-haiku-4-5` değil): sonuçlar tam modele bağlanır.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
API_VERSION = "2023-06-01"
# Zorunlu araç çağrısı kısa bir nesne üretir; 30 sn yalnızca ağ/yük dalgalanması payıdır.
DEFAULT_TIMEOUT_S = 30.0
# Altı sorunun yanıtı ~150 token; kesilirse (max_tokens) şema hatası sayılır ve yeniden denenir.
MAX_TOKENS = 600

_ERROR_TYPE = re.compile(r"[a-z_]{1,40}")
_STOP_REASONS = frozenset({"end_turn", "max_tokens", "stop_sequence", "tool_use", "refusal"})
_CACHE_FIELDS = ("cache_creation_input_tokens", "cache_read_input_tokens")


def _error_type(response: httpx.Response) -> str | None:
    """Hata gövdesindeki `error.type` (ör. overloaded_error); yalnızca sınırlı bir belirteçse."""
    try:
        body = response.json()
    except ValueError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    value = error.get("type") if isinstance(error, dict) else None
    if isinstance(value, str) and _ERROR_TYPE.fullmatch(value):
        return value
    return None


class AnthropicProvider:
    name = "anthropic"
    prompt_version = PROMPT_VERSION
    # Harcama üst sınırı (budget.py) için: zorunlu araç çağrısının sistem istemi token'ları (resmî
    # fiyat sayfası, Haiku 4.5) ve istekteki sert çıktı tavanı.
    fixed_overhead_tokens = 588
    max_output_tokens = MAX_TOKENS

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        # Tekrarlanabilirlik için 0. Claude Opus 4.7+ varsayılan dışı değeri reddeder (400);
        # o modellerde None verilerek alan hiç gönderilmez.
        temperature: float | None = 0.0,
        price: PriceEntry | None = CLAUDE_HAIKU_4_5,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key:
            raise ValueError("Anthropic API anahtarı boş olamaz.")
        self.model = model
        self.temperature = temperature
        self.price: PriceEntry | None = price
        # Otomatik yeniden deneme yok: retry politikası retry.py'dedir (sınırlı ve kayıtlı).
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_s,
            transport=transport,
            headers={
                "x-api-key": api_key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
                "accept": "application/json",
            },
        )

    def __repr__(self) -> str:  # anahtar asla görünmez
        return f"AnthropicProvider(model={self.model!r})"

    def close(self) -> None:
        self._client.close()

    # --- istek ---

    def build_request(self, data: DecisionInput, questions: tuple[Question, ...]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "tools": [build_tool(questions)],
            "tool_choice": {"type": "tool", "name": TOOL_NAME},
            # Yalnızca karar için gereken alanlar, JSON verisi olarak; kullanıcı adı, kimlik ve
            # geçmiş gönderilmez.
            "messages": [{"role": "user", "content": render_state(data)}],
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        return payload

    # --- yanıt ---

    def _judgment(self, question: Question, answer: Any) -> Judgment:
        if not isinstance(answer, dict):
            raise SchemaError(f"{question.value} yanıtı nesne değil")
        confidence = unit(answer.get("confidence"), "confidence")
        value = answer.get("answer")
        if question in (Question.CATEGORY, Question.PRIORITY):
            options = option_codes(question)
            if not isinstance(value, str) or value not in options:
                raise SchemaError(f"{question.value}: bilinmeyen seçenek")
            n_options = len(options)
        else:
            if not isinstance(value, bool):
                raise SchemaError(f"{question.value}: evet/hayır değil")
            n_options = 2
        # LLM olasılık dağılımı vermez; güven modelin kendi yazdığı, kalibre olmayan sayıdır.
        return Judgment(
            question,
            value,
            None,
            confidence,
            ConfidenceKind.SELF_REPORTED,
            n_options,
            source=self.name,
        )

    @staticmethod
    def _tool_input(body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise SchemaError("gövde nesne değil")
        stop = body.get("stop_reason")
        stop_label = stop if stop in _STOP_REASONS else "bilinmiyor"
        if stop == "max_tokens":
            raise SchemaError("yanıt kesildi (max_tokens)")
        content = body.get("content")
        if not isinstance(content, list):
            raise SchemaError("content eksik")
        calls = [
            block
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "tool_use"
            and block.get("name") == TOOL_NAME
        ]
        if not calls:
            raise SchemaError(f"{TOOL_NAME} çağrısı yok (stop_reason={stop_label})")
        if len(calls) > 1:
            raise SchemaError(f"{TOOL_NAME} birden çok kez çağrıldı")
        tool_input = calls[0].get("input")
        if not isinstance(tool_input, dict):
            raise SchemaError("araç girdisi nesne değil")
        return tool_input

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
                "Anthropic zaman aşımı",
                record(CallStatus.TIMEOUT, error="zaman aşımı"),
            ) from None
        except httpx.TransportError as exc:
            reason = type(exc).__name__  # yalnızca tür; ayrıntı (adres vb.) kayda girmez
            raise ProviderError(
                CallStatus.UNAVAILABLE,
                "Anthropic'e ulaşılamadı",
                record(CallStatus.UNAVAILABLE, error=f"bağlantı hatası ({reason})"),
            ) from None

        request_id = response.headers.get("request-id")
        if response.status_code != 200:
            status = status_for_http(response.status_code)
            wait = retry_after_seconds(response) if status is CallStatus.RATE_LIMITED else None
            error_type = _error_type(response)
            detail = f"HTTP {response.status_code}" + (f" ({error_type})" if error_type else "")
            raise ProviderError(
                status,
                f"Anthropic HTTP {response.status_code}",
                record(status, request_id=request_id, error=detail),
                retry_after=wait,
            )

        try:
            body = response.json()
            tool_input = self._tool_input(body)
            judgments = tuple(self._judgment(q, tool_input.get(q.value)) for q in questions)
        except (ValueError, SchemaError) as exc:
            detail = str(exc) if isinstance(exc, SchemaError) else "JSON değil"
            tokens, note = self._usage(response)
            raise ProviderError(
                CallStatus.SCHEMA_ERROR,
                "Anthropic yanıtı şemaya uymuyor",
                # Şemaya uymayan yanıt da ücretlendirilir: gelen kullanım kaydedilir.
                record(
                    CallStatus.SCHEMA_ERROR,
                    request_id=request_id,
                    error="; ".join(filter(None, (f"şema: {detail}", note))),
                    **tokens,
                ),
            ) from None

        reported_model = body.get("model")
        tokens, note = self._usage(response)
        return ProviderResult(
            judgments,
            record(
                CallStatus.OK,
                model=reported_model
                if isinstance(reported_model, str) and reported_model
                else self.model,
                request_id=request_id,
                error=note,
                **tokens,
            ),
        )

    @staticmethod
    def _usage(response: httpx.Response) -> tuple[dict[str, int | None], str | None]:
        """(token alanları, not). Bildirilmeyen sayı None kalır. Önbellek kullanılmıyor; yine de
        sıfırdan büyük önbellek token'ı bildirilirse (farklı fiyatlanır) girdi maliyeti bilinmez
        ve bu nottan görülür."""
        try:
            body = response.json()
        except ValueError:
            return {"input_tokens": None, "output_tokens": None}, None
        usage = body.get("usage") if isinstance(body, dict) else None
        tokens = {
            "input_tokens": reported_tokens(usage, "input_tokens"),
            "output_tokens": reported_tokens(usage, "output_tokens"),
        }
        if any(reported_tokens(usage, name) for name in _CACHE_FIELDS):
            tokens["input_tokens"] = None
            return tokens, "beklenmeyen önbellek kullanımı; girdi maliyeti bilinmiyor"
        return tokens, None
