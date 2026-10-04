"""Kayıtlı deneyleri (evaluation/runs) panel için OKUR. Model çağrısı YAPMAZ.

Güvenlik ve dürüstlük ilkeleri:
- İstemciden dosya yolu alınmaz: yalnızca `run_id` (kesin desen) ve `sample_id` kabul edilir; çözülen
  yol, deney kök klasörünün DOĞRUDAN çocuğu olmak zorundadır (`..`, mutlak yol, sembolik bağ reddedilir).
- Hiçbir şey yazılmaz: bütçe defterine (evaluation/budget) dokunulmaz, hiçbir dosya değiştirilmez.
- Yanıtlar BEYAZ LİSTEYLE kurulur (alan alan seçilir): run.json'daki yerel dosya yolları (defter yolu),
  olası gizli değerler veya bilinmeyen alanlar yanıta sızamaz. API anahtarı hiçbir kayıtta tutulmaz;
  yine de yalnızca bilinen alanlar kopyalanır.
- Hesaplamalar mevcut rapor koduyla aynıdır (`app.evaluation.metrics.compute_metrics`,
  `app.evaluation.report.metrics_to_dict`); sayılar `report.md`/`metrics.json` ile aynı çıkar.
- Dosya yoksa/bozuksa/yarımsa rakam UYDURULMAZ: durum açıkça söylenir ve metrikler boş kalır.
- Bilinmeyen ücret sıfır sayılmaz (None). Ücretsiz çıktı tokenı "sıfır token" gibi gösterilmez:
  bildirilen token sayısı olduğu gibi verilir, çıktı fiyatının sıfır olduğu ayrıca işaretlenir.
"""

import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.evaluation.dataset import DatasetError, Sample, dataset_sha256, load_samples, repo_root
from app.evaluation.metrics import Prediction, Proportion, compute_metrics
from app.evaluation.report import SMALL_SAMPLE_WARNING, STOP_REASONS, metrics_to_dict

RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[A-Za-z0-9._+-]{1,80}$")
SAMPLE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
MAX_FILE_BYTES = 25 * 1024 * 1024  # bundan büyük dosya okunmaz (yanlışlıkla dev dosya)

ROUTING_V1 = "hibrit-yonlendirme-v1"
ROUTING_DESCRIPTIONS = {
    "hibrit-yonlendirme-v1": (
        "Tüm sorulara aynı Jev güven eşiği; güvenilmeyen HER soru (iletişim ve zaman bilgisi dahil) "
        "LLM'e geçerdi."
    ),
    "hibrit-yonlendirme-v2": (
        "Yalnızca ürün kararını etkileyen sorular (kategori, öncelik, konum, açıklama) LLM'e geçer; "
        "bilgi amaçlı belirsiz yanıtlar LLM'e gitmez."
    ),
}
SOURCE_TR = {"synthetic": "sentetik"}
SPLIT_TR = {"dev": "geliştirme", "val": "doğrulama", "test": "test"}

COMPARABILITY_NOTE = (
    "Bu ekran yalnızca AYNI deneydeki stratejileri karşılaştırır. Farklı deneyler (veri, örnekler, soru "
    "kapsamı, eşik, model veya hibrit yönlendirme sürümü) otomatik olarak doğrudan kıyaslanmaz."
)
TOKEN_NOTE = (
    "Farklı sağlayıcıların tokenizer'ları eşdeğer değildir; token sayıları birebir karşılaştırılmamalıdır. "
    "Ücret ayrı bir ölçümdür ve sağlayıcının bildirdiği kullanımdan hesaplanır."
)
UNCERTAINTY_FILE_NAME = "etiket_belirsizlikleri.json"


class ExperimentNotFound(Exception):
    """İstenen deney (veya örnek) bulunamadı ya da kimliği geçersiz."""


class ExperimentCorrupt(Exception):
    """Deney dosyası okunamıyor/bozuk. Ayrıntı yalnızca dosya adı ve satır numarasıdır."""


def default_runs_dir() -> Path:
    return repo_root() / "evaluation" / "runs"


def default_uncertainty_file() -> Path:
    return repo_root() / "evaluation" / UNCERTAINTY_FILE_NAME


# --------------------------------------------------------------------------- dosya erişimi


