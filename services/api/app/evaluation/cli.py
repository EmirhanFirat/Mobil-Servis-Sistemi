"""Komut satırı: `python -m app.evaluation run|report`.

Örnek (services/api içinde):
  .\\.venv\\Scripts\\python.exe -m app.evaluation run --splits dev,val
  .\\.venv\\Scripts\\python.exe -m app.evaluation report --run ..\\..\\evaluation\\runs\\<kimlik>
"""

import argparse
import sys
from pathlib import Path

from app.evaluation.report import write_report
from app.evaluation.runner import STRATEGY_BUILDERS, TestSplitGuard, run_evaluation


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
        "--final", action="store_true", help="Test bölümüne izin ver (yalnızca nihai rapor)"
    )

    report = sub.add_parser(
        "report", help="Kayıtlı bir çalıştırmadan rapor üret (model çağrısı yok)"
    )
    report.add_argument("--run", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            out = run_evaluation(
                version=args.dataset,
                splits=tuple(s for s in args.splits.split(",") if s),
                strategy_names=tuple(s for s in args.strategies.split(",") if s),
                out_root=args.out,
                shuffle_seed=args.shuffle_seed,
                final=args.final,
            )
            print(f"Çalıştırma kaydedildi: {out}")
            print(f'Rapor için: python -m app.evaluation report --run "{out}"')
        else:
            print(f"Rapor yazıldı: {write_report(args.run)}")
    except (TestSplitGuard, ValueError) as error:
        print(f"Hata: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
