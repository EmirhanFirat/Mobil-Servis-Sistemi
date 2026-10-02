"""Komut satırı: `python -m app.evaluation plan|run|report`.

Örnek (services/api içinde):
  .\\.venv\\Scripts\\python.exe -m app.evaluation run --splits dev,val
  .\\.venv\\Scripts\\python.exe -m app.evaluation plan --splits dev,val
  .\\.venv\\Scripts\\python.exe -m app.evaluation run --splits val --strategies llm_only `
      --max-cost-usd 0.50
  .\\.venv\\Scripts\\python.exe -m app.evaluation report --run ..\\..\\evaluation\\runs\\<kimlik>

Gerçek (ücretli) stratejiler (`jev_only`, `llm_only`, `hybrid`) varsayılan listede yoktur; yalnızca
`--strategies` ile açıkça istenir ve pozitif `--max-cost-usd` ister. Ayrıca ücretli çağrılar açık
(`TALEPAKIS_PAID_MODEL_CALLS_ENABLED=true`) ve anahtarlar ortam değişkeninde tanımlı olmalıdır.
"""

import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.config import get_settings
from app.decision.budget_ledger import BudgetLedger, LedgerError
from app.decision.contract import ALL_QUESTIONS, Question
from app.decision.factory import MissingApiKey, PaidCallsDisabled
from app.decision.strategies import HybridThresholds
from app.evaluation.detail import build_detail
from app.evaluation.plan import PLANNABLE, estimate_plan, format_plan
from app.evaluation.preflight import build_preflight
from app.evaluation.report import write_report
from app.evaluation.runner import (
    LIVE_STRATEGY_BUILDERS,
    STRATEGY_BUILDERS,
    LiveRunGuard,
    TestSplitGuard,
    ledger_path,
    run_evaluation,
    select_samples,
)


def _usd(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"geçerli bir tutar değil: {text!r}") from None
    if not value.is_finite() or value <= 0:
        raise argparse.ArgumentTypeError("tutar pozitif olmalı")
    return value


def _csv(text: str) -> tuple[str, ...]:
    return tuple(s for s in text.split(",") if s)