def resolve_run_dir(root: Path, run_id: str) -> Path:
    """`run_id` → doğrulanmış deney klasörü. Aksi hâlde ExperimentNotFound (içerik sızdırmaz)."""
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise ExperimentNotFound("Deney bulunamadı.")
    try:
        base = root.resolve(strict=True)
        candidate = (base / run_id).resolve(strict=True)
    except OSError as exc:
        raise ExperimentNotFound("Deney bulunamadı.") from exc
    if candidate.parent != base or not candidate.is_dir():
        raise ExperimentNotFound("Deney bulunamadı.")
    return candidate


def _read_json(path: Path) -> dict:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ExperimentCorrupt(f"{path.name} çok büyük; okunmadı.")
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExperimentCorrupt(f"{path.name} okunamadı veya geçerli JSON değil.") from exc
    if not isinstance(data, dict):
        raise ExperimentCorrupt(f"{path.name} beklenen biçimde değil.")
    return data


def _read_rows(path: Path) -> list[dict]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ExperimentCorrupt(f"{path.name} çok büyük; okunmadı.")
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise ExperimentCorrupt(f"{path.name} okunamadı.") from exc
    rows = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExperimentCorrupt(f"{path.name} satır {number} geçerli JSON değil.") from exc
        if not isinstance(row, dict) or "sample_id" not in row or "strategy" not in row:
            raise ExperimentCorrupt(f"{path.name} satır {number} beklenen biçimde değil.")
        rows.append(row)
    return rows


def load_uncertainties(
    version: str, path: Path | None = None
) -> tuple[dict[str, dict], str | None]:
    """Tartışmalı etiket işaretleri (yalnızca okunur; etiketler/sonuçlar değiştirilmez).

    (işaretler, hata): dosya yoksa hata None (işaret yok demektir); VAR ama okunamıyorsa hata metni
    döner ve çağıran bunu kullanıcıya gösterir: işaretler sessizce kaybolmaz."""
    path = path or default_uncertainty_file()
    if not path.exists():
        return {}, None
    try:
        # utf-8-sig: Windows araçlarının eklediği BOM'u da kabul eder.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        entries = data["datasets"].get(version, {})
    except (OSError, ValueError, KeyError, AttributeError):
        return {}, f"{path.name} okunamadı; tartışmalı etiket işaretleri gösterilemiyor."
    result = {}
    for sample_id, entry in entries.items():
        if isinstance(entry, dict):
            result[str(sample_id)] = {
                "status": str(entry.get("status", "gözden geçirme bekliyor")),
                "note": str(entry.get("note", "")),
            }
    return result, None


# --------------------------------------------------------------------------- yardımcılar


def _dec(value: Decimal | None) -> str | None:
    """Ondalık sayıyı bilimsel gösterim olmadan, 12 basamağa kadar metin yapar."""
    if value is None:
        return None
    return format(value.quantize(Decimal("1e-12")).normalize(), "f")


def _prop(p: Proportion) -> dict:
    return {
        "successes": p.successes,
        "n": p.n,
        "value": p.value,
        "wilson95": list(p.interval) if p.interval else None,
    }


def _hybrid_routing(run: dict) -> dict | None:
    for strategy in run.get("strategies", []):
        if strategy.get("kind") == "hybrid":
            version = strategy.get("routing_version")
            recorded = bool(version)
            version = version or ROUTING_V1
            return {
                "version": version,
                "recorded": recorded,
                "description": ROUTING_DESCRIPTIONS.get(version, ""),
            }
    return None


def _scope_label(run: dict) -> str:
    dataset = run.get("dataset", {})
    count = dataset.get("n_samples_completed", dataset.get("n_samples", 0))
    source = SOURCE_TR.get(dataset.get("source", ""), str(dataset.get("source", "")))
    splits = " + ".join(SPLIT_TR.get(s, s) for s in dataset.get("splits_used", []))
    label = f"{count} {source} {splits} örneği".replace("  ", " ")
    live = bool((run.get("budget") or {}).get("live"))
    mock = any(s.get("is_mock") for s in run.get("strategies", []))
    if mock:
        label += " — MOCK sonuçlar (gerçek model ölçümü değil)"
    elif live and count < SMALL_SAMPLE_WARNING:
        label += " — bağlantı denemesi"
    elif count < SMALL_SAMPLE_WARNING:
        label += " — küçük örneklem"
    return label


