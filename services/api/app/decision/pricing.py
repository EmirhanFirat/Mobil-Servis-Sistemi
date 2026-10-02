"""Tarihli fiyat yapılandırması. Birim: USD / 1 milyon token. Decimal ile hesaplanır.

Fiyatlar sabit gerçek sayılmaz: her kayıt kaynağını ve kontrol tarihini taşır ve canlı deney
öncesi yeniden doğrulanmalıdır. Sağlayıcı kullanım (token) bildirmezse maliyet BİLİNMEZ (None);
sıfır sayılmaz. "Çıktı ücretsiz" olması çıktı token sayısının sıfır olduğu anlamına gelmez; çıktı
token'ı yine de kaydedilir.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class PriceEntry:
    provider: str
    model: str
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    source_url: str
    checked_on: date
    note: str = ""


# Jev: https://docs.typesafe.ai/models — "jev-1.13.0", girdi 0,042 USD / 1M token, çıktı ücretsiz.
JEV_1_13 = PriceEntry(
    provider="jev",
    model="jev-1.13.0",
    input_usd_per_mtok=Decimal("0.042"),
    output_usd_per_mtok=Decimal("0"),
    source_url="https://docs.typesafe.ai/models",
    checked_on=date(2026, 10, 2),
    note="Çıktı token'ları ücretsiz ama yine de kaydedilir. Canlı deney öncesi yeniden doğrula.",
)

# Mock sağlayıcılar gerçek ücret üretmez; sıfır fiyat, sonuçların gerçek ölçüm OLMADIĞINI gösterir.
MOCK_JEV = PriceEntry(
    "mock-jev", "mock-jev-1", Decimal(0), Decimal(0), "yok (mock)", date(2026, 10, 2)
)
MOCK_LLM = PriceEntry(
    "mock-llm", "mock-llm-1", Decimal(0), Decimal(0), "yok (mock)", date(2026, 10, 2)
)

PRICES: dict[tuple[str, str], PriceEntry] = {
    (entry.provider, entry.model): entry for entry in (JEV_1_13, MOCK_JEV, MOCK_LLM)
}


def compute_cost(
    price: PriceEntry | None, input_tokens: int | None, output_tokens: int | None
) -> Decimal | None:
    """Çağrı ücreti. Fiyat veya gerekli token sayısı bilinmiyorsa None (uydurulmaz)."""
    if price is None or input_tokens is None:
        return None
    cost = Decimal(input_tokens) / _MILLION * price.input_usd_per_mtok
    if price.output_usd_per_mtok != 0:
        if output_tokens is None:
            return None
        cost += Decimal(output_tokens) / _MILLION * price.output_usd_per_mtok
    return cost
