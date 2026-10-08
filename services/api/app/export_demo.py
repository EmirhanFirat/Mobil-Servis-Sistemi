"""Kayıtlı deney sonuçlarını, API uyanmadan açılabilen STATİK JSON'a aktarır (portföy demosu).

Kaynak `evaluation/runs` yalnızca OKUNUR; model çağrısı yapılmaz, hiçbir şey silinmez veya
değiştirilmez. Çıktı, yönetici panelindeki "Model karşılaştırma" sayfasının API'den aldığı
yanıtlarla AYNI şemadadır (Pydantic yanıt modellerinden üretilir): bu yüzden beyaz liste
uygulanır ve bütçe defterinin yerel yolu gibi alanlar çıkmaz.

Yalnızca GERÇEK sağlayıcı çağrılarıyla alınmış (`live`) ve rakam üretilebilen (tamamlanmış veya
kısmi) deneyler aktarılır. Mock/ücretsiz çalıştırmalar "gerçek ölçüm" gibi yayımlanmasın diye
varsayılan olarak DIŞARIDA bırakılır. Çıktı belirleyicidir (zaman damgası yok): aynı kayıtlardan
aynı dosyalar üretilir, Git farkı yalnızca gerçek değişikliği gösterir.
"""

import json
from pathlib import Path

from app import experiments
from app.evaluation.dataset import repo_root
from app.routers.meta import vocabulary
from app.schemas_experiments import RunDetailOut, RunListOut, SampleDetailOut

EXPORTED_STATUSES = ("complete", "partial")
FILE_EXPERIMENTS = "experiments.json"
FILE_VOCABULARY = "vocabulary.json"


def default_output_dir() -> Path:
    return repo_root() / "apps" / "admin" / "public" / "demo-data"


def build_payload(root: Path, *, include_mock: bool = False) -> dict:
    listing = experiments.list_runs(root)
    runs = [
        run
        for run in listing["runs"]
        if run["status"] in EXPORTED_STATUSES and (run["live"] or include_mock)
    ]
    details: dict[str, dict] = {}
    samples: dict[str, dict[str, dict]] = {}
    for run in runs:
        run_id = run["id"]
        detail = RunDetailOut.model_validate(experiments.load_run_detail(root, run_id))
        details[run_id] = detail.model_dump(mode="json")
        samples[run_id] = {}
        for row in detail.samples:
            sample = experiments.load_sample_detail(root, run_id, row.id)
            samples[run_id][row.id] = SampleDetailOut.model_validate(sample).model_dump(mode="json")
    shown = RunListOut.model_validate({"runs_dir_found": listing["runs_dir_found"], "runs": runs})
    return {"list": shown.model_dump(mode="json"), "details": details, "samples": samples}


def _write(path: Path, data: object) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def export_demo_data(
    runs_dir: Path | None = None, out_dir: Path | None = None, *, include_mock: bool = False
) -> list[Path]:
    """`experiments.json` ve `vocabulary.json` dosyalarını yazar; yazılan yolları döndürür."""
    root = runs_dir or experiments.default_runs_dir()
    out = out_dir or default_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    payload = build_payload(root, include_mock=include_mock)
    _write(out / FILE_EXPERIMENTS, payload)
    _write(out / FILE_VOCABULARY, vocabulary().model_dump(mode="json"))
    return [out / FILE_EXPERIMENTS, out / FILE_VOCABULARY]
