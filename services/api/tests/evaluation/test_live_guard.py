import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.config import Settings
from app.decision.contract import ALL_QUESTIONS, StrategyName
from app.decision.factory import MissingApiKey, PaidCallsDisabled
from app.decision.retry import RetryPolicy
from app.decision.strategies import HybridStrategy, HybridThresholds, ProviderStrategy
from app.evaluation import runner
from app.evaluation.cli import main
from app.evaluation.dataset import load_samples
from app.evaluation.plan import PLANNABLE, estimate_plan, format_plan
from app.evaluation.report import build_report, write_report
from app.evaluation.runner import (
    LIVE_STRATEGY_BUILDERS,
    STRATEGY_BUILDERS,
    LiveRunGuard,
    run_evaluation,
)
from tests.decision.test_jev import ok_response as jev_ok_response
from tests.decision.test_jev import provider as jev_provider
from tests.decision.test_llm_anthropic import KEY
from tests.decision.test_llm_anthropic import ok_response as llm_ok_response
from tests.decision.test_llm_anthropic import provider as llm_provider

FIXED_NOW = datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)
NO_WAIT = RetryPolicy()
LLM_CALL_COST = Decimal("0.0019")  # test yanıtındaki 1100 girdi + 160 çıktı token'ının ücreti
JEV_CALL_COST = Decimal("0.000016464")  # 392 girdi token'ı
DEV_SAMPLES = 21


def git_stub():
    return {"source_commit": "abc123def456", "git_dirty": False}


def live_settings(**overrides) -> Settings:
    base = dict(
        _env_file=None,
        paid_model_calls_enabled=True,
        anthropic_api_key=KEY,
        jev_api_key="SIR-JEV-ANAHTAR-456",
    )
    return Settings(**{**base, **overrides})


def do_run(tmp_path, **kwargs):
    defaults = dict(
        splits=("dev",),
        out_root=tmp_path,
        now=lambda: FIXED_NOW,
        git=git_stub,
        settings=live_settings(),
    )
    return run_evaluation(**{**defaults, **kwargs})


def run_json(run_dir) -> dict:
    return json.loads((run_dir / "run.json").read_text(encoding="utf-8"))


def predictions(run_dir) -> list[dict]:
    lines = (run_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def install_llm(monkeypatch, handler):
    """`llm_only` gerçek adaptörünü sahte HTTP taşıyıcısıyla kurar (ağ isteği yok)."""

    def build(_settings):
        llm, requests = llm_provider(handler)
        build.requests = requests  # test, gönderilen istekleri buradan sayar
        return ProviderStrategy(StrategyName.LLM_ONLY, llm, NO_WAIT, lambda s: None)

    build.requests = []
    monkeypatch.setitem(LIVE_STRATEGY_BUILDERS, "llm_only", build)
    return build


class TestGuards:
    def test_gercek_stratejiler_varsayilan_listede_yok(self, tmp_path):
        assert set(LIVE_STRATEGY_BUILDERS) == {"jev_only", "llm_only", "hybrid"}
        assert not set(LIVE_STRATEGY_BUILDERS) & set(STRATEGY_BUILDERS)
        assert main(["run", "--splits", "dev", "--out", str(tmp_path)]) == 0  # varsayılan
        record = run_json(next(tmp_path.iterdir()))
        assert [s["name"] for s in record["strategies"]] == list(STRATEGY_BUILDERS)
        assert record["budget"]["live"] is False

    @pytest.mark.parametrize("cap", [None, Decimal(0), Decimal("-1")])
    def test_harcama_siniri_olmadan_gercek_strateji_kurulmaz_ve_calismaz(
        self, tmp_path, monkeypatch, cap
    ):
        def must_not_build(_settings):
            raise AssertionError("sınır yokken strateji kurulmamalı")

        monkeypatch.setitem(LIVE_STRATEGY_BUILDERS, "llm_only", must_not_build)

        with pytest.raises(LiveRunGuard, match="harcama sınırı"):
            do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=cap)

        assert not any(tmp_path.iterdir())  # hiçbir şey yazılmadı

    def test_ucretli_cagrilar_kapaliysa_acik_hata_ve_hicbir_sey_yazilmaz(self, tmp_path):
        settings = Settings(_env_file=None, anthropic_api_key=KEY)  # bayrak varsayılan: kapalı

        with pytest.raises(PaidCallsDisabled):
            do_run(
                tmp_path,
                strategy_names=("llm_only",),
                max_cost_usd=Decimal("1"),
                settings=settings,
            )

        assert not any(tmp_path.iterdir())

    def test_anahtar_yoksa_acik_hata_ve_hicbir_sey_yazilmaz(self, tmp_path):
        settings = Settings(_env_file=None, paid_model_calls_enabled=True)

        with pytest.raises(MissingApiKey):
            do_run(
                tmp_path,
                strategy_names=("hybrid",),
                max_cost_usd=Decimal("1"),
                settings=settings,
            )

        assert not any(tmp_path.iterdir())

    def test_negatif_sinir_ucretsiz_stratejilerde_de_gecersizdir(self, tmp_path):
        with pytest.raises(ValueError, match="pozitif"):
            do_run(tmp_path, strategy_names=("rule_based",), max_cost_usd=Decimal("-1"))

        assert not any(tmp_path.iterdir())

    def test_sinir_yalniz_ucretsiz_stratejilerde_zorunlu_degil(self, tmp_path):
        run_dir = do_run(tmp_path, strategy_names=("rule_based", "mock_jev"))

        assert run_json(run_dir)["budget"]["live"] is False
        assert run_json(run_dir)["stopped_early"] is None


