"""Değerlendirme çalıştırıcısı: aynı örnekler, aynı sorular, aynı asgari bilgiyle tüm stratejiler.

Adil karşılaştırma ilkeleri:
- Stratejiler yalnızca `Sample.to_input()` alır (başlık, açıklama, konum); etiket gitmez.
- Sıra etkisi için strateji sırası her örnekte döner (rotasyon); tohumlu karıştırma isteğe bağlı.
- Tek istek gecikmesi ölçülür (eşzamanlılık 1); throughput ile karıştırılmaz.
- Test bölümü yalnızca `final=True` ile çalıştırılır (ayar yaparken test kümesine bakılmasın).
- Her çalıştırma bir yeniden üretilebilirlik kaydı (run.json) bırakır.

Gerçek (ücretli) stratejiler `LIVE_STRATEGY_BUILDERS` içindedir ve varsayılan listede YOKTUR:
yalnızca açıkça istenirse, pozitif bir toplam harcama sınırıyla (`max_cost_usd`), ücretli çağrılar
açık ve anahtarlar tanımlıysa çalışır. Harcama sınırı **çağrı başına muhafazakâr rezervasyonla**
uygulanır (bkz. app/decision/budget.py): her sağlayıcı çağrısından ve her retry'dan önce o
çağrının ücretinin üst sınırı rezerve edilir; bütçe yetmiyorsa çağrı HİÇ gönderilmez. Maliyeti
bilinemeyen çağrı ücretsiz sayılmaz, rezerve edilen en kötü durum bedeliyle sayılır. Her örneğe
başlamadan önce o örneğin TÜM stratejilerdeki en kötü durum ücreti de karşılanabiliyor olmalıdır;
böylece tüm stratejiler aynı örnekleri tamamlar. Garanti edilemeyen noktalar budget.py başında
açıkça listelenir.
"""

import json
import platform
import random
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.config import Settings, get_settings
from app.decision.budget import (
    BudgetedProvider,
    BudgetGuard,
    worst_decision_cost,
)
from app.decision.budget_ledger import BudgetLedger
from app.decision.contract import BudgetExhausted, DecisionInput, DecisionUnavailable, StrategyName
from app.decision.factory import anthropic_provider_from_settings, jev_provider_from_settings
from app.decision.pricing import PRICES
from app.decision.registry import FREE_STRATEGY_BUILDERS
from app.decision.retry import DEFAULT_RETRY
from app.decision.rule_based import RULES_VERSION, RuleBasedStrategy
from app.decision.serialize import call_to_dict, decision_to_dict
from app.decision.strategies import HybridStrategy, ProviderStrategy
from app.evaluation.dataset import (
    SPLITS,
    Sample,
    dataset_sha256,
    load_manifest,
    load_samples,
    repo_root,
)

# Varsayılan stratejiler: kurallı taban ve mock'lar. Ağ isteği yapmazlar, ücretsizdirler.
# (Kayıt defteri karar worker'ıyla paylaşılır; testler bu kopyayı yamayabilir.)
STRATEGY_BUILDERS: dict[str, Callable[[], object]] = dict(FREE_STRATEGY_BUILDERS)

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


class TestSplitGuard(RuntimeError):
    """Test bölümü nihai olmayan bir çalıştırmada istendi."""

    __test__ = False  # pytest bunu test sınıfı sanmasın


_BUDGET_ID = re.compile(r"[A-Za-z0-9._-]{1,60}")


def ledger_path(budget_id: str | None, budget_dir: Path | None = None) -> Path:
    """Bütçe defterinin yolu: evaluation/budget/<kimlik>.json (Git'e girmez)."""
    if not budget_id or not _BUDGET_ID.fullmatch(budget_id):
        raise ValueError("Geçersiz bütçe kimliği.")
    return (budget_dir or repo_root() / "evaluation" / "budget") / f"{budget_id}.json"


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


