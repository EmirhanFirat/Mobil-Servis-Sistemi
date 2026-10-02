from decimal import Decimal

import pytest

from app.evaluation.dataset import CATEGORY_LABELS, Gold, Sample
from app.evaluation.metrics import (
    Prediction,
    Proportion,
    class_scores,
    compute_metrics,
    confusion,
    macro_f1,
    percentile,
    wilson_interval,
)


def sample(id, category="plumbing", priority="normal", missing=(), review=False, tags=()):
    return Sample(
        id=id,
        group=f"G{id}",
        split="dev",
        title="t",
        description="d",
        location="l",
        gold=Gold(category, priority, tuple(missing)),
        expected_review=review,
        tags=tuple(tags),
        variant="resmi",
        source="synthetic",
        label_status="x",
    )


def pred(
    sample_id,
    category="plumbing",
    priority="normal",
    missing=(),
    review=False,
    failed=False,
    latency=10.0,
    calls=(),
    mock=False,
    strategy="s",
):
    return Prediction(
        sample_id=sample_id,
        strategy=strategy,
        failed=failed,
        category=category,
        priority=priority,
        missing_info=tuple(missing),
        review_required=review,
        review_reasons=(),
        latency_ms=latency,
        is_mock=mock,
        calls=list(calls),
    )


def call(cost="0.001", status="ok", tokens=(100, 10)):
    return {
        "cost_usd": cost,
        "status": status,
        "input_tokens": tokens[0] if tokens else None,
        "output_tokens": tokens[1] if tokens else None,
    }


class TestPrimitives:
    def test_wilson_bilinen_degerler(self):
        assert wilson_interval(0, 0) is None
        low, high = wilson_interval(5, 10)
        assert low == pytest.approx(0.2366, abs=1e-3) and high == pytest.approx(0.7634, abs=1e-3)
        low, high = wilson_interval(10, 10)
        assert high == pytest.approx(1.0) and low == pytest.approx(0.7225, abs=1e-3)
        assert wilson_interval(0, 10)[0] == 0.0

    def test_kucuk_orneklemde_aralik_genistir(self):
        small = wilson_interval(8, 10)
        large = wilson_interval(80, 100)

        assert (small[1] - small[0]) > (large[1] - large[0])

    def test_yuzdelik_dogrusal_enterpolasyon(self):
        assert percentile([], 50) is None
        assert percentile([7.0], 95) == 7.0
        assert percentile([1, 2, 3, 4], 50) == 2.5
        assert percentile([10, 20, 30, 40, 50], 95) == pytest.approx(48.0)
        assert percentile([5, 1, 3], 0) == 1  # sıralı değil girdi

    def test_proportion(self):
        assert Proportion(1, 4).value == 0.25
        assert Proportion(0, 0).value is None and Proportion(0, 0).interval is None

    def test_sinif_skorlari_ve_makro_f1(self):
        gold = ["a", "a", "b", "b", "c"]
        predicted = ["a", "b", "b", "b", "a"]

        scores = class_scores(gold, predicted, ("a", "b", "c", "d"))

        assert scores["a"].precision == 0.5 and scores["a"].recall == 0.5
        assert scores["b"].precision == pytest.approx(2 / 3) and scores["b"].recall == 1.0
        assert scores["c"].support == 1 and scores["c"].f1 == 0.0
        assert scores["d"].support == 0 and scores["d"].f1 is None  # destek yok → ortalamaya girmez
        assert macro_f1(scores) == pytest.approx((0.5 + 0.8 + 0.0) / 3)

    def test_karisiklik_matrisi(self):
        matrix = confusion(["a", "a", "b"], ["a", "b", "b"], ("a", "b"))

        assert matrix == {"a": {"a": 1, "b": 1}, "b": {"a": 0, "b": 1}}