def _strategy_info(strategy: dict) -> dict:
    kind = strategy.get("kind")
    info: dict[str, Any] = {
        "name": str(strategy.get("name", "")),
        "kind": kind,
        "is_mock": bool(strategy.get("is_mock", False)),
        "provider": None,
        "model": None,
        "prompt_version": None,
        "temperature": None,
        "jev": None,
        "llm": None,
        "thresholds": None,
        "escalate_on": None,
        "llm_min_self_reported": None,
        "routing_version": None,
    }
    if kind == "hybrid":
        for part in ("jev", "llm"):
            sub = strategy.get(part) or {}
            info[part] = {
                "provider": sub.get("provider"),
                "model": sub.get("model"),
                "prompt_version": sub.get("prompt_version"),
                "temperature": sub.get("temperature"),
            }
        thresholds = strategy.get("thresholds")
        if isinstance(thresholds, dict):
            info["thresholds"] = {str(k): float(v) for k, v in thresholds.items()}
        escalate = strategy.get("escalate_on")
        if isinstance(escalate, list):
            info["escalate_on"] = [str(q) for q in escalate]
        info["llm_min_self_reported"] = strategy.get("llm_min_self_reported")
        info["routing_version"] = strategy.get("routing_version")
    else:
        info["provider"] = strategy.get("provider")
        info["model"] = strategy.get("model")
        info["prompt_version"] = strategy.get("prompt_version") or strategy.get("rules_version")
        info["temperature"] = strategy.get("temperature")
    return info


def _status(run: dict, has_predictions: bool) -> tuple[str, str | None]:
    if not has_predictions:
        return "missing_files", "predictions.jsonl bulunamadı; bu deney için rakam gösterilemez."
    dataset = run.get("dataset", {})
    planned = dataset.get("n_samples")
    done = dataset.get("n_samples_completed", planned)
    stopped = run.get("stopped_early")
    if stopped:
        reason = STOP_REASONS.get(stopped.get("reason", ""), str(stopped.get("reason", "")))
        return "partial", f"Çalıştırma yarıda kaldı ({done}/{planned} örnek): {reason}."
    if planned is not None and done is not None and done < planned:
        return "partial", f"Örneklerin yalnızca {done}/{planned} tanesi tamamlandı."
    return "complete", None


def _budget_view(run: dict) -> dict | None:
    budget = run.get("budget") or {}
    if not budget.get("live"):
        return None
    keys = (
        "budget_id",
        "max_cost_usd",
        "known_spent_usd",
        "conservative_spent_usd",
        "conservative_charges",
        "calls",
        "prior_spent_usd",
        "prior_unresolved_reserved_usd",
        "total_spent_usd",
        "remaining_usd",
    )
    # `ledger` (yerel dosya yolu) ve `method` bilerek alınmaz.
    return {key: budget.get(key) for key in keys}


def summarize_run(run_dir: Path) -> dict:
    """Seçici için özet. Bozuk/eksik deney de listelenir (durumuyla); rakam üretmez."""
    run_id = run_dir.name
    base: dict[str, Any] = {
        "id": run_id,
        "created_at": None,
        "source_commit": None,
        "git_dirty": None,
        "dataset": None,
        "strategies": [],
        "status": "corrupt",
        "status_detail": None,
        "live": False,
        "hybrid_routing": None,
        "scope_label": None,
        "files": {"predictions": False, "metrics": False, "report": False},
    }
    base["files"] = {
        "predictions": (run_dir / "predictions.jsonl").is_file(),
        "metrics": (run_dir / "metrics.json").is_file(),
        "report": (run_dir / "report.md").is_file(),
    }
    try:
        run = _read_json(run_dir / "run.json")
    except FileNotFoundError:
        base["status"] = "missing_files"
        base["status_detail"] = "run.json bulunamadı; bu klasör bir deney kaydı değil."
        return base
    except ExperimentCorrupt as exc:
        base["status_detail"] = str(exc)
        return base

    dataset = run.get("dataset") or {}
    version = dataset.get("version")
    matches = None
    if version:
        try:
            matches = dataset_sha256(version) == dataset.get("sha256")
        except (OSError, ValueError):
            matches = None
    status, detail = _status(run, base["files"]["predictions"])
    base.update(
        created_at=run.get("created_at"),
        source_commit=run.get("source_commit"),
        git_dirty=run.get("git_dirty"),
        dataset={
            "version": version,
            "sha256_short": (dataset.get("sha256") or "")[:16] or None,
            "splits": list(dataset.get("splits_used", [])),
            "n_samples": dataset.get("n_samples"),
            "n_completed": dataset.get("n_samples_completed", dataset.get("n_samples")),
            "source": dataset.get("source"),
            "label_status": dataset.get("label_status"),
            "matches_current": matches,
        },
        strategies=[_strategy_info(s) for s in run.get("strategies", [])],
        status=status,
        status_detail=detail,
        live=bool((run.get("budget") or {}).get("live")),
        hybrid_routing=_hybrid_routing(run),
        scope_label=_scope_label(run),
    )
    return base


