"""Değerlendirme çalıştırıcısı: aynı örnekler, aynı sorular, aynı asgari bilgiyle tüm stratejiler.

Adil karşılaştırma ilkeleri:
- Stratejiler yalnızca `Sample.to_input()` alır (başlık, açıklama, konum); etiket gitmez.
- Sıra etkisi için strateji sırası her örnekte döner (rotasyon); tohumlu karıştırma isteğe bağlı.
- Tek istek gecikmesi ölçülür (eşzamanlılık 1); throughput ile karıştırılmaz.
- Test bölümü yalnızca `final=True` ile çalıştırılır (ayar yaparken test kümesine bakılmasın).
- Her çalıştırma bir yeniden üretilebilirlik kaydı (run.json) bırakır.
"""

import json
import platform
import random
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.decision.contract import DecisionUnavailable, StrategyName
from app.decision.mock import MockProvider
from app.decision.pricing import PRICES
from app.decision.retry import DEFAULT_RETRY
from app.decision.rule_based import RULES_VERSION, RuleBasedStrategy
from app.decision.strategies import HybridStrategy, ProviderStrategy
from app.evaluation.dataset import (
    SPLITS,
    Sample,
    dataset_sha256,
    load_manifest,
    load_samples,
    repo_root,
)
from app.evaluation.serialize import call_to_dict, decision_to_dict

# Canlı (gerçek sağlayıcı) stratejiler henüz kayıtlı değildir; yalnızca kurallı taban ve mock'lar.
STRATEGY_BUILDERS: dict[str, Callable[[], object]] = {
    "rule_based": RuleBasedStrategy,
    "mock_jev": lambda: ProviderStrategy(StrategyName.JEV_ONLY, MockProvider("jev")),
    "mock_llm": lambda: ProviderStrategy(StrategyName.LLM_ONLY, MockProvider("llm")),
    "mock_hybrid": lambda: HybridStrategy(MockProvider("jev"), MockProvider("llm")),
}


class TestSplitGuard(RuntimeError):
    """Test bölümü nihai olmayan bir çalıştırmada istendi."""

    __test__ = False  # pytest bunu test sınıfı sanmasın


def describe_strategy(name: str, strategy: object) -> dict:
    """Stratejinin hangi sağlayıcı/model/istem sürümüyle çalıştığı (kayıt için)."""
    info: dict = {"name": name, "is_mock": name.startswith("mock_")}
    if isinstance(strategy, RuleBasedStrategy):
        info.update(kind="rule_based", rules_version=RULES_VERSION)
    elif isinstance(strategy, ProviderStrategy):
        p = strategy.provider
        info.update(
            kind=strategy.name.value,
            provider=p.name,
            model=p.model,
            prompt_version=p.prompt_version,
        )
    elif isinstance(strategy, HybridStrategy):
        info.update(
            kind="hybrid",
            jev={
                "provider": strategy.jev.name,
                "model": strategy.jev.model,
                "prompt_version": strategy.jev.prompt_version,
            },
            llm={
                "provider": strategy.llm.name,
                "model": strategy.llm.model,
                "prompt_version": strategy.llm.prompt_version,
            },
            thresholds={q.value: v for q, v in strategy.thresholds.jev_min_confidence.items()},
            llm_min_self_reported=strategy.thresholds.llm_min_self_reported,
        )
    return info


def git_state(cwd: Path | None = None) -> dict:
    """Kaynak commit SHA'sı ve çalışma ağacının kirli olup olmadığı."""
    cwd = cwd or repo_root()

    def run(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=15, check=True
            )
            return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    sha = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {
        "source_commit": sha or "bilinmiyor",
        "git_dirty": None if status is None else bool(status),
    }


def run_evaluation(
    *,
    version: str = "v1",
    splits: tuple[str, ...] = ("dev",),
    strategy_names: tuple[str, ...] = tuple(STRATEGY_BUILDERS),
    out_root: Path | None = None,
    shuffle_seed: int | None = None,
    final: bool = False,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    git: Callable[[], dict] = git_state,
) -> Path:
    unknown_splits = set(splits) - set(SPLITS)
    if unknown_splits:
        raise ValueError(f"Geçersiz bölüm: {sorted(unknown_splits)}")
    if "test" in splits and not final:
        raise TestSplitGuard(
            "Test bölümü yalnızca nihai rapor için çalıştırılır (--final). Eşik ve istem ayarını "
            "doğrulama (val) bölümünde yap; test kümesine bakarak optimizasyon yapma."
        )
    bad = set(strategy_names) - set(STRATEGY_BUILDERS)
    if bad:
        raise ValueError(f"Bilinmeyen strateji: {sorted(bad)}")

    samples = [s for s in load_samples(version) if s.split in splits]
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(samples)
    strategies = {name: STRATEGY_BUILDERS[name]() for name in strategy_names}

    started = now()
    run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}-{version}-{'+'.join(splits)}"
    out_dir = (out_root or repo_root() / "evaluation" / "runs") / run_id
    out_dir.mkdir(parents=True, exist_ok=False)

    names = list(strategies)
    with (out_dir / "predictions.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for index, sample in enumerate(samples):
            # Rotasyon: her örnekte başlangıç stratejisi değişir (sıra etkisini azaltır).
            rotation = names[index % len(names) :] + names[: index % len(names)]
            for name in rotation:
                handle.write(
                    json.dumps(_predict(name, strategies[name], sample), ensure_ascii=False) + "\n"
                )

    manifest = load_manifest(version)
    record = {
        "run_id": run_id,
        "created_at": started.isoformat(),
        **git(),
        "dataset": {
            "version": version,
            "sha256": dataset_sha256(version),
            "manifest_sha256": manifest.get("samples_sha256"),
            "splits_used": list(splits),
            "n_samples": len(samples),
            "source": manifest.get("source"),
            "label_status": manifest.get("label_status"),
        },
        "strategies": [describe_strategy(n, s) for n, s in strategies.items()],
        "config": {
            "concurrency": 1,
            "cache": "yok",
            "retry": asdict(DEFAULT_RETRY),
            "shuffle_seed": shuffle_seed,
            "strategy_order": "her örnekte döndürülür (rotasyon)",
            "final": final,
        },
        "prices": [
            {
                "provider": e.provider,
                "model": e.model,
                "input_usd_per_mtok": str(e.input_usd_per_mtok),
                "output_usd_per_mtok": str(e.output_usd_per_mtok),
                "source_url": e.source_url,
                "checked_on": e.checked_on.isoformat(),
            }
            for e in PRICES.values()
        ],
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
    }
    (out_dir / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return out_dir


def _predict(name: str, strategy: object, sample: Sample) -> dict:
    base = {"sample_id": sample.id, "strategy": name, "split": sample.split}
    started = time.perf_counter()
    try:
        decision = strategy.decide(sample.to_input())  # type: ignore[attr-defined]
    except DecisionUnavailable as failure:
        return {
            **base,
            "failed": True,
            "error": str(failure),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "calls": [call_to_dict(c) for c in failure.calls],
            "is_mock": any(c.is_mock for c in failure.calls),
        }
    latency = round((time.perf_counter() - started) * 1000, 3)
    return {
        **base,
        "failed": False,
        "error": None,
        "latency_ms": latency,
        **decision_to_dict(decision),
    }