class TestComputeMetrics:
    def build(self, rows):
        samples = {s.id: s for s, _ in rows}
        return compute_metrics(samples, [p for _, p in rows], "s")

    def test_dogruluk_ve_belirsiz_tahmin_unclear_sayilir(self):
        rows = [
            (sample("1", "plumbing"), pred("1", "plumbing")),
            (sample("2", "electrical"), pred("2", "plumbing")),
            (sample("3", "unclear"), pred("3", None)),  # model çekimser = "unclear" doğru
            (sample("4", "cleaning"), pred("4", None)),  # çekimser ama gerçek cleaning → yanlış
        ]

        m = self.build(rows)

        assert (m.category_accuracy.successes, m.category_accuracy.n) == (2, 4)
        assert m.category_confusion["cleaning"]["unclear"] == 1
        assert set(m.category_confusion) == set(CATEGORY_LABELS)

    def test_basarisiz_kararlar_dogruluktan_dusulur_hata_orani_ayri(self):
        rows = [
            (sample("1"), pred("1")),
            (sample("2"), pred("2", None, None, failed=True)),
        ]

        m = self.build(rows)

        assert m.n == 2 and m.n_failed == 1
        assert m.category_accuracy.n == 1  # yalnızca tamamlanan karar
        assert m.failure_rate.value == 0.5

    def test_yuksek_oncelik_recall_ve_kacirilanlar(self):
        rows = [
            (sample("1", priority="high"), pred("1", priority="high")),
            (sample("2", priority="high"), pred("2", priority="normal")),
            (sample("3", priority="high"), pred("3", priority="low")),
            (
                sample("4", priority="normal"),
                pred("4", priority="high"),
            ),  # fazladan yüksek recall'ı etkilemez
        ]

        m = self.build(rows)

        assert (m.high_priority_recall.successes, m.high_priority_recall.n) == (1, 3)
        assert m.high_priority_missed == ("2", "3")

    def test_otomasyon_ve_inceleme_metrikleri(self):
        rows = [
            (sample("1", review=False), pred("1", review=False)),  # otomatik, doğru
            (
                sample("2", "electrical", review=False),
                pred("2", "plumbing", review=False),
            ),  # otomatik, yanlış
            (sample("3", review=True), pred("3", review=True)),  # doğru inceleme
            (sample("4", review=False), pred("4", review=True)),  # gereksiz inceleme
            (sample("5", review=True), pred("5", review=False)),  # kaçırılan inceleme
        ]

        m = self.build(rows)

        assert (m.review_rate.successes, m.review_rate.n) == (2, 5)
        assert (m.automated_category_accuracy.successes, m.automated_category_accuracy.n) == (2, 3)
        assert (m.review_precision.successes, m.review_precision.n) == (
            1,
            2,
        )  # 2 işaretlenenin 1'i gerekliydi
        assert (m.review_recall.successes, m.review_recall.n) == (
            1,
            2,
        )  # gerekli 2'nin 1'i işaretlendi
        assert (
            m.correct_automated == 2
        )  # ikisi de kategori+öncelik doğru; inceleme bırakılan sayılmaz

    def test_eksik_bilgi_etiketleri(self):
        rows = [
            (sample("1", missing=["location"]), pred("1", missing=["location"])),
            (sample("2", missing=["location"]), pred("2", missing=[])),
            (sample("3", missing=[]), pred("3", missing=["location"])),
            (sample("4", missing=["detail"]), pred("4", missing=["detail"])),
        ]

        m = self.build(rows)

        assert m.missing_scores["location"].precision == 0.5
        assert m.missing_scores["location"].recall == 0.5
        assert m.missing_scores["detail"].f1 == 1.0

    def test_gecikme_yuzdelikleri(self):
        rows = [(sample(str(i)), pred(str(i), latency=float(i))) for i in range(1, 6)]

        m = self.build(rows)

        assert m.latency_p50_ms == 3.0
        assert m.latency_p95_ms == pytest.approx(4.8)

    def test_maliyet_bilinen_toplam_ve_karar_basi(self):
        rows = [
            (sample("1"), pred("1", calls=[call("0.002"), call("0.001")])),
            (sample("2"), pred("2", calls=[call("0.003")])),
        ]

        m = self.build(rows)

        assert m.cost_known_usd == Decimal("0.006")
        assert m.cost_total_usd == Decimal("0.006")
        assert m.cost_per_decision_usd == Decimal("0.003")
        assert m.cost_per_correct_usd == Decimal("0.003")  # 2 doğru otomatik karar
        assert (m.calls_total, m.calls_failed) == (3, 0)
        assert (m.input_tokens_known, m.output_tokens_known) == (300, 30)

    def test_bilinmeyen_maliyet_sifir_sayilmaz(self):
        rows = [
            (
                sample("1"),
                pred("1", calls=[call("0.002"), call(None, status="timeout", tokens=None)]),
            ),
            (sample("2"), pred("2", calls=[call("0.003")])),
        ]

        m = self.build(rows)

        assert m.calls_with_unknown_cost == 1
        assert m.cost_total_usd is None  # toplam bilinmiyor
        assert m.cost_known_usd == Decimal("0.005")  # bilinen kısım ayrı
        assert m.cost_per_decision_usd is None and m.cost_per_correct_usd is None
        assert m.calls_failed == 1 and m.calls_without_usage == 1

    def test_basarisiz_kararin_cagri_maliyeti_toplama_girer(self):
        failed = pred("1", None, None, failed=True, calls=[call("0.004", status="unavailable")])
        rows = [(sample("1"), failed), (sample("2"), pred("2", calls=[call("0.001")]))]

        m = self.build(rows)

        assert m.cost_known_usd == Decimal("0.005")
        assert m.calls_failed == 1

    def test_etiket_bazinda_dogruluk_ve_mock_isareti(self):
        rows = [
            (sample("1", tags=["typo"]), pred("1", mock=True)),
            (sample("2", "electrical", tags=["typo", "hazard"]), pred("2", "plumbing", mock=True)),
        ]

        m = self.build(rows)

        assert (m.by_tag["typo"].successes, m.by_tag["typo"].n) == (1, 2)
        assert (m.by_tag["hazard"].successes, m.by_tag["hazard"].n) == (0, 1)
        assert m.is_mock

    def test_bos_veri_cokmez(self):
        m = compute_metrics({}, [], "yok")

        assert m.n == 0 and m.category_accuracy.value is None
        assert m.cost_per_decision_usd is None and m.latency_p50_ms is None