def list_runs(root: Path) -> dict:
    """{runs_dir_found, runs}: yeni → eski. Klasör yoksa boş liste ve `runs_dir_found=False`."""
    try:
        base = root.resolve(strict=True)
    except OSError:
        return {"runs_dir_found": False, "runs": []}
    runs = []
    for entry in sorted(base.iterdir(), key=lambda p: p.name, reverse=True):
        if not RUN_ID_RE.fullmatch(entry.name):
            continue
        try:
            run_dir = resolve_run_dir(base, entry.name)
        except ExperimentNotFound:
            continue  # sembolik bağ vb.
        runs.append(summarize_run(run_dir))
    runs.sort(key=lambda r: r["created_at"] or r["id"], reverse=True)
    return {"runs_dir_found": True, "runs": runs}


# --------------------------------------------------------------------------- kullanım ve ücret


def _provider_usage(calls: list[dict], prices: list[dict]) -> list[dict]:
    """Çağrıları sağlayıcı/modele göre toplar. Bildirilmeyen token ve ücret sıfır sayılmaz."""
    output_free = {
        (p.get("provider"), p.get("model")): Decimal(str(p.get("output_usd_per_mtok", "1"))) == 0
        for p in prices
    }
    groups: dict[tuple[str, str], list[dict]] = {}
    for call in calls:
        groups.setdefault((str(call.get("provider")), str(call.get("model"))), []).append(call)
    result = []
    for (provider, model), items in groups.items():
        known = Decimal(0)
        unknown = 0
        for call in items:
            cost = call.get("cost_usd")
            if cost is None:
                unknown += 1
            else:
                known += Decimal(str(cost))
        in_known = sum(c["input_tokens"] for c in items if c.get("input_tokens") is not None)
        out_known = sum(c["output_tokens"] for c in items if c.get("output_tokens") is not None)
        result.append(
            {
                "provider": provider,
                "model": model,
                "is_mock": any(bool(c.get("is_mock")) for c in items),
                "calls": len(items),
                "retries": sum(1 for c in items if (c.get("attempt") or 1) > 1),
                "call_errors": sum(1 for c in items if c.get("status") != "ok"),
                "input_tokens": in_known,
                "output_tokens": out_known,
                "calls_without_input_usage": sum(1 for c in items if c.get("input_tokens") is None),
                "calls_without_output_usage": sum(
                    1 for c in items if c.get("output_tokens") is None
                ),
                "usage_estimated_calls": sum(1 for c in items if c.get("usage_estimated")),
                "output_tokens_free": bool(output_free.get((provider, model), False)),
                "cost_known_usd": _dec(known),
                "calls_with_unknown_cost": unknown,
            }
        )
    result.sort(key=lambda r: r["provider"])
    return result


def _hybrid_stats(rows: list[dict], strategy: dict) -> dict | None:
    """Hibritte LLM'e geçiş: kaç örnekte, hangi sorular için. Yalnızca kayıtlı çağrılardan."""
    llm_provider = (strategy.get("llm") or {}).get("provider")
    if not llm_provider or not rows:
        return None
    escalated = 0
    triggers: Counter[str] = Counter()
    for row in rows:
        llm_calls = [c for c in row.get("calls", []) if c.get("provider") == llm_provider]
        if not llm_calls:
            continue
        escalated += 1
        asked: list[str] = []
        for call in llm_calls:
            for question in call.get("questions") or []:
                if question not in asked:
                    asked.append(question)
        triggers.update(asked)
    jev_calls = sum(
        1 for row in rows for c in row.get("calls", []) if c.get("provider") != llm_provider
    )
    llm_calls_total = sum(
        1 for row in rows for c in row.get("calls", []) if c.get("provider") == llm_provider
    )
    return {
        "escalated": _prop(Proportion(escalated, len(rows))),
        "trigger_questions": dict(sorted(triggers.items(), key=lambda kv: (-kv[1], kv[0]))),
        "jev_stage_calls": jev_calls,
        "llm_stage_calls": llm_calls_total,
    }


