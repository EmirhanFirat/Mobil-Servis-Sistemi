"""Canlı çalıştırma öncesi YAKLAŞIK ücret tahmini. Bu bir ÖLÇÜM DEĞİLDİR: gerçek token sayıları
sağlayıcı yanıtından gelir; buradaki sayılar, gerçek istek gövdelerinin uzunluğundan ve açıkça
yazılı varsayımlardan türetilir. Amaç, kullanıcının makul bir toplam harcama sınırı
(`--max-cost-usd`) belirleyebilmesidir; sınır, çalıştırıcıda gerçek ücretlere göre uygulanır.

Hiçbir ağ isteği yapılmaz: sağlayıcılar yalnızca istek gövdesini üretmek için kurulur.
"""

import json
import math
from dataclasses import dataclass
from decimal import Decimal

from app.decision.contract import ALL_QUESTIONS
from app.decision.jev import JevProvider
from app.decision.llm_anthropic import MAX_TOKENS, AnthropicProvider
from app.decision.pricing import compute_cost
from app.decision.retry import DEFAULT_RETRY
from app.evaluation.dataset import Sample

# Varsayımlar (ölçülmedi; gerçek değerler farklı olabilir). Muhafazakâr yönde seçildi.
CHARS_PER_TOKEN = 3  # JSON ve Türkçe metin için düşük bir oran → token sayısı yüksek tahmin edilir
FORCED_TOOL_OVERHEAD_TOKENS = 588  # Claude Haiku 4.5, zorunlu araç çağrısı (resmî fiyat sayfası)
TYPICAL_LLM_OUTPUT_TOKENS = 160  # altı soru için kabaca; üst sınır MAX_TOKENS

PLANNABLE = ("jev_only", "llm_only", "hybrid")


@dataclass(frozen=True)
class PlanLine:
    strategy: str
    calls: str
    typical_low_usd: Decimal
    typical_high_usd: Decimal
    worst_usd: Decimal


@dataclass(frozen=True)
class PlanEstimate:
    n_samples: int
    lines: tuple[PlanLine, ...]
    typical_low_usd: Decimal
    typical_high_usd: Decimal
    worst_usd: Decimal


def _tokens(payload: dict) -> int:
    return math.ceil(len(json.dumps(payload, ensure_ascii=False)) / CHARS_PER_TOKEN)


def estimate_plan(samples: list[Sample], strategy_names: tuple[str, ...]) -> PlanEstimate:
    unknown = set(strategy_names) - set(PLANNABLE)
    if unknown:
        raise ValueError(f"Tahmin yalnızca gerçek stratejiler için: {sorted(unknown)}")
    jev = JevProvider("plan-only")  # yalnızca istek gövdesi için; ağ isteği yapılmaz
    llm = AnthropicProvider("plan-only")
    attempts = DEFAULT_RETRY.max_attempts
    try:
        jev_typical = Decimal(0)
        llm_typical = Decimal(0)
        llm_worst = Decimal(0)
        for sample in samples:
            data = sample.to_input()
            jev_in = _tokens(jev.build_request(data, ALL_QUESTIONS))
            llm_in = _tokens(llm.build_request(data, ALL_QUESTIONS)) + FORCED_TOOL_OVERHEAD_TOKENS
            jev_typical += compute_cost(jev.price, jev_in, 0) or Decimal(0)
            llm_typical += compute_cost(llm.price, llm_in, TYPICAL_LLM_OUTPUT_TOKENS) or Decimal(0)
            llm_worst += compute_cost(llm.price, llm_in, MAX_TOKENS) or Decimal(0)
    finally:
        jev.close()
        llm.close()

    # En kötü durum: her çağrı tüm deneme haklarını kullanır ve çıktı üst sınıra dayanır.
    jev_worst = jev_typical * attempts
    llm_worst *= attempts
    lines: list[PlanLine] = []
    for name in strategy_names:
        if name == "jev_only":
            lines.append(PlanLine(name, "1 Jev", jev_typical, jev_typical, jev_worst))
        elif name == "llm_only":
            lines.append(PlanLine(name, "1 LLM", llm_typical, llm_typical, llm_worst))
        else:
            # Hibrit: her zaman Jev; LLM yalnızca Jev'in güvenmediği sorular için (oran bilinmiyor).
            lines.append(
                PlanLine(
                    name,
                    "1 Jev + 0–1 LLM",
                    jev_typical,
                    jev_typical + llm_typical,
                    jev_worst + llm_worst,
                )
            )
    return PlanEstimate(
        n_samples=len(samples),
        lines=tuple(lines),
        typical_low_usd=sum((line.typical_low_usd for line in lines), Decimal(0)),
        typical_high_usd=sum((line.typical_high_usd for line in lines), Decimal(0)),
        worst_usd=sum((line.worst_usd for line in lines), Decimal(0)),
    )


def _usd(value: Decimal) -> str:
    return f"{value:.4f}"


def format_plan(plan: PlanEstimate) -> str:
    rows = [
        "Canlı çalıştırma planı (YAKLAŞIK TAHMİN — ölçüm değildir)",
        f"Örnek sayısı: {plan.n_samples} (her strateji aynı örnekleri görür)",
        "",
        f"{'strateji':<10} {'çağrı/örnek':<18} {'tipik (USD)':<20} {'en kötü (USD)':<14}",
    ]
    for line in plan.lines:
        typical = (
            _usd(line.typical_low_usd)
            if line.typical_low_usd == line.typical_high_usd
            else f"{_usd(line.typical_low_usd)}–{_usd(line.typical_high_usd)}"
        )
        rows.append(
            f"{line.strategy:<10} {line.calls:<18} {typical:<20} {_usd(line.worst_usd):<14}"
        )
    total_typical = f"{_usd(plan.typical_low_usd)}–{_usd(plan.typical_high_usd)}"
    rows += [
        f"{'TOPLAM':<10} {'':<18} {total_typical:<20} {_usd(plan.worst_usd):<14}",
        "",
        "Varsayımlar:",
        f"- Girdi token'ı: istek gövdesi uzunluğu / {CHARS_PER_TOKEN} (muhafazakâr), Anthropic'te "
        f"+{FORCED_TOOL_OVERHEAD_TOKENS} zorunlu araç çağrısı sistem istemi.",
        f"- Çıktı token'ı: LLM tipik {TYPICAL_LLM_OUTPUT_TOKENS}, en kötü {MAX_TOKENS} "
        "(max_tokens); Jev çıktısı ücretsiz.",
        f"- En kötü durum: her çağrı {DEFAULT_RETRY.max_attempts} deneme hakkını kullanır.",
        "- Hibritte LLM'e giden soru oranı bilinmiyor: alt sınır yalnızca Jev, üst sınır tüm "
        "sorular LLM'e gider.",
        "- Gerçek token sayıları ve ücret sağlayıcı yanıtından gelir ve farklı olabilir; fiyatlar "
        "docs/SAGLAYICILAR.md'deki tarihli değerlerdir (canlı öncesi yeniden doğrulanmalı).",
        "- Harcama sınırı (--max-cost-usd) çalıştırıcıda gerçek ücretlere göre uygulanır; "
        "aşım en çok bir örneğin ücreti kadar olabilir.",
    ]
    return "\n".join(rows)