def select_samples(
    version: str,
    splits: tuple[str, ...],
    *,
    shuffle_seed: int | None = None,
    limit: int | None = None,
) -> list[Sample]:
    """Çalıştırılacak/planlanacak örnekler: bölümlere göre süz, (tohumluysa) karıştır, ilk `limit`
    tanesini al. Aynı girdi her zaman aynı örnekleri verir."""
    if limit is not None and limit < 1:
        raise ValueError("Örnek sınırı (--limit) en az 1 olmalı.")
    samples = [s for s in load_samples(version) if s.split in splits]
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(samples)
    return samples if limit is None else samples[:limit]


# Hızlı durdurma: sistematik bir hata (yanlış anahtar, hatalı istek, süren kesinti) her örnekte
# yeniden denenip bütçeyi boşuna "en kötü bedel" olarak yakmasın. Yalnızca gerçek (bütçeli)
# çalıştırmalarda uygulanır.
FATAL_CALL_STATUSES = frozenset({"auth_error", "bad_request"})
MAX_CONSECUTIVE_FAILURES = 2


def _circuit_breaker(name: str, prediction: dict, failures: dict[str, int]) -> dict | None:
    """Durdurulmalı mı? Kalıcı istemci hatası (401/402/403, 400/413/422...) tek seferde durdurur;
    aynı stratejinin ardışık iki kararı tüm denemelerine rağmen başarısız olursa durdurur."""
    for call in prediction.get("calls", []):
        if call["status"] in FATAL_CALL_STATUSES:
            return {
                "reason": "provider_error",
                "provider": call["provider"],
                "strategy": name,
                "status": call["status"],
            }
    failures[name] = failures.get(name, 0) + 1 if prediction.get("failed") else 0
    if failures[name] >= MAX_CONSECUTIVE_FAILURES:
        return {"reason": "provider_unavailable", "strategy": name}
    return None


def _attach_budget(strategy: object, guard: BudgetGuard) -> None:
    """Stratejideki her gerçek sağlayıcıyı bütçe korumasıyla sarar (her çağrı rezervasyonlu)."""
    if isinstance(strategy, ProviderStrategy):
        strategy.provider = BudgetedProvider(strategy.provider, guard)
    elif isinstance(strategy, HybridStrategy):
        strategy.jev = BudgetedProvider(strategy.jev, guard)
        strategy.llm = BudgetedProvider(strategy.llm, guard)