def _strategy_result(
    samples: dict[str, Sample],
    predictions: list[Prediction],
    rows: list[dict],
    info: dict,
    raw_strategy: dict,
    prices: list[dict],
) -> dict:
    name = info["name"]
    m = compute_metrics(samples, predictions, name)
    md = metrics_to_dict(m)
    ok = m.n - m.n_failed
    automated = Proportion(ok - int(round(m.review_rate.successes)), ok)
    all_calls = [c for row in rows for c in row.get("calls", [])]
    usage = _provider_usage(all_calls, prices)
    known = m.cost_known_usd
    unknown = m.calls_with_unknown_cost
    per_completed = (known / ok) if ok and not unknown else None
    estimate_1000 = per_completed * 1000 if per_completed is not None else None
    return {
        "name": name,
        "info": info,
        "n": m.n,
        "n_failed": m.n_failed,
        "metrics": {
            "category_accuracy": md["category_accuracy"],
            "category_macro_f1": md["category_macro_f1"],
            "priority_accuracy": md["priority_accuracy"],
            "high_priority_recall": md["high_priority_recall"],
            "high_priority_missed": md["high_priority_missed"],
            "review_rate": md["review_rate"],
            "automated_rate": _prop(automated),
            "automated_category_accuracy": md["automated_category_accuracy"],
            "automated_priority_accuracy": md["automated_priority_accuracy"],
            "latency_p50_ms": md["latency_p50_ms"],
            "latency_p95_ms": md["latency_p95_ms"],
        },
        "cost": {
            "known_usd": _dec(known),
            "calls_with_unknown_cost": unknown,
            "total_usd": _dec(m.cost_total_usd),
            "per_completed_usd": _dec(per_completed),
            "estimate_per_1000_usd": _dec(estimate_1000),
        },
        "usage": {
            "providers": usage,
            "calls": m.calls_total,
            "retries": sum(p["retries"] for p in usage),
            "call_errors": m.calls_failed,
            "input_tokens": m.input_tokens_known,
            "output_tokens": m.output_tokens_known,
            "calls_without_usage": m.calls_without_usage,
        },
        "hybrid": _hybrid_stats(rows, raw_strategy) if info["kind"] == "hybrid" else None,
    }


# --------------------------------------------------------------------------- ayrıntı


def _empty_detail(summary: dict, reason: str) -> dict:
    return {
        "run": summary,
        "metrics_available": False,
        "unavailable_reason": reason,
        "conditions": None,
        "budget": None,
        "common": {"n": 0, "sample_ids": [], "excluded": []},
        "strategies": [],
        "reconciliation": None,
        "samples": [],
        "warnings": [],
        "notes": {"comparability": COMPARABILITY_NOTE, "tokens": TOKEN_NOTE},
    }


def _conditions(run: dict, summary: dict) -> dict:
    config = run.get("config") or {}
    retry = config.get("retry") or {}
    prices = []
    for p in run.get("prices", []):
        prices.append(
            {
                "provider": p.get("provider"),
                "model": p.get("model"),
                "input_usd_per_mtok": str(p.get("input_usd_per_mtok")),
                "output_usd_per_mtok": str(p.get("output_usd_per_mtok")),
                "source_url": p.get("source_url"),
                "checked_on": p.get("checked_on"),
            }
        )
    env = run.get("environment") or {}
    return {
        "dataset_version": summary["dataset"]["version"],
        "splits": summary["dataset"]["splits"],
        "shuffle_seed": config.get("shuffle_seed"),
        "final": bool(config.get("final", False)),
        "limit": (run.get("dataset") or {}).get("limit"),
        "concurrency": config.get("concurrency"),
        "retry_max_attempts": retry.get("max_attempts"),
        "strategies": summary["strategies"],
        "prices": prices,
        "python": env.get("python"),
    }