class TestBudget:
    def test_sinira_ulasinca_ornek_sinirinda_durur(self, tmp_path, monkeypatch):
        build = install_llm(monkeypatch, lambda r: llm_ok_response())

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("0.005"))

        record = run_json(run_dir)
        assert len(predictions(run_dir)) == 2  # 0,0019 + 0,0019 = 0,0038; üçüncüsü 0,0057 > 0,005
        assert len(build.requests) == 2  # durduktan sonra istek atılmadı
        assert record["stopped_early"] == {
            "reason": "budget",
            "samples_completed": 2,
            "samples_planned": DEV_SAMPLES,
        }
        assert Decimal(record["budget"]["spent_known_usd"]) == Decimal("0.0038")
        assert Decimal(record["budget"]["spent_known_usd"]) <= Decimal(
            record["budget"]["max_cost_usd"]
        )
        assert record["dataset"]["n_samples"] == DEV_SAMPLES
        assert record["dataset"]["n_samples_completed"] == 2

    def test_yeterli_butcede_tum_ornekler_calisir(self, tmp_path, monkeypatch):
        install_llm(monkeypatch, lambda r: llm_ok_response())

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("1"))

        record = run_json(run_dir)
        assert len(predictions(run_dir)) == DEV_SAMPLES
        assert record["stopped_early"] is None
        assert Decimal(record["budget"]["spent_known_usd"]) == LLM_CALL_COST * DEV_SAMPLES
        assert record["budget"]["max_cost_usd"] == "1"
        assert record["budget"]["live"] is True

    def test_butce_ilk_ornekte_yetmese_bile_en_fazla_bir_ornek_calisir(self, tmp_path, monkeypatch):
        build = install_llm(monkeypatch, lambda r: llm_ok_response())

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("0.0001"))

        assert len(predictions(run_dir)) == 1 and len(build.requests) == 1
        assert run_json(run_dir)["stopped_early"]["reason"] == "budget"

    def test_tum_stratejiler_ayni_ornekleri_tamamlar(self, tmp_path, monkeypatch):
        install_llm(monkeypatch, lambda r: llm_ok_response())

        run_dir = do_run(
            tmp_path, strategy_names=("rule_based", "llm_only"), max_cost_usd=Decimal("0.005")
        )

        rows = predictions(run_dir)
        by_strategy = {
            name: {r["sample_id"] for r in rows if r["strategy"] == name}
            for name in ("rule_based", "llm_only")
        }
        assert by_strategy["rule_based"] == by_strategy["llm_only"]
        assert len(by_strategy["llm_only"]) == 2

    def test_maliyeti_bilinmeyen_cagri_calistirmayi_durdurur(self, tmp_path, monkeypatch):
        install_llm(monkeypatch, lambda r: llm_ok_response(usage={}))  # kullanım bildirilmedi

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("1"))

        record = run_json(run_dir)
        assert len(predictions(run_dir)) == 1
        assert record["stopped_early"]["reason"] == "unknown_cost"
        assert record["budget"]["billable_calls_with_unknown_cost"] == 1

    def test_sema_hatasi_yanitinin_ucreti_butceye_girer(self, tmp_path, monkeypatch):
        broken = {"category": {"answer": "bilinmeyen", "confidence": 0.5}}  # eksik/yanlış şema
        install_llm(monkeypatch, lambda r: llm_ok_response(broken))

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("1"))

        record = run_json(run_dir)
        # 3 deneme × 0,0019 ücretlendirildi (kullanım bildirildi); ilk örnek başarısız olarak kayıtlı.
        assert predictions(run_dir)[0]["failed"] is True
        assert Decimal(record["budget"]["spent_known_usd"]) >= LLM_CALL_COST * 3

    def test_hata_denemeleri_butceyi_durdurmaz_ama_raporda_bilinmiyor_gorunur(
        self, tmp_path, monkeypatch
    ):
        install_llm(monkeypatch, lambda r: httpx.Response(529))

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("0.01"))

        record = run_json(run_dir)
        assert len(predictions(run_dir)) == DEV_SAMPLES  # her örnek denendi, çalıştırma sürdü
        assert record["stopped_early"] is None
        assert record["budget"]["spent_known_usd"] == "0"
        metrics = build_report(run_dir)[1]["splits"]["dev"]["llm_only"]
        assert metrics["n_failed"] == DEV_SAMPLES
        assert metrics["calls_with_unknown_cost"] == 3 * DEV_SAMPLES  # 3 deneme × örnek

    def test_hibrit_gercek_adaptorlerle_harcama_jev_ve_llm_toplamidir(self, tmp_path, monkeypatch):
        def build(_settings):
            jev, _ = jev_provider(lambda r: jev_ok_response())
            llm, _ = llm_provider(lambda r: llm_ok_response())
            thresholds = HybridThresholds(dict.fromkeys(ALL_QUESTIONS, 0.99))  # hepsi LLM'e gider
            return HybridStrategy(jev, llm, thresholds, NO_WAIT, lambda s: None)

        monkeypatch.setitem(LIVE_STRATEGY_BUILDERS, "hybrid", build)

        run_dir = do_run(tmp_path, strategy_names=("hybrid",), max_cost_usd=Decimal("1"))

        record = run_json(run_dir)
        spent = Decimal(record["budget"]["spent_known_usd"])
        assert spent == (JEV_CALL_COST + LLM_CALL_COST) * DEV_SAMPLES
        strategy = record["strategies"][0]
        assert strategy["jev"]["model"] == "jev-1.13.0"
        assert strategy["llm"]["model"] == "claude-haiku-4-5-20251001"
        assert strategy["llm"]["temperature"] == 0.0
        assert strategy["is_mock"] is False

    def test_kayitlarda_anahtar_yok(self, tmp_path, monkeypatch):
        install_llm(monkeypatch, lambda r: llm_ok_response())

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("1"))
        write_report(run_dir)

        for path in run_dir.iterdir():
            text = path.read_text(encoding="utf-8")
            assert KEY not in text and "SIR-JEV-ANAHTAR-456" not in text

    def test_llm_stratejisinin_kaydi_model_istem_surumu_ve_sicakligi_tasir(
        self, tmp_path, monkeypatch
    ):
        install_llm(monkeypatch, lambda r: llm_ok_response())

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("0.002"))

        strategy = run_json(run_dir)["strategies"][0]
        assert strategy["provider"] == "anthropic" and strategy["temperature"] == 0.0
        assert strategy["model"] == "claude-haiku-4-5-20251001"
        assert strategy["prompt_version"].startswith("llm-istem-v1-")
        prices = {(p["provider"], p["model"]): p for p in run_json(run_dir)["prices"]}
        price = prices[("anthropic", "claude-haiku-4-5-20251001")]
        assert price["input_usd_per_mtok"] == "1" and price["output_usd_per_mtok"] == "5"


