"""Veri seti yükleme ve doğrulama. Etiketler stratejilere ASLA gitmez: `Sample.to_input()` yalnızca
başlık, açıklama ve konumu içeren bir DecisionInput döndürür."""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.decision.contract import UNCLEAR, DecisionInput
from app.domain.vocabulary import Category, Priority

SPLITS = ("dev", "val", "test")
CATEGORY_LABELS = (*(c.value for c in Category), UNCLEAR)
PRIORITY_LABELS = tuple(p.value for p in Priority)
# v1'de yalnızca bu eksik bilgi türlerinin etiketi vardır (bkz. LABELING_GUIDE.md).
MISSING_LABELS = ("location", "detail")


def repo_root() -> Path:
    # .../services/api/app/evaluation/dataset.py → depo kökü
    return Path(__file__).resolve().parents[4]


def dataset_dir(version: str) -> Path:
    return repo_root() / "evaluation" / "datasets" / version


@dataclass(frozen=True)
class Gold:
    category: str
    priority: str
    missing_info: tuple[str, ...]


@dataclass(frozen=True)
class Sample:
    id: str
    group: str
    split: str
    title: str
    description: str
    location: str
    gold: Gold
    expected_review: bool
    tags: tuple[str, ...]
    variant: str
    source: str
    label_status: str

    def to_input(self) -> DecisionInput:
        """Stratejilere giden TEK şey. Etiket, bölüm, grup veya etiket (tag) taşımaz."""
        return DecisionInput(title=self.title, description=self.description, location=self.location)


class DatasetError(ValueError):
    """Veri seti geçersiz."""


def _parse(row: dict) -> Sample:
    labels = row["labels"]
    return Sample(
        id=row["id"],
        group=row["group"],
        split=row["split"],
        title=row["title"],
        description=row["description"],
        location=row["location"],
        gold=Gold(labels["category"], labels["priority"], tuple(labels["missing_info"])),
        expected_review=bool(row["expected_review"]),
        tags=tuple(row.get("tags", [])),
        variant=row.get("variant", ""),
        source=row["source"],
        label_status=row["label_status"],
    )


def validate(samples: list[Sample]) -> None:
    """Yapısal doğrulama; ihlalde DatasetError."""
    ids = [s.id for s in samples]
    if len(ids) != len(set(ids)):
        raise DatasetError("Yinelenen örnek kimliği var.")
    group_splits: dict[str, set[str]] = defaultdict(set)
    for s in samples:
        if s.split not in SPLITS:
            raise DatasetError(f"{s.id}: geçersiz bölüm {s.split!r}")
        if s.gold.category not in CATEGORY_LABELS:
            raise DatasetError(f"{s.id}: geçersiz kategori {s.gold.category!r}")
        if s.gold.priority not in PRIORITY_LABELS:
            raise DatasetError(f"{s.id}: geçersiz öncelik {s.gold.priority!r}")
        if not set(s.gold.missing_info) <= set(MISSING_LABELS):
            raise DatasetError(f"{s.id}: değerlendirilmeyen eksik bilgi etiketi")
        if not (s.title.strip() and s.description.strip() and s.location.strip()):
            raise DatasetError(f"{s.id}: boş alan")
        group_splits[s.group].add(s.split)
    crossing = sorted(group for group, splits in group_splits.items() if len(splits) > 1)
    if crossing:
        raise DatasetError(f"Aynı olay birden çok bölümde (sızıntı): {', '.join(crossing)}")


def load_samples(version: str = "v1") -> list[Sample]:
    path = dataset_dir(version) / "samples.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise DatasetError(f"Veri seti bulunamadı: {path}") from exc
    samples = [_parse(json.loads(line)) for line in lines if line.strip()]
    validate(samples)
    return samples


def dataset_sha256(version: str = "v1") -> str:
    return hashlib.sha256((dataset_dir(version) / "samples.jsonl").read_bytes()).hexdigest()


def load_manifest(version: str = "v1") -> dict:
    return json.loads((dataset_dir(version) / "MANIFEST.json").read_text(encoding="utf-8"))