def _sample_row(
    sample: Sample,
    by_strategy: dict[str, dict],
    uncertain: dict,
    common: set[str],
    names: list[str],
) -> dict:
    cells = {}
    for name in names:
        row = by_strategy.get(name)
        if row is None:
            cells[name] = None
            continue
        calls = row.get("calls", [])
        known = Decimal(0)
        unknown = 0
        for call in calls:
            if call.get("cost_usd") is None:
                unknown += 1
            else:
                known += Decimal(str(call["cost_usd"]))
        failed = bool(row.get("failed"))
        cells[name] = {
            "failed": failed,
            "category": row.get("category"),
            "priority": row.get("priority"),
            "category_ok": None
            if failed
            else (row.get("category") or "unclear") == sample.gold.category,
            "priority_ok": None
            if failed
            else (row.get("priority") or "unclear") == sample.gold.priority,
            "review_required": None if failed else bool(row.get("review_required")),
            "latency_ms": row.get("latency_ms"),
            "cost_known_usd": _dec(known),
            "calls_with_unknown_cost": unknown,
        }
    return {
        "id": sample.id,
        "title": sample.title,
        "split": sample.split,
        "variant": sample.variant,
        "tags": list(sample.tags),
        "gold": {
            "category": sample.gold.category,
            "priority": sample.gold.priority,
            "missing_info": list(sample.gold.missing_info),
            "expected_review": sample.expected_review,
        },
        "disputed": uncertain.get(sample.id),
        "in_common": sample.id in common,
        "strategies": cells,
    }


def load_run_detail(root: Path, run_id: str, *, uncertainty_path: Path | None = None) -> dict:
    run_dir = resolve_run_dir(root, run_id)
    summary = summarize_run(run_dir)
    if summary["status"] in ("corrupt", "missing_files"):
        return _empty_detail(summary, summary["status_detail"] or "Deney kaydı okunamadı.")
    try:
        run = _read_json(run_dir / "run.json")
        rows = _read_rows(run_dir / "predictions.jsonl")
    except (ExperimentCorrupt, FileNotFoundError) as exc:
        summary["status"] = "corrupt"
        summary["status_detail"] = str(exc) if isinstance(exc, ExperimentCorrupt) else str(exc)
        return _empty_detail(summary, summary["status_detail"])

    version = summary["dataset"]["version"]
    try:
        samples = {s.id: s for s in load_samples(version)}
    except (DatasetError, OSError, ValueError, TypeError):
        return _empty_detail(
            summary, f"Veri seti ({version}) bulunamadı; etiketler olmadan başarı rakamı üretilmez."
        )
    unknown_ids = {r["sample_id"] for r in rows} - set(samples)
    if unknown_ids:
        return _empty_detail(summary, "Kayıttaki bazı örnekler veri setinde yok; rakam üretilmedi.")

    raw_strategies = {s.get("name"): s for s in run.get("strategies", [])}
    names = [s["name"] for s in summary["strategies"]]
    uncertain, uncertainty_error = load_uncertainties(version, uncertainty_path)

    by_sample: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_sample.setdefault(row["sample_id"], {})[row["strategy"]] = row
    # Karşılaştırma yalnızca TÜM stratejilerin tamamladığı örneklerde (rapor koduyla aynı kural).
    common = {sid for sid, per in by_sample.items() if all(n in per for n in names)}
    excluded = [
        {
            "sample_id": sid,
            "missing_strategies": [n for n in names if n not in per],
        }
        for sid, per in sorted(by_sample.items())
        if sid not in common
    ]
    common_rows = [r for r in rows if r["sample_id"] in common]
    predictions = [Prediction.from_dict(r) for r in common_rows]
    prices = [p for p in run.get("prices", []) if isinstance(p, dict)]

    strategy_results = []
    for info in summary["strategies"]:
        name = info["name"]
        strategy_rows = [r for r in common_rows if r["strategy"] == name]
        strategy_results.append(
            _strategy_result(
                samples, predictions, strategy_rows, info, raw_strategies.get(name, {}), prices
            )
        )

    budget = _budget_view(run)
    compared_known = sum((Decimal(r["cost"]["known_usd"]) for r in strategy_results), Decimal(0))
    reconciliation = None
    if budget is not None:
        run_known = Decimal(str(budget["known_spent_usd"]))
        reconciliation = {
            "compared_known_usd": _dec(compared_known),
            "run_known_spent_usd": _dec(run_known),
            # Karşılaştırma dışı kalan çağrıların (yarım/ayrılan örnekler, kesilen karar) harcaması
            # toplamdan GİZLENMEZ: fark açıkça gösterilir.
            "outside_comparison_usd": _dec(run_known - compared_known),
            "conservative_spent_usd": budget["conservative_spent_usd"],
        }

    warnings = _warnings(summary, run, strategy_results, common, uncertain, version, excluded)
    if uncertainty_error:
        warnings.append({"code": "uncertainty_unreadable", "text": uncertainty_error})
    return {
        "run": summary,
        "metrics_available": True,
        "unavailable_reason": None,
        "conditions": _conditions(run, summary),
        "budget": budget,
        "common": {"n": len(common), "sample_ids": sorted(common), "excluded": excluded},
        "strategies": strategy_results,
        "reconciliation": reconciliation,
        "samples": [
            _sample_row(samples[sid], by_sample[sid], uncertain, common, names)
            for sid in sorted(by_sample)
        ],
        "warnings": warnings,
        "notes": {"comparability": COMPARABILITY_NOTE, "tokens": TOKEN_NOTE},
    }


