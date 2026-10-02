"""Örnek bazında ayrıntı: her strateji için tahmin, beklenen etiket, gerçek token, süre, retry ve ücret.

Küçük (birkaç örneklik) çalıştırmalar için tasarlandı: genel doğruluk veya tasarruf çıkarımı
YAPILMAZ; amaç, her çağrının gerçekte ne yaptığını tek tek görmektir. Kayıtlı çıktılardan üretilir
(model çağrısı yapmaz). Tahmin ve etiket içeriği olduğu gibi gösterilir; hiçbir şey uydurulmaz:
bildirilmeyen token/ücret "—" veya "bilinmiyor" olarak görünür, sıfır sayılmaz.
"""

import json
from decimal import Decimal
from pathlib import Path

from app.evaluation.dataset import MISSING_LABELS, load_samples

SMALL_RUN_LIMIT = 20  # bu kadar ya da daha az örnekte rapora da eklenir


def _usd(value: Decimal) -> str:
    return f"{value:.6f}".replace(".", ",")


def _mark(ok: bool) -> str:
    return "✓" if ok else "✗"


def _tokens(calls: list[dict], field: str) -> str:
    known = [c[field] for c in calls if c.get(field) is not None]
    missing = len(calls) - len(known)
    if not calls:
        return "—"
    if not known:
        return "bildirilmedi"
    total = sum(known)
    return f"{total}" + (f" (+{missing} çağrıda bildirilmedi)" if missing else "")


def _cost(calls: list[dict]) -> tuple[str, int]:
    """(bilinen ücret metni, ücreti bilinmeyen çağrı sayısı). Bilinmeyen sıfır sayılmaz."""
    if not calls:
        return "—", 0
    known = [Decimal(c["cost_usd"]) for c in calls if c.get("cost_usd") is not None]
    unknown = len(calls) - len(known)
    return (_usd(sum(known, Decimal(0))) if known else "—"), unknown


def _read_predictions(run_dir: Path) -> list[dict]:
    text = (run_dir / "predictions.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def build_detail(run_dir: Path) -> str:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    samples = {s.id: s for s in load_samples(run["dataset"]["version"])}
    strategy_order = [s["name"] for s in run["strategies"]]
    rows = _read_predictions(run_dir)

    order: list[str] = []
    by_sample: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_sample.setdefault(row["sample_id"], {})[row["strategy"]] = row
        if row["sample_id"] not in order:
            order.append(row["sample_id"])

    out = [
        "## Örnek bazında ayrıntı",
        "",
        "> Bu bölüm her çağrının gerçekte ne yaptığını gösterir. **Birkaç örnekten genel doğruluk, "
        "güvenilirlik veya maliyet tasarrufu sonucu çıkarılmaz.** ✓/✗ yalnızca bu örnekteki etiketle "
        "eşleşmeyi gösterir; etiketler tek kişiyce yazılmış ve gözden geçirilmemiştir. Bildirilmeyen "
        "token ve ücret sıfır sayılmaz.",
        "",
    ]
    for sample_id in order:
        sample = samples[sample_id]
        gold_missing = ", ".join(sample.gold.missing_info) or "yok"
        out += [
            f"### {sample.id} — {sample.title}",
            "",
            f"- Metin: {sample.description} (konum: {sample.location})",
            f"- **Beklenen etiket:** kategori `{sample.gold.category}`, öncelik "
            f"`{sample.gold.priority}`, eksik bilgi (konum/açıklama) {gold_missing}, "
            f"insan incelemesi {'bekleniyor' if sample.expected_review else 'beklenmiyor'}",
            "",
            "| Strateji | Tahmin: kategori | öncelik | eksik bilgi | inceleme | süre (ms) | "
            "çağrı / retry | girdi token | çıktı token | bilinen ücret (USD) | ücreti bilinmeyen çağrı |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        call_rows: list[str] = []
        for strategy in strategy_order:
            row = by_sample[sample_id].get(strategy)
            if row is None:
                out.append(f"| `{strategy}` | _bu örnekte çalışmadı_ |" + " |" * 9)
                continue
            calls = row.get("calls", [])
            retries = sum(1 for c in calls if c["status"] != "ok")
            cost_text, unknown = _cost(calls)
            latency = "—" if row.get("latency_ms") is None else f"{row['latency_ms']:.0f}"
            if row.get("failed"):
                prediction = "**BAŞARISIZ** (karar üretilemedi)" + " |" * 3 + " —"
            else:
                category = row.get("category") or "unclear"
                priority = row.get("priority") or "—"
                evaluated = sorted(set(row.get("missing_info", [])) & set(MISSING_LABELS))
                missing_ok = evaluated == sorted(sample.gold.missing_info)
                missing = ", ".join(row.get("missing_info", [])) or "yok"
                reasons = ", ".join(row.get("review_reasons", []))
                review = (
                    "gerekli" + (f" ({reasons})" if reasons else "")
                    if row.get("review_required")
                    else "gerekmiyor"
                )
                prediction = (
                    f"`{category}` {_mark(category == sample.gold.category)} | "
                    f"`{priority}` {_mark(priority == sample.gold.priority)} | "
                    f"{missing} {_mark(missing_ok)} | {review}"
                )
            out.append(
                f"| `{strategy}` | {prediction} | {latency} | {len(calls)} / {retries} | "
                f"{_tokens(calls, 'input_tokens')} | {_tokens(calls, 'output_tokens')} | "
                f"{cost_text} | {unknown} |"
            )
            for call in calls:
                cost = (
                    "bilinmiyor"
                    if call.get("cost_usd") is None
                    else _usd(Decimal(call["cost_usd"]))
                )
                call_rows.append(
                    f"| `{strategy}` | {call['provider']} / {call['model']} | {call['attempt']} | "
                    f"{call['status']} | {call.get('duration_ms', '—')} | "
                    f"{call.get('input_tokens') if call.get('input_tokens') is not None else '—'} | "
                    f"{call.get('output_tokens') if call.get('output_tokens') is not None else '—'} | "
                    f"{cost} | {call.get('request_id') or '—'} |"
                )
        if call_rows:
            out += [
                "",
                "<details><summary>Çağrı kayıtları</summary>",
                "",
                "| Strateji | Sağlayıcı / model | deneme | durum | süre (ms) | girdi | çıktı | "
                "ücret (USD) | istek kimliği |",
                "|---|---|---|---|---|---|---|---|---|",
                *call_rows,
                "",
                "</details>",
            ]
        out.append("")
    return "\n".join(out) + "\n"