def _budget_stop_reason(
    guard: BudgetGuard, live_strategies: list[object], data: DecisionInput
) -> str | None:
    """Bu örneğe başlanabilir mi? Başlanamazsa nedeni. Örneğin TÜM gerçek stratejilerdeki en kötü
    durum ücreti (her çağrı tüm deneme haklarını kullanır) karşılanabilmeli."""
    if guard.bound_violations:
        return "estimate_violated"  # üst sınır varsayımı ihlal edildi: güvenilemez, dur
    try:
        worst = sum((worst_decision_cost(s, data) for s in live_strategies), Decimal(0))
    except BudgetExhausted:
        return "unbounded"  # fiyat veya çıktı tavanı bilinmiyor: ücret sınırlanamaz
    return None if guard.can_afford(worst) else "budget"


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
    budget_id: str | None = None,
    budget_dir: Path | None = None,
    limit: int | None = None,
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
    if live and not budget_id:
        raise LiveRunGuard(
            "Gerçek (ücretli) strateji için bütçe defteri kimliği zorunlu (--budget-id). Toplam "
            "sınır, aynı kimlikli TÜM çalıştırmaların toplamıdır ve süreçler arası diskte tutulur."
        )
    if budget_id is not None and not _BUDGET_ID.fullmatch(budget_id):
        raise ValueError(
            "Bütçe kimliği yalnızca harf, rakam, '.', '_' ve '-' içerebilir (en çok 60)."
        )
    if max_cost_usd is not None and max_cost_usd <= 0:
        raise ValueError("Harcama sınırı pozitif olmalı.")

    samples = select_samples(version, splits, shuffle_seed=shuffle_seed, limit=limit)
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

    # Gerçek stratejilerin her sağlayıcı çağrısı bütçe rezervasyonundan geçer ve rezervasyonlar
    # KALICI deftere yazılır: süreç yeniden başlarsa önceki harcama ve çözülmemiş rezervasyonlar
    # kalan bütçeden düşülür; yeni bir sınır açılmaz.
    ledger: BudgetLedger | None = None
    guard: BudgetGuard | None = None
    try:
        if live:
            ledger = BudgetLedger.open(
                ledger_path(budget_id, budget_dir), budget_id=budget_id, cap=max_cost_usd
            )
            guard = BudgetGuard(ledger.cap, ledger=ledger, run_id=run_id)
        out_dir.mkdir(parents=True, exist_ok=False)
    except BaseException:
        if ledger is not None:
            ledger.release()
        for strategy in strategies.values():
            _close(strategy)
        raise
    live_strategies = [strategies[n] for n in strategy_names if n in LIVE_STRATEGY_BUILDERS]
    if guard is not None:
        for strategy in live_strategies:
            _attach_budget(strategy, guard)

    names = list(strategies)
    completed = 0
    stopped: dict | None = None
    aborted: dict | None = None
    failure: Exception | None = None
    failures: dict[str, int] = {}  # strateji başına ardışık başarısız karar sayısı
    try:
        with (out_dir / "predictions.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for index, sample in enumerate(samples):
                if guard is not None:
                    reason = _budget_stop_reason(guard, live_strategies, sample.to_input())
                    if reason:
                        stopped = {"reason": reason}
                        break
                # Rotasyon: her örnekte başlangıç stratejisi değişir (sıra etkisini azaltır).
                rotation = names[index % len(names) :] + names[: index % len(names)]
                written = 0
                for name in rotation:
                    prediction = _predict(name, strategies[name], sample)
                    if prediction.get("aborted"):  # bütçe bu kararın ortasında bitti
                        halt = {"reason": "budget"}
                    else:
                        halt = _circuit_breaker(name, prediction, failures) if guard else None
                    if prediction.get("aborted") or (halt and halt["reason"] == "provider_error"):
                        # Yarım karar veya kalıcı istemci hatası tahmin sayılmaz (örnek rapor
                        # dışı kalır) ama harcanan çağrılar kayıpta kalmaz: run.json'da saklanır.
                        aborted = {
                            "sample_id": sample.id,
                            "strategy": name,
                            "reason": halt["reason"],
                            "calls": prediction["calls"],
                        }
                        stopped = halt
                        break
                    handle.write(json.dumps(prediction, ensure_ascii=False) + "\n")
                    written += 1
                    if halt:  # ardışık başarısızlık: bu karar kayıtlı, ama durulur
                        stopped = halt
                        break
                handle.flush()  # kesintide o ana dek olan tahminler diskte kalır
                if written == len(rotation):
                    completed += 1  # tüm stratejiler bu örneği bitirdi
                if stopped is not None:
                    break
    except KeyboardInterrupt:
        stopped = {"reason": "interrupted"}
    except Exception as exc:  # kaydı yine de yaz; sonra yeniden fırlat
        stopped = {"reason": "error", "error": type(exc).__name__}
        failure = exc
    finally:
        for strategy in strategies.values():
            _close(strategy)
        if ledger is not None:
            ledger.release()
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
            "limit": limit,
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
            "method": "çağrı başına en kötü durum rezervasyonu + kalıcı defter" if live else None,
            **(
                guard.summary()
                if guard is not None
                else {"max_cost_usd": None if max_cost_usd is None else str(max_cost_usd)}
            ),
        },
        "stopped_early": stopped,
        "aborted_prediction": aborted,
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
    except BudgetExhausted as stop:
        return {
            **base,
            "aborted": True,
            "error": str(stop),
            "calls": [call_to_dict(c) for c in stop.calls],
        }
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
