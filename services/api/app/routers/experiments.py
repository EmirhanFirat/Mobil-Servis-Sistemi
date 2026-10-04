"""Model karşılaştırma: kayıtlı deneyleri (evaluation/runs) yalnızca yöneticiye gösterir.

Yalnızca OKUR ve yalnızca GET: sayfayı açmak, yenilemek, süzmek veya dışa aktarmak HİÇBİR model
çağrısı başlatmaz, bütçe defterine dokunmaz, dosya yazmaz. İstemciden dosya yolu kabul edilmez;
yalnızca `run_id` ve `sample_id` (kesin desenli) alınır. Ayrıntı: app/experiments.py.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from app import experiments
from app.deps import SettingsDep, require_admin
from app.errors import not_found
from app.schemas_experiments import RunDetailOut, RunListOut, SampleDetailOut

router = APIRouter(
    prefix="/admin/experiments",
    tags=["model karşılaştırma"],
    dependencies=[Depends(require_admin)],
)


def get_experiments_root(settings: SettingsDep) -> Path:
    """Deney kök klasörü. Testler bunu geçici klasörle değiştirir."""
    return settings.experiments_dir or experiments.default_runs_dir()


def get_uncertainty_file() -> Path | None:
    """Tartışmalı etiket işaret dosyası (None = varsayılan yol). Testler değiştirir."""
    return None


RootDep = Annotated[Path, Depends(get_experiments_root)]
UncertaintyDep = Annotated[Path | None, Depends(get_uncertainty_file)]


@router.get("", response_model=RunListOut, summary="Kayıtlı deneyler")
def list_experiments(root: RootDep) -> dict:
    return experiments.list_runs(root)


@router.get("/{run_id}", response_model=RunDetailOut, summary="Bir deneyin karşılaştırması")
def get_experiment(run_id: str, root: RootDep, uncertainty: UncertaintyDep) -> dict:
    try:
        return experiments.load_run_detail(root, run_id, uncertainty_path=uncertainty)
    except experiments.ExperimentNotFound:
        raise not_found("Deney bulunamadı.") from None


@router.get(
    "/{run_id}/samples/{sample_id}",
    response_model=SampleDetailOut,
    summary="Bir örnek: metin, beklenen etiket ve stratejilerin tahminleri",
)
def get_experiment_sample(
    run_id: str, sample_id: str, root: RootDep, uncertainty: UncertaintyDep
) -> dict:
    try:
        return experiments.load_sample_detail(root, run_id, sample_id, uncertainty_path=uncertainty)
    except experiments.ExperimentNotFound:
        raise not_found("Örnek bulunamadı.") from None
