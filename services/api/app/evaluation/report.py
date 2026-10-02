"""Kayıtlı çıktılardan (run.json + predictions.jsonl) Markdown rapor ve metrics.json üretir.

Model çağrısı YAPMAZ: yalnızca kayıtlı tahminleri ve veri setini okur; aynı kayıtlardan aynı
rapor yeniden üretilir.
"""

import json
from decimal import Decimal
from pathlib import Path

from app.evaluation.dataset import dataset_sha256, load_samples
from app.evaluation.detail import SMALL_RUN_LIMIT, build_detail
from app.evaluation.metrics import (
    ClassScore,
    Prediction,
    Proportion,
    StrategyMetrics,
    compute_metrics,
)

MOCK_BANNER = (
    "> **UYARI — MOCK SONUÇLAR:** Bu raporda `mock_*` ile başlayan stratejiler deterministik sahte "
    "sağlayıcılarla üretilmiştir. Bu sayılar **gerçek model ölçümü değildir**; yalnızca değerlendirme "
    "boru hattını doğrular. Gerçek Jev/LLM sonuçları için canlı çalıştırma gerekir (henüz yapılmadı). "
    "`rule_based` ise gerçek bir tabandır (model çağrısı yapmaz)."
)

STOP_REASONS = {
    "budget": "bir sonraki karar/çağrı için en kötü durum ücreti kalan harcama sınırını aşacaktı",
    "estimate_violated": (
        "gerçek ücret rezerve edilen üst sınırı aştı; ücret tahmini varsayımı güvenilmez, durduruldu"
    ),
    "unbounded": "ücretin üst sınırı hesaplanamadı (fiyat veya çıktı tavanı bilinmiyor), durduruldu",
    "provider_error": (
        "bir sağlayıcı kalıcı bir istemci hatası döndürdü (anahtar veya istek hatası); bütçeyi "
        "boşuna yakmamak için hemen durduruldu"
    ),
    "provider_unavailable": (
        "bir stratejinin ardışık iki kararı tüm denemelerine rağmen başarısız oldu "
        "(sağlayıcı kesintisi); bütçeyi boşuna yakmamak için durduruldu"
    ),
    "interrupted": "çalıştırma elle kesildi",
    "error": "beklenmeyen bir hata oluştu",
}
SMALL_SAMPLE_WARNING = 30

LIMITATIONS = """\
## Sınırlamalar ve okuma notları

- **Sentetik veri:** örnekler yazar tarafından yazılmıştır; gerçek kullanımda başarı kanıtı değildir.
- **Etiketler gözden geçirilmedi:** tek etiketleyici; özellikle aciliyet etiketleri insan kontrolü bekliyor.
- **Küçük örneklem:** köşeli parantez içindeki aralıklar %95 Wilson güven aralığıdır ve geniştir; küçük farklar anlamlı sayılmamalıdır.
- **İncelemeye bırakılan örnekler başarı sayılmaz:** "otomatik karar doğruluğu" yalnızca insana gitmeyen kararlar içindir; otomasyon oranı (1 − inceleme oranı) birlikte okunmalıdır.
- **Maliyet:** bilinmeyen maliyet sıfır sayılmaz. Mock çağrıların fiyatı sıfırdır ve gerçek ücreti temsil etmez. Sabit sunucu/veritabanı giderleri dahil değildir.
- **Token:** farklı sağlayıcıların tokenizer'ları tam eşdeğer değildir; token sayıları doğrudan karşılaştırılmamalıdır. Mock token sayıları tahmindir.
- **Gecikme:** tek istek, eşzamanlılık 1, önbellek yok; uçtan uca (ağ ve yeniden deneme dahil). Sağlayıcının kendi raporladığı süre varsa ayrı tutulur (şu an yok).
- **Eksik bilgi:** v1'de yalnızca `location` ve `detail` etiketlidir.
"""


