import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.decision.contract import (
    CallRecord,
    CallStatus,
    DecisionInput,
    DecisionUnavailable,
    StrategyName,
)
from app.evaluation import report as report_module
from app.evaluation import runner
from app.evaluation.cli import main
from app.evaluation.dataset import load_samples
from app.evaluation.report import build_report, write_report
from app.evaluation.runner import STRATEGY_BUILDERS, TestSplitGuard, run_evaluation

FIXED_NOW = datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)


def git_stub():
    return {"source_commit": "abc123def456", "git_dirty": False}


def do_run(tmp_path, **kwargs):
    defaults = dict(
        splits=("dev",),
        out_root=tmp_path,
        now=lambda: FIXED_NOW,
        git=git_stub,
    )
    return run_evaluation(**{**defaults, **kwargs})


def read_predictions(run_dir):
    lines = (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


class TestRun:
    def test_her_ornek_icin_her_strateji_bir_tahmin_uretir(self, tmp_path):
        run_dir = do_run(tmp_path)

        predictions = read_predictions(run_dir)
        samples = [s for s in load_samples("v1") if s.split == "dev"]
        assert len(predictions) == len(samples) * len(STRATEGY_BUILDERS)
        assert {p["strategy"] for p in predictions} == set(STRATEGY_BUILDERS)
        assert {p["sample_id"] for p in predictions} == {s.id for s in samples}

    def test_yeniden_uretilebilirlik_kaydi(self, tmp_path):
        run_dir = do_run(tmp_path, shuffle_seed=7)

        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

        assert record["run_id"] == "20261002T120000Z-v1-dev"
        assert record["source_commit"] == "abc123def456" and record["git_dirty"] is False
        assert record["dataset"]["version"] == "v1"
        assert len(record["dataset"]["sha256"]) == 64
        assert record["dataset"]["sha256"] == record["dataset"]["manifest_sha256"]
        assert record["dataset"]["splits_used"] == ["dev"]
        assert record["config"]["concurrency"] == 1
        assert record["config"]["cache"] == "yok"
        assert record["config"]["shuffle_seed"] == 7
        assert record["config"]["retry"]["max_attempts"] == 3
        assert {p["provider"] for p in record["prices"]} >= {"jev", "mock-jev", "mock-llm"}
        jev_price = next(p for p in record["prices"] if p["provider"] == "jev")
        assert (
            jev_price["input_usd_per_mtok"] == "0.042" and jev_price["checked_on"] == "2026-10-02"
        )
        assert "python" in record["environment"]

    def test_stratejiler_modeller_ve_istem_surumleri_kaydedilir(self, tmp_path):
        run_dir = do_run(tmp_path)

        strategies = {
            s["name"]: s
            for s in json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["strategies"]
        }

        assert strategies["rule_based"]["rules_version"].startswith("kurallar-")
        assert not strategies["rule_based"]["is_mock"]
        assert strategies["mock_jev"]["model"] == "mock-jev-1" and strategies["mock_jev"]["is_mock"]
        hybrid = strategies["mock_hybrid"]
        assert hybrid["jev"]["model"] == "mock-jev-1" and hybrid["llm"]["model"] == "mock-llm-1"
        assert set(hybrid["thresholds"]) == {
            "category",
            "priority",
            "missing_location",
            "missing_detail",
            "missing_contact",
            "missing_timing",
        }

    def test_strateji_sirasi_ornekler_arasinda_doner(self, tmp_path):
        run_dir = do_run(tmp_path)

        predictions = read_predictions(run_dir)
        n = len(STRATEGY_BUILDERS)
        firsts = [predictions[i * n]["strategy"] for i in range(4)]
        assert firsts == list(STRATEGY_BUILDERS)[:4]  # her örnekte başlangıç stratejisi değişir

    def test_tohumlu_karistirma_tekrarlanabilir_ve_farkli_tohum_farkli_sira(self, tmp_path):
        def order(seed, subdir):
            run_dir = do_run(tmp_path / subdir, shuffle_seed=seed, strategy_names=("rule_based",))
            return [p["sample_id"] for p in read_predictions(run_dir)]

        assert order(1, "a") == order(1, "b")
        assert order(1, "c") != order(2, "d")

    def test_yalniz_istenen_bolum_calisir(self, tmp_path):
        run_dir = do_run(tmp_path, splits=("val",), strategy_names=("rule_based",))

        samples = {s.id: s for s in load_samples("v1")}
        assert {samples[p["sample_id"]].split for p in read_predictions(run_dir)} == {"val"}


class TestGuards:
    def test_test_bolumu_nihai_olmadan_calismaz(self, tmp_path):
        with pytest.raises(TestSplitGuard, match="nihai"):
            do_run(tmp_path, splits=("dev", "test"))
        assert not any(tmp_path.iterdir())  # hiçbir şey yazılmadı

    def test_nihai_bayragiyla_test_bolumu_calisir(self, tmp_path):
        run_dir = do_run(tmp_path, splits=("test",), final=True, strategy_names=("rule_based",))

        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        assert record["config"]["final"] is True and record["dataset"]["splits_used"] == ["test"]

    @pytest.mark.parametrize(
        "kwargs", [{"splits": ("egitim",)}, {"strategy_names": ("gercek_jev",)}]
    )
    def test_gecersiz_bolum_veya_strateji(self, tmp_path, kwargs):
        with pytest.raises(ValueError):
            do_run(tmp_path, **kwargs)

    def test_stratejiler_yalniz_asgari_girdiyi_gorur_etiket_degil(self, tmp_path, monkeypatch):
        seen = []
        original = STRATEGY_BUILDERS["rule_based"]  # yamadan ÖNCE yakala (özyineleme olmasın)

        class Spy:
            name = StrategyName.RULE_BASED

            def decide(self, data):
                seen.append(data)
                return original().decide(data)

        monkeypatch.setitem(STRATEGY_BUILDERS, "rule_based", Spy)

        do_run(tmp_path, strategy_names=("rule_based",))

        assert seen and all(type(d) is DecisionInput for d in seen)
        assert all(set(vars(d)) == {"title", "description", "location"} for d in seen)


class TestFailures:
    def test_kalici_hata_kayda_gecer_ve_maliyeti_korunur(self, tmp_path, monkeypatch):
        attempt = CallRecord(
            strategy=StrategyName.JEV_ONLY,
            provider="jev",
            model="jev-1.13.0",
            prompt_version="v",
            questions=(),
            status=CallStatus.UNAVAILABLE,
            input_tokens=None,
            error="HTTP 529",
        )

        class Broken:
            name = StrategyName.JEV_ONLY

            def decide(self, data):
                raise DecisionUnavailable("jev yanıt vermedi", calls=(attempt, attempt))

        monkeypatch.setitem(STRATEGY_BUILDERS, "rule_based", Broken)

        run_dir = do_run(tmp_path, strategy_names=("rule_based",))

        predictions = read_predictions(run_dir)
        assert all(p["failed"] and p["error"] and len(p["calls"]) == 2 for p in predictions)
        metrics = build_report(run_dir)[1]["splits"]["dev"]["rule_based"]
        assert metrics["n_failed"] == metrics["n"] > 0
        assert metrics["category_accuracy"]["n"] == 0  # hata, başarı olarak sayılmaz
        assert metrics["calls_with_unknown_cost"] == 2 * metrics["n"]
        assert metrics["cost_total_usd"] is None


class TestReport:
    def test_rapor_kayitli_ciktilardan_model_cagrisi_olmadan_uretilir(self, tmp_path, monkeypatch):
        run_dir = do_run(tmp_path)

        class Explodes:
            def __init__(self, *a, **k):
                raise AssertionError("rapor sırasında strateji kurulmamalı")

        monkeypatch.setattr(runner, "STRATEGY_BUILDERS", {n: Explodes for n in STRATEGY_BUILDERS})
        monkeypatch.setattr(report_module, "dataset_sha256", report_module.dataset_sha256)

        markdown, metrics = build_report(run_dir)

        assert "Değerlendirme raporu" in markdown
        assert set(metrics["splits"]["dev"]) == set(STRATEGY_BUILDERS)

    def test_ayni_kayitlardan_ayni_rapor(self, tmp_path):
        run_dir = do_run(tmp_path)

        first = build_report(run_dir)
        second = build_report(run_dir)

        assert first == second

    def test_mock_varsa_uyari_ve_gercek_olcum_degil_notu(self, tmp_path):
        markdown, _ = build_report(do_run(tmp_path))

        assert "MOCK SONUÇLAR" in markdown
        assert "gerçek model ölçümü değildir" in markdown
        assert "| `mock_jev` | evet |" in markdown
        assert "| `rule_based` | hayır |" in markdown

    def test_yalniz_kurali_taban_varsa_mock_uyarisi_yok(self, tmp_path):
        markdown, _ = build_report(do_run(tmp_path, strategy_names=("rule_based",)))

        assert "MOCK SONUÇLAR" not in markdown

    def test_kayit_ve_sinirlamalar_bolumleri_var(self, tmp_path):
        markdown, _ = build_report(do_run(tmp_path))

        assert "abc123def456" in markdown  # kaynak commit
        assert "sha256" in markdown and "single_annotator_unreviewed" in markdown
        assert "## Sınırlamalar ve okuma notları" in markdown
        assert "Sentetik veri" in markdown and "Küçük örneklem" in markdown
        assert "tokenizer" in markdown
        assert "%" in markdown and "," in markdown  # Türkçe ondalık biçimi

    def test_veri_seti_degismisse_uyarir(self, tmp_path, monkeypatch):
        run_dir = do_run(tmp_path)
        monkeypatch.setattr(report_module, "dataset_sha256", lambda version: "0" * 64)

        markdown, _ = build_report(run_dir)

        assert "veri seti" in markdown and "sha256 uyuşmuyor" in markdown

    def test_bilinmeyen_maliyet_raporda_bilinmiyor_olarak_gorunur(self, tmp_path):
        run_dir = do_run(tmp_path, strategy_names=("mock_jev",))
        lines = (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines]
        rows[0]["calls"][0]["cost_usd"] = None  # bir çağrının maliyeti bilinmiyor
        (run_dir / "predictions.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
        )

        markdown, metrics = build_report(run_dir)

        assert "bilinmiyor (1 çağrı" in markdown
        assert metrics["splits"]["dev"]["mock_jev"]["cost_total_usd"] is None
        assert Decimal(metrics["splits"]["dev"]["mock_jev"]["cost_known_usd"]) == 0

    def test_write_report_dosyalari_yazar(self, tmp_path):
        run_dir = do_run(tmp_path)

        path = write_report(run_dir)

        assert path == run_dir / "report.md" and path.read_text(encoding="utf-8").startswith("# ")
        assert json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))["splits"]["dev"]


class TestCli:
    def test_run_ve_report_komutlari(self, tmp_path, capsys):
        assert (
            main(["run", "--splits", "dev", "--strategies", "rule_based", "--out", str(tmp_path)])
            == 0
        )
        run_dir = next(tmp_path.iterdir())

        assert main(["report", "--run", str(run_dir)]) == 0

        assert (run_dir / "report.md").exists() and (run_dir / "metrics.json").exists()
        assert "Rapor yazıldı" in capsys.readouterr().out

    def test_test_bolumu_icin_nihai_bayragi_gerekir(self, tmp_path, capsys):
        code = main(["run", "--splits", "test", "--out", str(tmp_path)])

        assert code == 2
        assert "nihai" in capsys.readouterr().err

    def test_bilinmeyen_strateji_acik_hata(self, tmp_path, capsys):
        assert main(["run", "--strategies", "yok", "--out", str(tmp_path)]) == 2
        assert "Bilinmeyen strateji" in capsys.readouterr().err