def _warnings(
    summary: dict,
    run: dict,
    results: list[dict],
    common: set[str],
    uncertain: dict,
    version: str,
    excluded: list[dict],
) -> list[dict]:
    out: list[dict] = []

    def add(code: str, text: str) -> None:
        out.append({"code": code, "text": text})

    if len(common) < SMALL_SAMPLE_WARNING:
        add(
            "small_sample",
            f"Küçük örneklem ({len(common)} örnek): bu deney bağlantıyı, biçimi ve çağrı kayıtlarını "
            "doğrular; doğruluk, güvenilirlik veya maliyet tasarrufu sonucu çıkarılamaz.",
        )
    if any(s["info"]["is_mock"] for s in results):
        add("mock", "Mock stratejiler içerir: bu sayılar gerçek model ölçümü değildir.")
    if summary["status"] == "partial":
        add("partial", summary["status_detail"] or "Çalıştırma yarım kaldı.")
    if summary["dataset"]["matches_current"] is False:
        add(
            "dataset_changed",
            "Veri seti bu deneyden sonra değişmiş (sha256 uyuşmuyor); etiketler çalıştırma anındaki "
            "veriyle aynı olmayabilir.",
        )
    routing = summary["hybrid_routing"]
    if routing and not routing["recorded"]:
        add(
            "hybrid_v1",
            "Bu deney hibrit yönlendirme v1 ile alındı (kayıtta sürüm alanı yok): tüm sorular tek eşik, "
            "güvenilmeyen her soru LLM'e geçerdi. Güncel kod (v2) ile alınmış gibi okunmamalıdır; "
            "v2'nin daha iyi olduğuna dair henüz gerçek ölçüm yoktur.",
        )
    if any(s["n_failed"] for s in results):
        add(
            "failed_decisions",
            "Bazı stratejilerde başarısız kararlar var; doğrulukları sayıdan düşülmez, ayrıca gösterilir.",
        )
    if any(s["cost"]["calls_with_unknown_cost"] for s in results):
        add(
            "unknown_cost",
            "Bazı çağrıların ücreti bilinmiyor; toplam ücret 'bilinmiyor' gösterilir, sıfır sayılmaz.",
        )
    disputed = sorted(sid for sid in uncertain if sid in common)
    if disputed:
        add(
            "disputed_labels",
            f"Tartışmalı etiketli örnek: {', '.join(disputed)} (bağımsız ikinci değerlendirme bekliyor). "
            "Etiketler ve bu deneyin sonuçları değiştirilmedi.",
        )
    if excluded:
        add(
            "excluded_samples",
            f"{len(excluded)} örneği tüm stratejiler tamamlamadığı için karşılaştırma dışı; bu örneklerin "
            "çağrı harcaması toplam ücretten gizlenmez (bkz. 'karşılaştırma dışı harcama').",
        )
    return out


# --------------------------------------------------------------------------- örnek ayrıntısı

_JUDGMENT_KEYS = (
    "question",
    "answer",
    "probabilities",
    "confidence",
    "confidence_kind",
    "n_options",
    "source",
    "adopted",
)
_CALL_KEYS = (
    "provider",
    "model",
    "attempt",
    "status",
    "duration_ms",
    "input_tokens",
    "output_tokens",
    "usage_estimated",
    "cost_usd",
    "questions",
    "is_mock",
)


