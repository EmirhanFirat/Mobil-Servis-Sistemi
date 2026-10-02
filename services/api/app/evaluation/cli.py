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

from app.decision.factory import MissingApiKey, PaidCallsDisabled
from app.evaluation.plan import PLANNABLE, estimate_plan, format_plan
from app.evaluation.report import write_report
from app.evaluation.runner import (
    LIVE_STRATEGY_BUILDERS,
    STRATEGY_BUILDERS,
    LiveRunGuard,
    TestSplitGuard,
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

    plan = sub.add_parser(
        "plan", help="Gerçek stratejiler için yaklaşık ücreti göster (ağ isteği yapmaz)"
    )
    plan.add_argument("--dataset", default="v1")
    plan.add_argument("--splits", default="dev,val")
    plan.add_argument("--strategies", default=",".join(PLANNABLE))
    plan.add_argument("--shuffle-seed", type=int, default=None)
    plan.add_argument("--limit", type=int, default=None, help="Yalnızca ilk N örnek")

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
                limit=args.limit,
            )
            print(f"Çalıştırma kaydedildi: {out}")
            print(f'Rapor için: python -m app.evaluation report --run "{out}"')
        else:
            print(f"Rapor yazıldı: {write_report(args.run)}")
    except (TestSplitGuard, LiveRunGuard, PaidCallsDisabled, MissingApiKey, ValueError) as error:
        print(f"Hata: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