def _threshold(text: str) -> tuple[Question, float]:
    """`soru=değer` (ör. missing_location=0.7): tek bir sorunun Jev güven eşiği."""
    name, _, value = text.partition("=")
    try:
        question = Question(name.strip())
    except ValueError:
        valid = ", ".join(q.value for q in ALL_QUESTIONS)
        raise argparse.ArgumentTypeError(f"bilinmeyen soru {name!r}; geçerli: {valid}") from None
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"eşik sayı olmalı: {text!r}") from None
    if not 0.0 <= number <= 1.0:  # nan da bu aralığın dışında kalır
        raise argparse.ArgumentTypeError("eşik 0 ile 1 arasında olmalı")
    return question, number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.evaluation", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Stratejileri veri setinde çalıştır ve kaydet")
    run.add_argument("--dataset", default="v1")
    run.add_argument("--splits", default="dev", help="Virgülle: dev,val (test için --final)")
    run.add_argument("--strategies", default=",".join(STRATEGY_BUILDERS))
    run.add_argument(
        "--out", type=Path, default=None, help="Çıktı klasörü (varsayılan evaluation/runs)"
    )
    run.add_argument("--shuffle-seed", type=int, default=None)
    run.add_argument(
        "--limit", type=int, default=None, help="Yalnızca ilk N örnek (küçük canlı deneme için)"
    )
    run.add_argument(
        "--final", action="store_true", help="Test bölümüne izin ver (yalnızca nihai rapor)"
    )
    run.add_argument(
        "--max-cost-usd",
        type=_usd,
        default=None,
        help="Toplam harcama sınırı (USD); gerçek stratejiler için ZORUNLU",
    )
    run.add_argument(
        "--budget-id",
        default=None,
        help="Bütçe defteri kimliği; gerçek stratejiler için ZORUNLU. Sınır, aynı kimlikli TÜM "
        "çalıştırmaların toplamıdır ve süreçler arası diskte tutulur",
    )
    run.add_argument("--budget-dir", type=Path, default=None, help=argparse.SUPPRESS)
    run.add_argument(
        "--hybrid-threshold",
        type=_threshold,
        action="append",
        default=[],
        metavar="SORU=DEĞER",
        help="Hibritte tek bir sorunun Jev güven eşiği (tekrarlanabilir). Verilmeyen sorular "
        "varsayılan (provizyonel) eşikte kalır. Eşikler doğrulama (val) bölümünde seçilir; "
        "run.json'a yazılır",
    )

    plan = sub.add_parser(
        "plan", help="Gerçek stratejiler için yaklaşık ücreti göster (ağ isteği yapmaz)"
    )
    plan.add_argument("--dataset", default="v1")
    plan.add_argument("--splits", default="dev,val")
    plan.add_argument("--strategies", default=",".join(PLANNABLE))
    plan.add_argument("--shuffle-seed", type=int, default=None)
    plan.add_argument("--limit", type=int, default=None, help="Yalnızca ilk N örnek")

    pre = sub.add_parser(
        "preflight",
        help="Canlı çalıştırma ön kontrolü: anahtar/bayrak durumu (değer yazdırmaz), fiyatlar, "
        "bütçe defteri, seçilen örnekler, plan ve komut",
    )
    pre.add_argument("--dataset", default="v1")
    pre.add_argument("--splits", default="dev")
    pre.add_argument("--strategies", default=",".join(PLANNABLE))
    pre.add_argument("--shuffle-seed", type=int, default=None)
    pre.add_argument("--limit", type=int, default=None)
    pre.add_argument("--max-cost-usd", type=_usd, required=True)
    pre.add_argument("--budget-id", required=True)
    pre.add_argument("--budget-dir", type=Path, default=None, help=argparse.SUPPRESS)

    budget = sub.add_parser("budget", help="Bütçe defterinin durumunu göster (salt okunur)")
    budget.add_argument("--budget-id", required=True)
    budget.add_argument("--budget-dir", type=Path, default=None, help=argparse.SUPPRESS)

    detail = sub.add_parser(
        "detail", help="Kayıtlı çalıştırmadan örnek bazında ayrıntı yazdır (model çağrısı yok)"
    )
    detail.add_argument("--run", type=Path, required=True)

    report = sub.add_parser(
        "report", help="Kayıtlı bir çalıştırmadan rapor üret (model çağrısı yok)"
    )
    report.add_argument("--run", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            samples = select_samples(
                args.dataset,
                _csv(args.splits),
                shuffle_seed=args.shuffle_seed,
                limit=args.limit,
            )
            print(format_plan(estimate_plan(samples, _csv(args.strategies))))
        elif args.command == "preflight":
            text, ready = build_preflight(
                settings=get_settings(),
                version=args.dataset,
                splits=_csv(args.splits),
                strategies=_csv(args.strategies),
                max_cost_usd=args.max_cost_usd,
                budget_id=args.budget_id,
                budget_dir=args.budget_dir,
                shuffle_seed=args.shuffle_seed,
                limit=args.limit,
            )
            print(text)
            return 0 if ready else 3
        elif args.command == "budget":
            ledger = BudgetLedger.read(ledger_path(args.budget_id, args.budget_dir))
            for key, value in ledger.status().items():
                print(f"{key}: {value}")
        elif args.command == "detail":
            print(build_detail(args.run))
        elif args.command == "run":
            names = _csv(args.strategies)
            splits = _csv(args.splits)
            live = tuple(n for n in names if n in LIVE_STRATEGY_BUILDERS)
            if live:
                samples = select_samples(
                    args.dataset, splits, shuffle_seed=args.shuffle_seed, limit=args.limit
                )
                print(format_plan(estimate_plan(samples, live)))
                print(f"\nToplam harcama sınırı: {args.max_cost_usd or 'YOK'} USD\n")
            out = run_evaluation(
                version=args.dataset,
                splits=splits,
                strategy_names=names,
                out_root=args.out,
                shuffle_seed=args.shuffle_seed,
                final=args.final,
                max_cost_usd=args.max_cost_usd,
                budget_id=args.budget_id,
                budget_dir=args.budget_dir,
                limit=args.limit,
                hybrid_thresholds=(
                    HybridThresholds().with_confidence(dict(args.hybrid_threshold))
                    if args.hybrid_threshold
                    else None
                ),
            )
            print(f"Çalıştırma kaydedildi: {out}")
            print(f'Rapor için: python -m app.evaluation report --run "{out}"')
        else:
            print(f"Rapor yazıldı: {write_report(args.run)}")
    except (
        TestSplitGuard,
        LiveRunGuard,
        PaidCallsDisabled,
        MissingApiKey,
        LedgerError,
        ValueError,
    ) as error:
        print(f"Hata: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