class TestInterruption:
    def test_kesinti_kaydi_yazar_ve_yarim_ornek_rapordan_cikar(self, tmp_path, monkeypatch):
        calls = {"n": 0}
        original = STRATEGY_BUILDERS["mock_jev"]

        class Interrupted:
            name = StrategyName.JEV_ONLY

            def __init__(self):
                self.inner = original()

            def decide(self, data):
                calls["n"] += 1
                if calls["n"] == 3:  # üçüncü örnekte, rule_based'ten sonra
                    raise KeyboardInterrupt
                return self.inner.decide(data)

        monkeypatch.setitem(STRATEGY_BUILDERS, "mock_jev", Interrupted)

        run_dir = do_run(tmp_path, strategy_names=("rule_based", "mock_jev"))

        record = run_json(run_dir)
        assert record["stopped_early"]["reason"] == "interrupted"
        assert record["stopped_early"]["samples_completed"] == 2
        assert len(predictions(run_dir)) == 5  # 2 tam örnek × 2 strateji + yarım örneğin 1 tahmini
        markdown, metrics = build_report(run_dir)
        assert "ÇALIŞTIRMA YARIDA KALDI" in markdown
        assert "çalıştırma elle kesildi" in markdown
        assert "Yarım kalan 1 örnek" in markdown
        dev = metrics["splits"]["dev"]
        assert dev["rule_based"]["n"] == dev["mock_jev"]["n"] == 2  # yarım örnek sayılmadı

    def test_beklenmeyen_hata_kaydi_yazar_ve_yeniden_firlar(self, tmp_path, monkeypatch):
        class Broken:
            name = StrategyName.RULE_BASED

            def decide(self, data):
                raise RuntimeError("GIZLI-HATA-METNI-77")

        monkeypatch.setitem(STRATEGY_BUILDERS, "rule_based", Broken)

        with pytest.raises(RuntimeError, match="GIZLI-HATA-METNI-77"):
            do_run(tmp_path, strategy_names=("rule_based",))

        record = run_json(next(tmp_path.iterdir()))
        assert record["stopped_early"]["reason"] == "error"
        assert record["stopped_early"]["error"] == "RuntimeError"
        assert "GIZLI-HATA-METNI-77" not in json.dumps(record)  # hata metni kayda girmez


