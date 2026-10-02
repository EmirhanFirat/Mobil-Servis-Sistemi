"""Canlı çalıştırma ön kontrolü. Ağ isteği YAPMAZ ve anahtar değerlerini ASLA yazdırmaz: yalnızca
"tanımlı mı" bilgisi gösterilir (Settings üzerinden, değer okunmadan `is not None`).

Gösterdikleri: anahtar/bayrak durumu, kullanılacak model ve tarihli fiyatlar, bütçe defteri durumu
(önceki harcama ve çözülmemiş rezervasyonlar dahil), seçilen örnekler, maliyet planı ve çalıştırılacak
komutun kendisi. Ücretli çağrıların açık olması ön kontrol için gerekmez; ama gerçek çalıştırma için
gerekir ve eksikse "EKSİK" olarak listelenir.
"""

from decimal import Decimal
from pathlib import Path

from app.config import Settings
from app.decision.budget_ledger import BudgetLedger, LedgerError
from app.decision.pricing import CLAUDE_HAIKU_4_5, JEV_1_13
from app.evaluation.plan import estimate_plan, format_plan
from app.evaluation.runner import ledger_path, select_samples


def build_preflight(
    *,
    settings: Settings,
    version: str,
    splits: tuple[str, ...],
    strategies: tuple[str, ...],
    max_cost_usd: Decimal,
    budget_id: str,
    budget_dir: Path | None,
    shuffle_seed: int | None,
    limit: int | None,
) -> tuple[str, bool]:
    """(metin, hazır mı). Anahtar değerleri metne girmez."""
    missing: list[str] = []
    lines = ["ÖN KONTROL (ağ isteği yok; anahtar değerleri gösterilmez)", ""]

    needs_jev = any(s in ("jev_only", "hybrid") for s in strategies)
    needs_llm = any(s in ("llm_only", "hybrid") for s in strategies)
    if needs_llm:
        defined = settings.anthropic_api_key is not None
        lines.append(f"- TALEPAKIS_ANTHROPIC_API_KEY: {'tanımlı' if defined else 'TANIMSIZ'}")
        if not defined:
            missing.append("TALEPAKIS_ANTHROPIC_API_KEY")
    if needs_jev:
        defined = settings.jev_api_key is not None
        lines.append(f"- TALEPAKIS_JEV_API_KEY: {'tanımlı' if defined else 'TANIMSIZ'}")
        if not defined:
            missing.append("TALEPAKIS_JEV_API_KEY")
    paid = settings.paid_model_calls_enabled
    lines.append(
        "- TALEPAKIS_PAID_MODEL_CALLS_ENABLED: "
        + ("açık" if paid else "KAPALI (gerçek çalıştırma için 'true' olmalı)")
    )
    if not paid:
        missing.append("TALEPAKIS_PAID_MODEL_CALLS_ENABLED=true")

    lines += ["", "Model ve fiyatlar (USD / 1M token; tarihli, canlı öncesi yeniden doğrulanmalı):"]
    entries = []
    if needs_jev:
        entries.append((JEV_1_13, settings.jev_model))
    if needs_llm:
        entries.append((CLAUDE_HAIKU_4_5, settings.anthropic_model))
    for price, configured in entries:
        same = (
            ""
            if configured == price.model
            else f"  !! AYARLI MODEL {configured} FİYAT TABLOSUNDA YOK"
        )
        lines.append(
            f"- {price.provider}: {price.model}  girdi {price.input_usd_per_mtok}, "
            f"çıktı {price.output_usd_per_mtok}  (kontrol: {price.checked_on}, {price.source_url}){same}"
        )
        if same:
            missing.append(f"{price.provider} modeli fiyat tablosuyla uyuşmuyor")

    lines += ["", "Bütçe defteri:"]
    path = ledger_path(budget_id, budget_dir)
    try:
        ledger = BudgetLedger.read(path)
    except LedgerError:
        lines.append(
            f"- {budget_id}: henüz yok; ilk çalıştırmada {max_cost_usd} USD ile açılır ({path})"
        )
    else:
        status = ledger.status()
        lines.append(
            f"- {budget_id}: sınır {status['cap_usd']} USD; kesinleşmiş harcama "
            f"{status['settled_total_usd']} (gerçek {status['settled_known_usd']}, en kötü bedelle "
            f"sayılan {status['settled_conservative_usd']}); çözülmemiş rezervasyon "
            f"{status['unresolved_reserved_usd']}; KALAN {status['remaining_usd']} USD"
        )
        if Decimal(status["cap_usd"]) != max_cost_usd:
            missing.append(
                f"verilen sınır ({max_cost_usd}) defterdeki sınırdan ({status['cap_usd']}) farklı"
            )
        if Decimal(status["remaining_usd"]) <= 0:
            missing.append("bütçe defterinde kalan bütçe yok")
    if path.with_suffix(".lock").exists():
        lines.append(
            f"- UYARI: kilit dosyası var ({path.with_suffix('.lock')}); çalıştırma reddedilir."
        )
        missing.append("bütçe defteri kilitli")

    samples = select_samples(version, splits, shuffle_seed=shuffle_seed, limit=limit)
    lines += ["", f"Seçilen örnekler ({len(samples)}; bölüm: {', '.join(splits)}):"]
    for sample in samples:
        lines.append(
            f"- {sample.id} [{sample.group}] {sample.title} — beklenen: "
            f"{sample.gold.category}/{sample.gold.priority}"
        )
    if "test" in splits:
        missing.append("nihai test bölümü bu denemede kullanılmaz")

    lines += ["", format_plan(estimate_plan(samples, strategies)), ""]
    command = (
        f"python -m app.evaluation run --splits {','.join(splits)}"
        + (f" --shuffle-seed {shuffle_seed}" if shuffle_seed is not None else "")
        + (f" --limit {limit}" if limit is not None else "")
        + f" --strategies {','.join(strategies)} --max-cost-usd {max_cost_usd} --budget-id {budget_id}"
    )
    lines += ["Çalıştırılacak komut:", f"  {command}", ""]
    ready = not missing
    lines.append("SONUÇ: HAZIR" if ready else "SONUÇ: EKSİK — " + "; ".join(missing))
    return "\n".join(lines), ready