def _num(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def pct(p: Proportion) -> str:
    if p.value is None:
        return "—"
    text = f"%{_num(p.value * 100)}"
    if p.interval:
        low, high = p.interval
        text += f" [{_num(low * 100, 0)}–{_num(high * 100, 0)}]"
    return f"{text} ({p.successes}/{p.n})"


def usd(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:.6f}".replace(".", ",")


def cost_cell(m: StrategyMetrics) -> str:
    if m.calls_with_unknown_cost:
        return f"bilinmiyor ({m.calls_with_unknown_cost} çağrı; bilinen {usd(m.cost_known_usd)})"
    return usd(m.cost_known_usd)


def ms(value: float | None) -> str:
    return "—" if value is None else _num(value, 1)


def _score(s: ClassScore) -> str:
    def f(v):
        return "—" if v is None else _num(v, 2)

    return f"{f(s.precision)} / {f(s.recall)} / {f(s.f1)} (destek {s.support})"


def metrics_to_dict(m: StrategyMetrics) -> dict:
    def prop(p: Proportion) -> dict:
        return {"successes": p.successes, "n": p.n, "value": p.value, "wilson95": p.interval}

    return {
        "strategy": m.strategy,
        "n": m.n,
        "n_failed": m.n_failed,
        "is_mock": m.is_mock,
        "category_accuracy": prop(m.category_accuracy),
        "category_macro_f1": m.category_macro_f1,
        "category_confusion": m.category_confusion,
        "priority_accuracy": prop(m.priority_accuracy),
        "high_priority_recall": prop(m.high_priority_recall),
        "high_priority_missed": list(m.high_priority_missed),
        "review_rate": prop(m.review_rate),
        "automated_category_accuracy": prop(m.automated_category_accuracy),
        "automated_priority_accuracy": prop(m.automated_priority_accuracy),
        "review_precision": prop(m.review_precision),
        "review_recall": prop(m.review_recall),
        "missing_info": {
            k: {"precision": s.precision, "recall": s.recall, "f1": s.f1, "support": s.support}
            for k, s in m.missing_scores.items()
        },
        "latency_p50_ms": m.latency_p50_ms,
        "latency_p95_ms": m.latency_p95_ms,
        "calls_total": m.calls_total,
        "calls_failed": m.calls_failed,
        "input_tokens_known": m.input_tokens_known,
        "output_tokens_known": m.output_tokens_known,
        "calls_without_usage": m.calls_without_usage,
        "cost_known_usd": str(m.cost_known_usd),
        "calls_with_unknown_cost": m.calls_with_unknown_cost,
        "cost_total_usd": None if m.cost_total_usd is None else str(m.cost_total_usd),
        "cost_per_decision_usd": None
        if m.cost_per_decision_usd is None
        else str(m.cost_per_decision_usd),
        "cost_per_correct_usd": None
        if m.cost_per_correct_usd is None
        else str(m.cost_per_correct_usd),
        "correct_automated": m.correct_automated,
        "by_tag": {k: prop(v) for k, v in m.by_tag.items()},
    }


def _confusion_table(matrix: dict[str, dict[str, int]]) -> str:
    labels = list(matrix)
    lines = ["| gerçek ↓ / tahmin → | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for gold in labels:
        lines.append(f"| {gold} | " + " | ".join(str(matrix[gold][p]) for p in labels) + " |")
    return "\n".join(lines)


def _split_section(split: str, metrics: list[StrategyMetrics]) -> str:
    n = metrics[0].n if metrics else 0
    out = [f"## Bölüm: `{split}` ({n} örnek / strateji)", ""]

    out += [
        "### Özet",
        "",
        "| Strateji | Mock? | Kategori doğruluğu | Macro-F1 | Öncelik doğruluğu | Yüksek öncelik recall (kaçırılan) | İnceleme oranı | Hata oranı |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in metrics:
        macro = "—" if m.category_macro_f1 is None else _num(m.category_macro_f1, 2)
        out.append(
            f"| `{m.strategy}` | {'evet' if m.is_mock else 'hayır'} | {pct(m.category_accuracy)} | {macro} | "
            f"{pct(m.priority_accuracy)} | {pct(m.high_priority_recall)} ({len(m.high_priority_missed)}) | "
            f"{pct(m.review_rate)} | {pct(m.failure_rate)} |"
        )

    out += [
        "",
        "### İnceleme ve otomasyon",
        "",
        "| Strateji | Otomatik karar doğruluğu (kategori) | Otomatik karar doğruluğu (öncelik) | İnceleme kesinliği | İnceleme duyarlılığı |",
        "|---|---|---|---|---|",
    ]
    for m in metrics:
        out.append(
            f"| `{m.strategy}` | {pct(m.automated_category_accuracy)} | {pct(m.automated_priority_accuracy)} | "
            f"{pct(m.review_precision)} | {pct(m.review_recall)} |"
        )
    out += [
        "",
        "_İnceleme kesinliği: incelemeye gönderilenlerin gerçekten incelenmesi gerekenlere oranı. "
        "Duyarlılık: incelenmesi gerekenlerin ne kadarının gönderildiği._",
        "",
        "### Süre ve maliyet",
        "",
        "| Strateji | p50 ms | p95 ms | Toplam USD | USD / karar | USD / doğru otomatik karar | Çağrı (başarısız) | Girdi/çıktı token (bilinen) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in metrics:
        out.append(
            f"| `{m.strategy}` | {ms(m.latency_p50_ms)} | {ms(m.latency_p95_ms)} | {cost_cell(m)} | "
            f"{usd(m.cost_per_decision_usd)} | {usd(m.cost_per_correct_usd)} | "
            f"{m.calls_total} ({m.calls_failed}) | {m.input_tokens_known}/{m.output_tokens_known}"
            + (f" (+{m.calls_without_usage} çağrıda yok)" if m.calls_without_usage else "")
            + " |"
        )

    out += [
        "",
        "### Eksik bilgi (konum / açıklama) — kesinlik / duyarlılık / F1",
        "",
        "| Strateji | location | detail |",
        "|---|---|---|",
    ]
    for m in metrics:
        out.append(
            f"| `{m.strategy}` | {_score(m.missing_scores['location'])} | {_score(m.missing_scores['detail'])} |"
        )

    tags = sorted({tag for m in metrics for tag in m.by_tag})
    if tags:
        out += [
            "",
            "### Etiket (tag) bazında kategori doğruluğu",
            "",
            "| Strateji | " + " | ".join(tags) + " |",
            "|---|" + "---|" * len(tags),
        ]
        for m in metrics:
            out.append(
                f"| `{m.strategy}` | "
                + " | ".join(pct(m.by_tag[t]) if t in m.by_tag else "—" for t in tags)
                + " |"
            )

    out += ["", "### Kategori karışıklık matrisleri", ""]
    for m in metrics:
        out += [f"**`{m.strategy}`**", "", _confusion_table(m.category_confusion), ""]
    return "\n".join(out)


def build_report(run_dir: Path) -> tuple[str, dict]:
    """(Markdown, metrics sözlüğü). Model çağrısı yapmaz."""
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    version = run["dataset"]["version"]
    samples = {s.id: s for s in load_samples(version)}
    predictions = [
        Prediction.from_dict(json.loads(line))
        for line in (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    strategies = [s["name"] for s in run["strategies"]]
    any_mock = any(p.is_mock for p in predictions) or any(
        s.get("is_mock") for s in run["strategies"]
    )
    stopped = run.get("stopped_early")
    budget = run.get("budget") or {}

    # Karşılaştırma adil kalsın: yalnızca TÜM stratejilerin tamamladığı örnekler sayılır (kesinti
    # bir örneğin ortasında olduysa o örnek dışarıda bırakılır).
    per_sample: dict[str, int] = {}
    for p in predictions:
        per_sample[p.sample_id] = per_sample.get(p.sample_id, 0) + 1
    complete = {sid for sid, count in per_sample.items() if count >= len(strategies)}
    dropped = len(per_sample) - len(complete)
    predictions = [p for p in predictions if p.sample_id in complete]

    lines = [f"# Değerlendirme raporu — `{run['run_id']}`", ""]
    if any_mock:
        lines += [MOCK_BANNER, ""]
    if len(complete) < SMALL_SAMPLE_WARNING:
        lines += [
            f"> **KÜÇÜK ÖRNEKLEM ({len(complete)} örnek):** bu çalıştırma bağlantıyı, biçimi ve "
            "çağrı kayıtlarını doğrular. Doğruluk, güvenilirlik veya maliyet tasarrufu sonucu "
            "çıkarılamaz; aşağıdaki yüzdeler ve aralıklar yalnızca betimleyicidir.",
            "",
        ]
    if stopped:
        lines += [
            f"> **UYARI — ÇALIŞTIRMA YARIDA KALDI:** {STOP_REASONS.get(stopped['reason'], stopped['reason'])}. "
            f"{stopped.get('samples_completed', len(complete))}/{stopped.get('samples_planned', '?')} "
            "örnek tamamlandı; sonuçlar yalnızca tamamlanan örnekleri kapsar ve tam bir çalıştırmayla "
            "kıyaslanmamalıdır.",
            "",
        ]
    lines += [
        "## Çalıştırma kaydı",
        "",
        f"- Tarih: {run['created_at']}",
        f"- Kaynak commit: `{run['source_commit']}`"
        + (" (**çalışma ağacı kirli**)" if run.get("git_dirty") else ""),
        f"- Veri seti: `{version}` (sha256 `{run['dataset']['sha256'][:16]}…`), kaynak: {run['dataset']['source']}, "
        f"etiket durumu: {run['dataset']['label_status']}",
        f"- Bölümler: {', '.join(run['dataset']['splits_used'])} ({run['dataset']['n_samples']} örnek)",
        f"- Eşzamanlılık {run['config']['concurrency']}, önbellek: {run['config']['cache']}, "
        f"yeniden deneme: en çok {run['config']['retry']['max_attempts']} deneme",
        "- Stratejiler: " + ", ".join(f"`{s['name']}`" for s in run["strategies"]),
    ]
    # Yönlendirme sürümü yalnızca kaydında alan olan çalıştırmalarda yazılır (v2 ve sonrası). Eski
    # kayıtlarda alan yoktur (v1) ve geçmiş raporlar bayt bayt aynı yeniden üretilebilsin diye
    # raporlarına satır eklenmez.
    for strategy in run["strategies"]:
        if strategy.get("kind") == "hybrid" and strategy.get("routing_version"):
            thresholds = ", ".join(f"{q}={v}" for q, v in strategy["thresholds"].items())
            lines.append(
                f"- Hibrit yönlendirme `{strategy['routing_version']}` (`{strategy['name']}`): LLM'e "
                f"geçişi tetikleyebilen sorular: {', '.join(strategy['escalate_on']) or 'yok'}; "
                f"Jev güven eşikleri: {thresholds}"
            )
    if budget.get("live"):
        lines += [
            f"- **Bütçe defteri `{budget.get('budget_id')}`** — toplam sınır "
            f"{usd(Decimal(budget['max_cost_usd']))} USD (aynı kimlikli tüm çalıştırmaların toplamı)",
            f"  - Bu çalıştırmada **gerçek (sağlayıcı kullanımından hesaplanan) ücret:** "
            f"{usd(Decimal(budget['known_spent_usd']))} USD ({budget['calls']} çağrı)",
            f"  - Bu çalıştırmada **bilinemeyen ücret için en kötü durum bedeli** (gerçek harcama "
            f"olmayabilir, ücretsiz de sayılmadı): {usd(Decimal(budget['conservative_spent_usd']))} "
            f"USD ({budget['conservative_charges']} çağrı)",
            f"  - Önceki çalıştırmalardan kesinleşmiş harcama: "
            f"{usd(Decimal(budget['prior_spent_usd']))} USD; **çözülmemiş rezervasyon** (çöken "
            f"süreçten kalan, en kötü bedelle düşüldü): "
            f"{usd(Decimal(budget['prior_unresolved_reserved_usd']))} USD",
            f"  - Defter toplamı (önceki + bu çalıştırma): {usd(Decimal(budget['total_spent_usd']))} "
            f"USD; **kalan bütçe {usd(Decimal(budget['remaining_usd']))} USD**",
        ]
        if budget.get("bound_violations"):
            lines.append(
                f"  - **{budget['bound_violations']} çağrıda gerçek ücret rezervasyonu aştı** "
                "(üst sınır varsayımı ihlali; çalıştırma durduruldu)."
            )
        lines.append(
            "- Sınır yöntemi: her çağrıdan (ve retry'dan) önce ücretin üst sınırı rezerve edilir ve "
            "diske yazılır; garanti edilemeyenler için `app/decision/budget.py` başına ve "
            "`docs/DECISIONS.md` D28'e bak."
        )
    if run.get("aborted_prediction"):
        aborted = run["aborted_prediction"]
        lines.append(
            f"- Yarıda kesilen karar (neden: {STOP_REASONS.get(aborted.get('reason', 'budget'), '?')}): "
            f"`{aborted['strategy']}` / `{aborted['sample_id']}` "
            f"({len(aborted['calls'])} çağrı harcandı; tahmin sayılmadı, kayıtlar `run.json`'da)."
        )
    if dropped:
        lines.append(
            f"- Yarım kalan {dropped} örnek (tüm stratejiler tamamlamadığı için) rapor dışı bırakıldı."
        )
    lines.append("")
    current = dataset_sha256(version)
    if current != run["dataset"]["sha256"]:
        lines += [
            "> **UYARI:** veri seti, bu çalıştırmadan sonra değişmiş (sha256 uyuşmuyor). Sonuçlar eski veriyle üretilmiştir.",
            "",
        ]

    all_metrics: dict[str, dict] = {}
    for split in run["dataset"]["splits_used"]:
        split_predictions = [p for p in predictions if samples[p.sample_id].split == split]
        split_metrics = [compute_metrics(samples, split_predictions, name) for name in strategies]
        all_metrics[split] = {m.strategy: metrics_to_dict(m) for m in split_metrics}
        lines += [_split_section(split, split_metrics), ""]

    if 0 < len(complete) <= SMALL_RUN_LIMIT and (run_dir / "predictions.jsonl").exists():
        lines += [build_detail(run_dir)]
    lines += [LIMITATIONS]
    return "\n".join(lines) + "\n", {
        "run_id": run["run_id"],
        "stopped_early": stopped,
        "budget": budget,
        "splits": all_metrics,
    }


def write_report(run_dir: Path) -> Path:
    markdown, metrics = build_report(run_dir)
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    path = run_dir / "report.md"
    path.write_text(markdown, encoding="utf-8", newline="\n")
    return path