class TestReport:
    def test_yarida_kalan_calistirma_uyarisi_ve_harcama_raporda(self, tmp_path, monkeypatch):
        install_llm(monkeypatch, lambda r: llm_ok_response())
        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("0.005"))

        markdown, metrics = build_report(run_dir)

        assert "ÇALIŞTIRMA YARIDA KALDI" in markdown
        assert "toplam harcama sınırına ulaşıldı" in markdown
        assert "2/21 örnek tamamlandı" in markdown
        assert "bilinen toplam 0,003800 USD, sınır 0,005000 USD" in markdown
        assert metrics["stopped_early"]["reason"] == "budget"
        assert "MOCK SONUÇLAR" not in markdown  # gerçek stratejiler mock değildir

    def test_tam_calistirmada_yarim_kalma_uyarisi_yok(self, tmp_path):
        markdown, metrics = build_report(do_run(tmp_path, strategy_names=("rule_based",)))

        assert "YARIDA KALDI" not in markdown
        assert metrics["stopped_early"] is None

    def test_eski_bicimli_run_json_hala_okunur(self, tmp_path):
        run_dir = do_run(tmp_path, strategy_names=("rule_based",))
        record = run_json(run_dir)
        for key in ("budget", "stopped_early"):
            del record[key]
        (run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")

        markdown, metrics = build_report(run_dir)

        assert "Değerlendirme raporu" in markdown and metrics["stopped_early"] is None


class TestPlan:
    def test_tahmin_ag_istegi_yapmaz_ve_tutarli_sayilar_uretir(self, monkeypatch):
        def no_network(self, request):
            raise AssertionError("tahmin sırasında ağ isteği atılmamalı")

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
        samples = [s for s in load_samples("v1") if s.split == "dev"]

        plan = estimate_plan(samples, PLANNABLE)

        lines = {line.strategy: line for line in plan.lines}
        assert plan.n_samples == DEV_SAMPLES and set(lines) == set(PLANNABLE)
        for line in lines.values():
            assert 0 < line.typical_low_usd <= line.typical_high_usd <= line.worst_usd
        jev, llm, hybrid = lines["jev_only"], lines["llm_only"], lines["hybrid"]
        assert jev.worst_usd == jev.typical_low_usd * 3  # 3 deneme hakkı
        assert llm.typical_low_usd > jev.typical_low_usd  # LLM'in çıktısı ücretli, fiyatı yüksek
        assert hybrid.typical_low_usd == jev.typical_low_usd  # alt sınır: yalnızca Jev
        assert hybrid.typical_high_usd == jev.typical_low_usd + llm.typical_low_usd
        assert hybrid.worst_usd == jev.worst_usd + llm.worst_usd
        assert plan.worst_usd == sum(line.worst_usd for line in plan.lines)

    def test_tahmin_yalniz_gercek_stratejiler_icin(self):
        with pytest.raises(ValueError, match="gerçek stratejiler"):
            estimate_plan([], ("rule_based",))

    def test_cikti_tahmin_oldugunu_ve_varsayimlari_acikca_soyler(self):
        samples = [s for s in load_samples("v1") if s.split == "dev"]

        text = format_plan(estimate_plan(samples, ("llm_only",)))

        assert "YAKLAŞIK TAHMİN" in text and "ölçüm değildir" in text
        assert "Varsayımlar" in text and "588" in text and "max_tokens" in text
        assert "21" in text  # örnek sayısı

    def test_cli_plan_komutu(self, capsys):
        assert main(["plan", "--splits", "dev"]) == 0

        out = capsys.readouterr().out
        assert "jev_only" in out and "llm_only" in out and "hybrid" in out and "TOPLAM" in out


class TestCli:
    def test_gercek_strateji_sinir_olmadan_acik_hata_verir_ve_plani_gosterir(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr(runner, "get_settings", lambda: live_settings())

        code = main(["run", "--strategies", "llm_only", "--out", str(tmp_path)])

        captured = capsys.readouterr()
        assert code == 2
        assert "harcama sınırı" in captured.err
        assert "YAKLAŞIK TAHMİN" in captured.out  # kullanıcı önce yaklaşık ücreti görür
        assert not any(tmp_path.iterdir())

    def test_sinir_var_ama_ucretli_cagrilar_kapali(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(runner, "get_settings", lambda: Settings(_env_file=None))

        code = main(
            [
                "run",
                "--strategies",
                "llm_only",
                "--max-cost-usd",
                "0.5",
                "--out",
                str(tmp_path),
            ]
        )

        assert code == 2
        assert "kapalı" in capsys.readouterr().err
        assert not any(tmp_path.iterdir())

    @pytest.mark.parametrize("value", ["abc", "0", "-1", "nan"])
    def test_gecersiz_sinir_reddedilir(self, value):
        with pytest.raises(SystemExit) as caught:
            main(["run", "--strategies", "llm_only", "--max-cost-usd", value])

        assert caught.value.code == 2