def _safe_error(value: Any) -> str | None:
    if not value:
        return None
    return str(value)[:200]


def load_sample_detail(
    root: Path, run_id: str, sample_id: str, *, uncertainty_path: Path | None = None
) -> dict:
    if not SAMPLE_ID_RE.fullmatch(sample_id or ""):
        raise ExperimentNotFound("Örnek bulunamadı.")
    run_dir = resolve_run_dir(root, run_id)
    try:
        run = _read_json(run_dir / "run.json")
        rows = _read_rows(run_dir / "predictions.jsonl")
    except (ExperimentCorrupt, FileNotFoundError) as exc:
        raise ExperimentNotFound("Deney kayıtları okunamadı.") from exc
    version = (run.get("dataset") or {}).get("version")
    try:
        samples = {s.id: s for s in load_samples(version)}
    except (DatasetError, OSError, ValueError, TypeError) as exc:
        raise ExperimentNotFound("Veri seti bulunamadı.") from exc
    sample = samples.get(sample_id)
    mine = {r["strategy"]: r for r in rows if r["sample_id"] == sample_id}
    if sample is None or not mine:
        raise ExperimentNotFound("Örnek bu deneyde yok.")

    raw_strategies = {s.get("name"): s for s in run.get("strategies", [])}
    infos = [_strategy_info(s) for s in run.get("strategies", [])]
    uncertain, _ = load_uncertainties(version, uncertainty_path)
    prices = [p for p in run.get("prices", []) if isinstance(p, dict)]
    out_strategies = []
    for info in infos:
        row = mine.get(info["name"])
        if row is None:
            out_strategies.append({"name": info["name"], "info": info, "present": False})
            continue
        calls = row.get("calls", [])
        known = Decimal(0)
        unknown = 0
        for call in calls:
            if call.get("cost_usd") is None:
                unknown += 1
            else:
                known += Decimal(str(call["cost_usd"]))
        failed = bool(row.get("failed"))
        escalated: list[str] = []
        if info["kind"] == "hybrid":
            llm_provider = ((raw_strategies.get(info["name"]) or {}).get("llm") or {}).get(
                "provider"
            )
            for call in calls:
                if call.get("provider") == llm_provider:
                    for question in call.get("questions") or []:
                        if question not in escalated:
                            escalated.append(question)
        out_strategies.append(
            {
                "name": info["name"],
                "info": info,
                "present": True,
                "failed": failed,
                "error": _safe_error(row.get("error")),
                "category": row.get("category"),
                "priority": row.get("priority"),
                "missing_info": list(row.get("missing_info", [])),
                "review_required": None if failed else bool(row.get("review_required")),
                "review_reasons": list(row.get("review_reasons", [])),
                "latency_ms": row.get("latency_ms"),
                "is_mock": bool(row.get("is_mock", False)),
                "providers": list(row.get("providers", [])),
                "model_versions": list(row.get("model_versions", [])),
                "category_ok": None
                if failed
                else (row.get("category") or "unclear") == sample.gold.category,
                "priority_ok": None
                if failed
                else (row.get("priority") or "unclear") == sample.gold.priority,
                "judgments": [
                    {key: j.get(key) for key in _JUDGMENT_KEYS} for j in row.get("judgments", [])
                ],
                "calls": [{key: c.get(key) for key in _CALL_KEYS} for c in calls],
                "usage": _provider_usage(calls, prices),
                "cost_known_usd": _dec(known),
                "calls_with_unknown_cost": unknown,
                "escalated_questions": escalated,
            }
        )
    return {
        "run_id": run_id,
        "sample": {
            "id": sample.id,
            "title": sample.title,
            "description": sample.description,
            "location": sample.location,
            "split": sample.split,
            "variant": sample.variant,
            "tags": list(sample.tags),
            "source": sample.source,
            "label_status": sample.label_status,
            "gold": {
                "category": sample.gold.category,
                "priority": sample.gold.priority,
                "missing_info": list(sample.gold.missing_info),
                "expected_review": sample.expected_review,
            },
            "disputed": uncertain.get(sample.id),
        },
        "strategies": out_strategies,
    }
