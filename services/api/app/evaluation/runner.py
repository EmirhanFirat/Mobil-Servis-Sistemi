"""Değerlendirme çalıştırıcısı: aynı örnekler, aynı sorular, aynı asgari bilgiyle tüm stratejiler.

Adil karşılaştırma ilkeleri:
- Stratejiler yalnızca `Sample.to_input()` alır (başlık, açıklama, konum); etiket gitmez.
- Sıra etkisi için strateji sırası her örnekte döner (rotasyon); tohumlu karıştırma isteğe bağlı.
- Tek istek gecikmesi ölçülür (eşzamanlılık 1); throughput ile karıştırılmaz.
- Test bölümü yalnızca `final=True` ile çalıştırılır (ayar yaparken test kümesine bakılmasın).
- Her çalıştırma bir yeniden üretilebilirlik kaydı (run.json) bırakır.

Gerçek (ücretli) stratejiler `LIVE_STRATEGY_BUILDERS` içindedir ve varsayılan listede YOKTUR:
yalnızca açıkça istenirse, pozitif bir toplam harcama sınırıyla (`max_cost_usd`), ücretli çağrılar
açık ve anahtarlar tanımlıysa çalışır. Sınır örnek sınırında denetlenir: bir sonraki örneğin
(şimdiye dek görülen en pahalı örnek kadar) ücreti sınırı aşacaksa durulur; böylece tüm stratejiler
aynı örnekleri tamamlamış olur ve aşım yalnızca beklenenden pahalı bir örnekle (ör. çok retry)
olabilir. Maliyeti bilinemeyen bir çağrı (kullanım bildirilmedi) harcama sınırını boşa çıkaracağı
için çalıştırmayı durdurur.
"""

import json
import platform
import random
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.config import Settings, get_settings
from app.decision.contract import DecisionUnavailable, StrategyName
from app.decision.factory import anthropic_provider_from_settings, jev_provider_from_settings
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

# Varsayılan stratejiler: kurallı taban ve mock'lar. Ağ isteği yapmazlar, ücretsizdirler.
STRATEGY_BUILDERS: dict[str, Callable[[], object]] = {
    "rule_based": RuleBasedStrategy,
    "mock_jev": lambda: ProviderStrategy(StrategyName.JEV_ONLY, MockProvider("jev")),
    "mock_llm": lambda: ProviderStrategy(StrategyName.LLM_ONLY, MockProvider("llm")),
    "mock_hybrid": lambda: HybridStrategy(MockProvider("jev"), MockProvider("llm")),
}

# Gerçek, ÜCRETLİ stratejiler. Ayarlardan kurulur; ücretli çağrılar kapalıysa veya anahtar yoksa
# kurulamaz (factory.py). Hibrit eşikleri başlangıç değerleridir; doğrulama (val) kümesinde
# ayarlanır ve run.json'a yazılır.
LIVE_STRATEGY_BUILDERS: dict[str, Callable[[Settings], object]] = {
    "jev_only": lambda s: ProviderStrategy(StrategyName.JEV_ONLY, jev_provider_from_settings(s)),
    "llm_only": lambda s: ProviderStrategy(
        StrategyName.LLM_ONLY, anthropic_provider_from_settings(s)
    ),
    "hybrid": lambda s: HybridStrategy(
        jev_provider_from_settings(s), anthropic_provider_from_settings(s)
    ),
}

# Harcama takibinde, maliyeti hesaplanamazsa "bilinmeyen maliyet" sayılan çağrı durumları: model
# yanıtı alındı (başarılı veya şemaya uymayan 200 yanıtı), dolayısıyla ücretlendirilmiş olabilir.
# Ağ/HTTP hata denemelerinde (zaman aşımı, 5xx, 429) sunucu tarafı ücret bilinemez ve takibe
# girmez; bunlar raporda yine "bilinmiyor" olarak görünür.
_BILLABLE_STATUSES = frozenset({"ok", "schema_error"})


class TestSplitGuard(RuntimeError):
    """Test bölümü nihai olmayan bir çalıştırmada istendi."""

    __test__ = False  # pytest bunu test sınıfı sanmasın


class LiveRunGuard(RuntimeError):
    """Gerçek (ücretli) strateji, zorunlu harcama sınırı olmadan istendi."""


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
        if hasattr(p, "temperature"):
            info["temperature"] = p.temperature
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
        if hasattr(strategy.llm, "temperature"):
            info["llm"]["temperature"] = strategy.llm.temperature
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


def _spend(prediction: dict) -> tuple[Decimal, int]:
    """(bilinen ücret, maliyeti hesaplanamayan ücretlendirilebilir çağrı sayısı)."""
    known = Decimal(0)
    unknown = 0
    for call in prediction.get("calls", []):
        if call["cost_usd"] is not None:
            known += Decimal(call["cost_usd"])
        elif call["status"] in _BILLABLE_STATUSES:
            unknown += 1
    return known, unknown


