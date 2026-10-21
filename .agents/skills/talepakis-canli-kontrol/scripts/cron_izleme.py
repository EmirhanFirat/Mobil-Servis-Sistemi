"""Hermes no-agent cron girişi: canli_kontrol'ü `--cron` kipinde çalıştırır.

Hermes cron betiğe argüman geçmediği için ayrı giriş dosyasıdır. İkisi birlikte Hermes'in
`scripts/` klasörüne kopyalanır (SKILL.md, "Zamanlanmış izleme").
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from canli_kontrol import main  # noqa: E402

sys.exit(main(["--cron"]))
