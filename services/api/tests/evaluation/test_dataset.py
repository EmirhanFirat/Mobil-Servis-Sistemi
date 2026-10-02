import dataclasses
from collections import Counter

import pytest

from app.decision.contract import DecisionInput
from app.evaluation.dataset import (
    CATEGORY_LABELS,
    DatasetError,
    Gold,
    Sample,
    dataset_sha256,
    load_manifest,
    load_samples,
    validate,
)


def make(**overrides) -> Sample:
    base = dict(
        id="s1",
        group="G1",
        split="dev",
        title="Lavabo",
        description="Lavabo akıtıyor",
        location="B Blok",
        gold=Gold("plumbing", "normal", ()),
        expected_review=False,
        tags=(),
        variant="resmi",
        source="synthetic",
        label_status="single_annotator_unreviewed",
    )
    return Sample(**{**base, **overrides})


class TestShippedDataset:
    def test_v1_yuklenir_ve_gecerlidir(self):
        samples = load_samples("v1")

        assert len(samples) == 54
        assert len({s.id for s in samples}) == 54

    def test_bolum_dagilimi_manifestle_tutarli(self):
        samples = load_samples("v1")
        manifest = load_manifest("v1")

        counts = Counter(s.split for s in samples)
        assert dict(counts) == {k: v["samples"] for k, v in manifest["splits"].items()}
        assert manifest["total_samples"] == 54
        assert manifest["samples_sha256"] == dataset_sha256(
            "v1"
        )  # dosya manifestten sonra değişmemiş

    def test_her_olay_grubu_tek_bolumde_uc_yazimla(self):
        samples = load_samples("v1")
        by_group: dict[str, list[Sample]] = {}
        for s in samples:
            by_group.setdefault(s.group, []).append(s)

        assert len(by_group) == 18
        for group, rows in by_group.items():
            assert {r.split for r in rows} == {rows[0].split}, group  # sızıntı yok
            assert sorted(r.variant for r in rows) == ["kisa", "resmi", "yazim_hatali"], group

    def test_her_bolum_zor_durumlari_icerir(self):
        samples = load_samples("v1")

        for split in ("val", "test"):
            tags = {tag for s in samples if s.split == split for tag in s.tags}
            assert tags, split
        test_tags = {tag for s in samples if s.split == "test" for tag in s.tags}
        val_tags = {tag for s in samples if s.split == "val" for tag in s.tags}
        assert {"hazard", "injection", "multi_issue"} <= test_tags | val_tags
        assert {"vague", "missing_location"} <= val_tags

    def test_tum_kategori_ve_oncelik_siniflari_temsil_edilir(self):
        samples = load_samples("v1")

        assert set(CATEGORY_LABELS) <= {s.gold.category for s in samples}
        assert {"low", "normal", "high"} == {s.gold.priority for s in samples}

    def test_etiketli_olmayan_ornekte_beklenen_inceleme_tutarli(self):
        for s in load_samples("v1"):
            if set(s.tags) & {"hazard", "injection", "multi_issue", "vague", "missing_location"}:
                assert s.expected_review, s.id

    def test_stratejilere_giden_girdi_yalniz_uc_alan_etiket_yok(self):
        sample = load_samples("v1")[0]

        data = sample.to_input()

        assert isinstance(data, DecisionInput)
        assert {f.name for f in dataclasses.fields(data)} == {"title", "description", "location"}
        assert sample.gold.category not in vars(data)  # etiket taşınmaz

    def test_kaynak_ve_etiket_durumu_durustce_isaretli(self):
        for s in load_samples("v1"):
            assert s.source == "synthetic"
            assert s.label_status == "single_annotator_unreviewed"
        manifest = load_manifest("v1")
        assert manifest["priority_labels_human_reviewed"] is False


class TestValidate:
    def test_ayni_olay_iki_bolumde_olamaz(self):
        samples = [make(id="a", split="dev"), make(id="b", split="test")]

        with pytest.raises(DatasetError, match="sızıntı"):
            validate(samples)

    def test_yinelenen_kimlik_reddedilir(self):
        with pytest.raises(DatasetError, match="Yinelenen"):
            validate([make(id="a"), make(id="a", group="G2")])

    @pytest.mark.parametrize(
        "override",
        [
            {"split": "egitim"},
            {"gold": Gold("bilinmeyen", "normal", ())},
            {"gold": Gold("plumbing", "acil", ())},
            {"gold": Gold("plumbing", "normal", ("contact",))},  # v1'de değerlendirilmeyen etiket
            {"title": "  "},
            {"location": ""},
        ],
    )
    def test_gecersiz_alanlar_reddedilir(self, override):
        with pytest.raises(DatasetError):
            validate([make(**override)])