def _close(strategy: object) -> None:
    """Sağlayıcıların HTTP istemcilerini kapatır (mock ve kurallı tabanda close yoktur)."""
    providers = []
    if isinstance(strategy, ProviderStrategy):
        providers = [strategy.provider]
    elif isinstance(strategy, HybridStrategy):
        providers = [strategy.jev, strategy.llm]
    for provider in providers:
        close = getattr(provider, "close", None)
        if close is not None:
            close()


def run_evaluation(
    *,
    version: str = "v1",
    splits: tuple[str, ...] = ("dev",),
    strategy_names: tuple[str, ...] = tuple(STRATEGY_BUILDERS),
    out_root: Path | None = None,
    shuffle_seed: int | None = None,
    final: bool = False,
    max_cost_usd: Decimal | None = None,
    settings: Settings | None = None,
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
    bad = set(strategy_names) - set(STRATEGY_BUILDERS) - set(LIVE_STRATEGY_BUILDERS)
    if bad:
        raise ValueError(f"Bilinmeyen strateji: {sorted(bad)}")
    live = any(name in LIVE_STRATEGY_BUILDERS for name in strategy_names)
    if live and (max_cost_usd is None or max_cost_usd <= 0):
        raise LiveRunGuard(
            "Gerçek (ücretli) strateji için pozitif bir toplam harcama sınırı zorunlu "
            "(--max-cost-usd). Önce `plan` komutuyla yaklaşık ücreti gör."
        )
    if max_cost_usd is not None and max_cost_usd <= 0:
        raise ValueError("Harcama sınırı pozitif olmalı.")

    samples = [s for s in load_samples(version) if s.split in splits]
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(samples)
    # Stratejiler çıktı klasörü açılmadan KURULUR: ücretli çağrılar kapalıysa veya anahtar yoksa
    # hiçbir şey yazılmadan açık hata alınır.
    live_settings = (settings or get_settings()) if live else None
    strategies: dict[str, object] = {}
    for name in strategy_names:
        if name in LIVE_STRATEGY_BUILDERS:
            strategies[name] = LIVE_STRATEGY_BUILDERS[name](live_settings)
        else:
            strategies[name] = STRATEGY_BUILDERS[name]()

    started = now()
    run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}-{version}-{'+'.join(splits)}"
    out_dir = (out_root or repo_root() / "evaluation" / "runs") / run_id
    try:
        out_dir.mkdir(parents=True, exist_ok=False)
    except BaseException:
        for strategy in strategies.values():
            _close(strategy)
        raise

    names = list(strategies)
    spent = Decimal(0)
    unknown_calls = 0
    max_sample_cost = Decimal(0)
    completed = 0
    stopped: dict | None = None
    failure: Exception | None = None
    try:
        with (out_dir / "predictions.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for index, sample in enumerate(samples):
                if live:
                    reason = None
                    if unknown_calls:
                        reason = "unknown_cost"
                    elif max_cost_usd is not None and spent + max_sample_cost > max_cost_usd:
                        reason = "budget"
                    if reason:
                        stopped = {"reason": reason}
                        break
                # Rotasyon: her örnekte başlangıç stratejisi değişir (sıra etkisini azaltır).
                rotation = names[index % len(names) :] + names[: index % len(names)]
                sample_cost = Decimal(0)
                for name in rotation:
                    prediction = _predict(name, strategies[name], sample)
                    handle.write(json.dumps(prediction, ensure_ascii=False) + "\n")
                    known, unknown = _spend(prediction)
                    spent += known
                    sample_cost += known
                    unknown_calls += unknown
                handle.flush()  # kesintide o ana dek olan tahminler diskte kalır
                max_sample_cost = max(max_sample_cost, sample_cost)
                completed += 1
    except KeyboardInterrupt:
        stopped = {"reason": "interrupted"}
    except Exception as exc:  # kaydı yine de yaz; sonra yeniden fırlat
        stopped = {"reason": "error", "error": type(exc).__name__}
        failure = exc
    finally:
        for strategy in strategies.values():
            _close(strategy)
    if stopped:
        stopped.update(samples_completed=completed, samples_planned=len(samples))

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
            "n_samples_completed": completed,
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
        "budget": {
            "live": live,
            "max_cost_usd": None if max_cost_usd is None else str(max_cost_usd),
            "spent_known_usd": str(spent),
            "billable_calls_with_unknown_cost": unknown_calls,
        },
        "stopped_early": stopped,
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
    if failure is not None:
        raise failure
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
