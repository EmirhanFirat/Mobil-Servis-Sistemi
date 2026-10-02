"""Kesin harcama sınırı için muhafazakâr bütçe rezervasyonu.

Yöntem: HER sağlayıcı çağrısından (ve her retry'dan) ÖNCE, o çağrının ücretinin kanıtlanabilir bir
ÜST SINIRI bütçeden rezerve edilir; kalan bütçe bunu karşılamıyorsa çağrı HİÇ gönderilmez
(`BudgetExhausted`). Çağrı bitince rezervasyon bırakılır ve yerine gerçek ücret yazılır. Maliyeti
bilinemeyen çağrı (kullanım bildirilmedi, ağ hatası, zaman aşımı, farklı model sürümü) ÜCRETSİZ
SAYILMAZ: rezerve edilen en kötü durum bedeliyle sayılır. Böylece `harcanan + rezerve ≤ sınır`
her an korunur.

Üst sınır nasıl hesaplanır:
- Girdi: istek gövdesinin UTF-8 bayt uzunluğu + sağlayıcıya özgü sabit ek token'lar + küçük bir pay.
  Bir token en az bir bayttır; bu yüzden bayt sayısı herhangi bir bayt düzeyli (BPE) tokenizer'ın
  token sayısının üst sınırıdır. Gerçek sayıdan 2–3 kat büyüktür; bilerek aşırı muhafazakârdır.
- Çıktı: sağlayıcının çıktı ücreti sıfırdan büyükse `max_tokens` (istekteki sert tavan);
  bilinmiyorsa çağrı reddedilir. Çıktı ücreti sıfırsa (Jev) çıktı ücretsizdir.

GARANTİ EDİLEMEYENLER (dürüstlük için açıkça):
1. Fiyat tablosunun güncelliği: yanlış/eski fiyat sınırı yanlış hesaplatır (fiyatlar tarihli ve
   canlı öncesi doğrulanır).
2. Sağlayıcının faturasının raporladığı kullanım ve yayımlanmış fiyatla birebir örtüştüğü varsayımı
   (önbellek, indirim, vergi, asgari ücret gibi fatura kalemleri burada bilinmez).
3. Aynı anahtarın başka yerde (başka süreç, başka araç) kullanımı izlenmez.
4. Bayt ≥ token varsayımı bayt düzeyli tokenizer'lar için doğrudur; gerçek ücret rezervasyonu
   aşarsa (`bound_violations`) çalıştırma durdurulur ve olay kayda geçer; ama o çağrının ücreti
   zaten harcanmıştır (aşım tespit edilir, önlenemez).
5. Süreç çağrı ile kayıt arasında çökerse in-memory sayaç kaybolur; `run.json` yazılmayabilir.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.decision.budget_ledger import BudgetLedger
from app.decision.contract import (
    ALL_QUESTIONS,
    BudgetExhausted,
    DecisionInput,
    Question,
    StrategyName,
)
from app.decision.pricing import compute_cost
from app.decision.providers import Provider, ProviderError, ProviderResult
from app.decision.strategies import HybridStrategy, ProviderStrategy

_MILLION = Decimal(1_000_000)
# Rol işaretleri, mesaj çerçevesi ve belgelenmemiş küçük ekler için sabit pay (token).
SAFETY_SLACK_TOKENS = 256


def _inner(provider: object) -> Any:
    """Bütçe sarmalayıcısının arkasındaki gerçek sağlayıcı."""
    return getattr(provider, "inner", provider)


def max_call_cost(
    provider: Provider, data: DecisionInput, questions: tuple[Question, ...] = ALL_QUESTIONS
) -> Decimal:
    """Bu çağrının ücretinin üst sınırı (USD). Hesaplanamıyorsa BudgetExhausted: çağrı yapılamaz."""
    provider = _inner(provider)
    price = provider.price
    if price is None:
        raise BudgetExhausted(f"{provider.name}: fiyat bilinmiyor; ücret üst sınırı hesaplanamaz.")
    payload = provider.build_request(data, questions)  # type: ignore[attr-defined]
    body_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    overhead = getattr(provider, "fixed_overhead_tokens", 0)
    cost = (
        Decimal(body_bytes + overhead + SAFETY_SLACK_TOKENS) / _MILLION * price.input_usd_per_mtok
    )
    if price.output_usd_per_mtok != 0:
        max_output = getattr(provider, "max_output_tokens", None)
        if max_output is None:
            raise BudgetExhausted(
                f"{provider.name}: çıktı ücreti sıfır değil ama çıktı token üst sınırı bilinmiyor."
            )
        cost += Decimal(max_output) / _MILLION * price.output_usd_per_mtok
    return cost


def worst_decision_cost(strategy: object, data: DecisionInput) -> Decimal:
    """Bir stratejinin BİR karar için en kötü durum ücreti: her çağrı tüm deneme hakkını kullanır
    (hibritte hem Jev hem LLM aşaması, tüm sorularla)."""
    if isinstance(strategy, ProviderStrategy):
        return strategy.retry.max_attempts * max_call_cost(strategy.provider, data)
    if isinstance(strategy, HybridStrategy):
        per_attempt = max_call_cost(strategy.jev, data) + max_call_cost(strategy.llm, data)
        return strategy.retry.max_attempts * per_attempt
    return Decimal(0)  # kurallı taban: çağrı yok


@dataclass(frozen=True)
class Reservation:
    """Çağrıdan önce rezerve edilen tutar; `seq`, kalıcı defterdeki satırdır (varsa)."""

    amount: Decimal
    seq: int | None = None


@dataclass
class BudgetGuard:
    """Toplam harcama sınırı. Tek iş parçacığı için (çalıştırıcı eşzamanlılık 1).

    `ledger` verilirse sınır ve önceki harcama KALICI defterden gelir: aynı `budget_id` altındaki
    önceki çalıştırmaların kesinleşmiş harcaması ve çözülmemiş (çöken süreçten kalan)
    rezervasyonları kalan bütçeden DÜŞÜLÜR; her rezervasyon çağrıdan önce diske yazılır.
    """

    cap: Decimal
    ledger: BudgetLedger | None = None
    run_id: str = ""
    # Bu çalıştırmadan ÖNCE defterde olanlar (yalnızca ledger ile dolar).
    prior_spent: Decimal = Decimal(0)
    prior_unresolved: Decimal = Decimal(0)
    # Bu çalıştırma.
    spent: Decimal = Decimal(0)  # kesinleşmiş: gerçek ücret veya muhafazakâr (en kötü durum) bedel
    known_spent: Decimal = Decimal(0)  # yalnızca sağlayıcı kullanımıyla hesaplanan GERÇEK kısım
    conservative_spent: Decimal = Decimal(0)  # bilinemeyen ücret için en kötü durum bedelleri
    reserved: Decimal = Decimal(0)  # uçuştaki çağrıların rezervasyonu
    conservative_charges: int = 0  # maliyeti bilinemediği için en kötü durumla sayılan çağrılar
    bound_violations: int = 0  # gerçek ücreti rezervasyonu aşan çağrılar (varsayım ihlali)
    calls: int = 0

    def __post_init__(self) -> None:
        if self.ledger is not None:
            self.cap = self.ledger.cap  # sınırın tek kaynağı defterdir
            self.prior_spent = self.ledger.settled_total()
            self.prior_unresolved = self.ledger.pending_total()

    def remaining(self) -> Decimal:
        committed = self.prior_spent + self.prior_unresolved + self.spent + self.reserved
        return self.cap - committed

    def can_afford(self, amount: Decimal) -> bool:
        return amount <= self.remaining()

    def reserve(self, amount: Decimal, *, provider: str = "", model: str = "") -> Reservation:
        if not self.can_afford(amount):
            raise BudgetExhausted(
                f"Harcama sınırı: {amount:.6f} USD rezerve edilemez (kalan {self.remaining():.6f})."
            )
        seq = None
        if self.ledger is not None:
            # Kalıcı yazılmadan istek gönderilmez: yazma başarısızsa istisna çağrıyı durdurur.
            seq = self.ledger.begin(self.run_id, provider, model, amount)
        self.reserved += amount
        return Reservation(amount, seq)

    def settle(self, reservation: Reservation, actual: Decimal | None) -> None:
        """Rezervasyonu bırakır; yerine gerçek ücreti (biliniyorsa) ya da rezerve edilen en kötü
        durum bedelini yazar."""
        self.reserved -= reservation.amount
        self.calls += 1
        if actual is None:
            charge = reservation.amount
            self.conservative_charges += 1
            self.conservative_spent += charge
        else:
            charge = actual
            self.known_spent += actual
            if actual > reservation.amount:
                self.bound_violations += 1
        self.spent += charge
        if self.ledger is not None and reservation.seq is not None:
            self.ledger.settle(reservation.seq, charge, known=actual is not None)

    def summary(self) -> dict:
        total = self.prior_spent + self.spent
        return {
            "budget_id": None if self.ledger is None else self.ledger.budget_id,
            "max_cost_usd": str(self.cap),
            # Bu çalıştırma: gerçek (sağlayıcı kullanımından) ve en kötü durum rezervasyonu AYRI.
            "spent_usd": str(self.spent),
            "known_spent_usd": str(self.known_spent),
            "conservative_spent_usd": str(self.conservative_spent),
            "conservative_charges": self.conservative_charges,
            "bound_violations": self.bound_violations,
            "calls": self.calls,
            # Aynı bütçe defterinin önceki çalıştırmaları.
            "prior_spent_usd": str(self.prior_spent),
            "prior_unresolved_reserved_usd": str(self.prior_unresolved),
            # Defter toplamı: önceki + bu çalıştırma + çözülmemiş rezervasyonlar.
            "total_spent_usd": str(total),
            "remaining_usd": str(self.cap - total - self.prior_unresolved),
            "ledger": None if self.ledger is None else str(self.ledger.path),
        }


class BudgetedProvider:
    """Bir sağlayıcıyı bütçe korumasıyla sarar: her `classify` çağrısından önce rezervasyon."""

    def __init__(self, inner: Provider, guard: BudgetGuard):
        self.inner = inner
        self.guard = guard

    # Provider arayüzü: asıl sağlayıcıya yönlendirilir.
    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def model(self) -> str:
        return self.inner.model

    @property
    def prompt_version(self) -> str:
        return self.inner.prompt_version

    @property
    def price(self):
        return self.inner.price

    def __getattr__(self, attribute: str) -> Any:  # temperature, build_request, close, ...
        return getattr(self.inner, attribute)

    def _actual(self, record) -> Decimal | None:
        """Gerçek ücret; fiyat yalnızca yanıtı veren GERÇEK model sürümüyle eşleşiyorsa uygulanır
        (retry.py ile aynı kural). Hesaplanamıyorsa None."""
        price = self.inner.price
        if price is None or record.model != price.model:
            return None
        return compute_cost(price, record.input_tokens, record.output_tokens)

    def classify(
        self, data: DecisionInput, questions: tuple[Question, ...], strategy: StrategyName
    ) -> ProviderResult:
        amount = max_call_cost(self.inner, data, questions)
        # Yetersizse BudgetExhausted: istek HİÇ gönderilmez. Defter varsa rezervasyon çağrıdan ÖNCE
        # diske yazılır.
        reservation = self.guard.reserve(amount, provider=self.inner.name, model=self.inner.model)
        try:
            result = self.inner.classify(data, questions, strategy)
        except ProviderError as error:
            self.guard.settle(reservation, self._actual(error.record))
            raise
        except BaseException:
            # Beklenmeyen kesinti (ör. Ctrl+C): istek gitmiş olabilir; en kötü durumla say.
            self.guard.settle(reservation, None)
            raise
        self.guard.settle(reservation, self._actual(result.call))
        return result
