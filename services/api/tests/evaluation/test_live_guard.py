import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.config import Settings
from app.decision.budget import max_call_cost, worst_decision_cost
from app.decision.contract import ALL_QUESTIONS, DECISION_QUESTIONS, StrategyName
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
    select_samples,
)
from tests.decision.test_jev import ok_response as jev_ok_response
from tests.decision.test_jev import provider as jev_provider
from tests.decision.test_llm_anthropic import KEY, usage_block
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


def budget_dir_for(tmp_path):
    """Bütçe defteri, çıktı klasöründen AYRI bir klasörde (çıktı klasörü 'boş mu' denetlenir)."""
    return tmp_path.parent / f"{tmp_path.name}-defter"


def do_run(tmp_path, **kwargs):
    defaults = dict(
        splits=("dev",),
        out_root=tmp_path,
        now=lambda: FIXED_NOW,
        git=git_stub,
        settings=live_settings(),
        budget_id="test-butce",
        budget_dir=budget_dir_for(tmp_path),
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


def first_dev_input():
    return [s for s in load_samples("v1") if s.split == "dev"][0].to_input()


def llm_worst_cost_for(data) -> Decimal:
    """Bir `llm_only` kararının en kötü durum ücreti (bütçe korumasının ön denetimiyle aynı hesap)."""
    llm, _ = llm_provider(lambda r: llm_ok_response())
    return worst_decision_cost(ProviderStrategy(StrategyName.LLM_ONLY, llm, NO_WAIT), data)


class TestBudget:
    def test_sinir_tek_karari_bile_karsilamiyorsa_hicbir_istek_gonderilmez(
        self, tmp_path, monkeypatch
    ):
        build = install_llm(monkeypatch, lambda r: llm_ok_response())

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("0.001"))

        record = run_json(run_dir)
        assert predictions(run_dir) == [] and build.requests == []
        assert record["stopped_early"] == {
            "reason": "budget",
            "samples_completed": 0,
            "samples_planned": DEV_SAMPLES,
        }
        assert record["budget"]["spent_usd"] == "0" and record["budget"]["calls"] == 0

    def test_ilk_ornegin_en_kotu_durumu_karsilanmiyorsa_baslanmaz_karsilaniyorsa_baslar(
        self, tmp_path, monkeypatch
    ):
        worst = llm_worst_cost_for(first_dev_input())
        build = install_llm(monkeypatch, lambda r: llm_ok_response())

        do_run(
            tmp_path / "kucuk",
            strategy_names=("llm_only",),
            max_cost_usd=worst - Decimal("0.000001"),
            limit=1,
        )
        assert build.requests == []  # bir kuruş eksik: tek istek bile gönderilmez

        run_dir = do_run(
            tmp_path / "yeterli", strategy_names=("llm_only",), max_cost_usd=worst, limit=1
        )
        assert len(build.requests) == 1 and len(predictions(run_dir)) == 1

    @pytest.mark.parametrize("cap", ["0.03", "0.05", "0.1", "0.2", "0.5"])
    def test_harcama_hicbir_zaman_siniri_asmaz(self, tmp_path, monkeypatch, cap):
        build = install_llm(monkeypatch, lambda r: llm_ok_response())

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal(cap))

        record = run_json(run_dir)
        budget = record["budget"]
        assert Decimal(budget["spent_usd"]) <= Decimal(cap)  # KESİN sınır
        assert budget["bound_violations"] == 0
        assert budget["calls"] == len(build.requests)  # her gönderilen istek sayıldı
        assert len(predictions(run_dir)) == record["dataset"]["n_samples_completed"]
        if record["stopped_early"]:
            assert record["stopped_early"]["reason"] == "budget"

    def test_yeterli_butcede_tum_ornekler_calisir_ucret_gercek_kullanimdan_hesaplanir(
        self, tmp_path, monkeypatch
    ):
        install_llm(monkeypatch, lambda r: llm_ok_response())

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("1"))

        record = run_json(run_dir)
        assert len(predictions(run_dir)) == DEV_SAMPLES and record["stopped_early"] is None
        budget = record["budget"]
        assert Decimal(budget["spent_usd"]) == LLM_CALL_COST * DEV_SAMPLES
        assert budget["known_spent_usd"] == budget["spent_usd"]
        assert budget["conservative_charges"] == 0 and budget["live"] is True
        assert budget["max_cost_usd"] == "1"

    def test_tum_stratejiler_ayni_ornekleri_tamamlar(self, tmp_path, monkeypatch):
        install_llm(monkeypatch, lambda r: llm_ok_response())

        run_dir = do_run(
            tmp_path, strategy_names=("rule_based", "llm_only"), max_cost_usd=Decimal("0.1")
        )

        rows = predictions(run_dir)
        by_strategy = {
            name: {r["sample_id"] for r in rows if r["strategy"] == name}
            for name in ("rule_based", "llm_only")
        }
        assert by_strategy["rule_based"] == by_strategy["llm_only"] and by_strategy["llm_only"]

    def test_kullanimi_bilinmeyen_cagri_ucretsiz_sayilmaz_en_kotu_bedelle_sayilir(
        self, tmp_path, monkeypatch
    ):
        install_llm(monkeypatch, lambda r: llm_ok_response(usage={}))  # kullanım bildirilmedi

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("0.1"))

        record = run_json(run_dir)
        budget = record["budget"]
        assert budget["conservative_charges"] == budget["calls"] > 0
        assert budget["known_spent_usd"] == "0"
        assert Decimal("0.01") < Decimal(budget["spent_usd"]) <= Decimal("0.1")  # sıfır DEĞİL
        assert record["stopped_early"]["reason"] == "budget"  # bedel hızla tükenir

    def test_http_hatalari_ve_zaman_asimi_da_ucretsiz_sayilmaz(self, tmp_path, monkeypatch):
        build = install_llm(monkeypatch, lambda r: httpx.Response(529))

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("0.1"))

        record = run_json(run_dir)
        budget = record["budget"]
        assert budget["calls"] == len(build.requests) == 6  # 2 başarısız karar × 3 deneme
        assert budget["conservative_charges"] == budget["calls"]  # her biri en kötü bedelle sayıldı
        assert budget["known_spent_usd"] == "0"
        assert 0 < Decimal(budget["spent_usd"]) <= Decimal("0.1")  # ücretsiz SAYILMADI
        # Sistematik kesinti: bütçeyi boşuna yakmamak için ardışık 2 başarısız kararda durulur.
        assert record["stopped_early"]["reason"] == "provider_unavailable"
        assert all(p["failed"] for p in predictions(run_dir))  # kararlar başarısız, ücret sayıldı

    def test_sema_hatasi_yaniti_kullanim_bildirdigi_icin_gercek_ucretle_sayilir(
        self, tmp_path, monkeypatch
    ):
        broken = {"category": {"answer": "bilinmeyen", "confidence": 0.5}}
        install_llm(monkeypatch, lambda r: llm_ok_response(broken))

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("1"))

        record = run_json(run_dir)
        assert all(p["failed"] for p in predictions(run_dir))
        # 2 başarısız karar × 3 deneme; yanıtlar kullanım bildirdiği için GERÇEK ücretle sayılır.
        assert Decimal(record["budget"]["spent_usd"]) == LLM_CALL_COST * 6
        assert record["budget"]["conservative_charges"] == 0
        assert record["stopped_early"]["reason"] == "provider_unavailable"

    def test_gercek_ucret_rezervasyonu_asarsa_calistirma_durur(self, tmp_path, monkeypatch):
        huge = usage_block(input_tokens=5_000_000)  # tahminin çok üstünde bir kullanım
        install_llm(monkeypatch, lambda r: llm_ok_response(usage=huge))

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("100"))

        record = run_json(run_dir)
        assert record["budget"]["bound_violations"] == 1
        assert record["stopped_early"]["reason"] == "estimate_violated"
        assert record["stopped_early"]["samples_completed"] == 1  # ihlalden sonra yeni örnek yok

    def test_fiyati_bilinmeyen_saglayicida_ucret_sinirlanamaz_hicbir_istek_gonderilmez(
        self, tmp_path, monkeypatch
    ):
        seen = []

        def build(_settings):
            llm, requests = llm_provider(lambda r: llm_ok_response(), price=None)
            seen.append(requests)
            return ProviderStrategy(StrategyName.LLM_ONLY, llm, NO_WAIT, lambda s: None)

        monkeypatch.setitem(LIVE_STRATEGY_BUILDERS, "llm_only", build)

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("1"))

        assert run_json(run_dir)["stopped_early"]["reason"] == "unbounded"
        assert seen[0] == [] and predictions(run_dir) == []

    def test_butce_karar_ortasinda_biterse_yarim_karar_run_json_a_yazilir_tahmin_sayilmaz(
        self, tmp_path, monkeypatch
    ):
        # Ön denetimi atlayıp (varsayım ihlali benzetimi) bütçenin LLM aşamasında bitmesini sağla.
        monkeypatch.setattr(runner, "worst_decision_cost", lambda strategy, data: Decimal(0))
        jev_probe, _ = jev_provider(lambda r: jev_ok_response())
        llm_probe, _ = llm_provider(lambda r: llm_ok_response())
        data = first_dev_input()
        cap = max_call_cost(jev_probe, data) + max_call_cost(llm_probe, data) / 2
        seen = {}

        def build(_settings):
            jev, seen["jev"] = jev_provider(lambda r: jev_ok_response())
            llm, seen["llm"] = llm_provider(lambda r: llm_ok_response())
            thresholds = HybridThresholds(dict.fromkeys(ALL_QUESTIONS, 0.99))  # hepsi LLM'e gider
            return HybridStrategy(jev, llm, thresholds, NO_WAIT, lambda s: None)

        monkeypatch.setitem(LIVE_STRATEGY_BUILDERS, "hybrid", build)

        run_dir = do_run(tmp_path, strategy_names=("hybrid",), max_cost_usd=cap)

        record = run_json(run_dir)
        assert predictions(run_dir) == []  # yarım karar tahmin sayılmadı
        assert len(seen["jev"]) == 1 and seen["llm"] == []  # LLM isteği hiç gönderilmedi
        assert record["stopped_early"]["reason"] == "budget"
        assert record["stopped_early"]["samples_completed"] == 0
        aborted = record["aborted_prediction"]
        assert aborted["reason"] == "budget"
        assert (
            aborted["strategy"] == "hybrid" and len(aborted["calls"]) == 1
        )  # Jev harcaması kayıtlı
        assert aborted["calls"][0]["provider"] == "jev"
        assert Decimal(record["budget"]["spent_usd"]) == JEV_CALL_COST  # harcama sayaçta
        markdown, _ = build_report(run_dir)
        assert "Yarıda kesilen karar (neden: bir sonraki karar/çağrı" in markdown

    def test_hibrit_gercek_adaptorlerle_harcama_jev_ve_llm_toplamidir(self, tmp_path, monkeypatch):
        def build(_settings):
            jev, _ = jev_provider(lambda r: jev_ok_response())
            llm, _ = llm_provider(lambda r: llm_ok_response())
            thresholds = HybridThresholds(dict.fromkeys(ALL_QUESTIONS, 0.99))  # hepsi LLM'e gider
            return HybridStrategy(jev, llm, thresholds, NO_WAIT, lambda s: None)

        monkeypatch.setitem(LIVE_STRATEGY_BUILDERS, "hybrid", build)

        run_dir = do_run(tmp_path, strategy_names=("hybrid",), max_cost_usd=Decimal("1"))

        record = run_json(run_dir)
        assert Decimal(record["budget"]["spent_usd"]) == (JEV_CALL_COST + LLM_CALL_COST) * (
            DEV_SAMPLES
        )
        strategy = record["strategies"][0]
        assert strategy["jev"]["model"] == "jev-1.13.0"
        assert strategy["llm"]["model"] == "claude-haiku-4-5-20251001"
        assert strategy["llm"]["temperature"] == 0.0
        assert strategy["is_mock"] is False

    def test_kayitlarda_anahtar_yok(self, tmp_path, monkeypatch):
        install_llm(monkeypatch, lambda r: llm_ok_response())

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("1"), limit=2)
        write_report(run_dir)

        for path in run_dir.iterdir():
            text = path.read_text(encoding="utf-8")
            assert KEY not in text and "SIR-JEV-ANAHTAR-456" not in text

    def test_llm_stratejisinin_kaydi_model_istem_surumu_ve_sicakligi_tasir(
        self, tmp_path, monkeypatch
    ):
        install_llm(monkeypatch, lambda r: llm_ok_response())

        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("1"), limit=1)

        strategy = run_json(run_dir)["strategies"][0]
        assert strategy["provider"] == "anthropic" and strategy["temperature"] == 0.0
        assert strategy["model"] == "claude-haiku-4-5-20251001"
        assert strategy["prompt_version"].startswith("llm-istem-v1-")
        prices = {(p["provider"], p["model"]): p for p in run_json(run_dir)["prices"]}
        price = prices[("anthropic", "claude-haiku-4-5-20251001")]
        assert price["input_usd_per_mtok"] == "1" and price["output_usd_per_mtok"] == "5"


class TestLimit:
    def test_limit_ilk_n_ornegi_calistirir_ve_kayda_yazilir(self, tmp_path):
        run_dir = do_run(tmp_path, strategy_names=("rule_based",), limit=3)

        record = run_json(run_dir)
        assert len(predictions(run_dir)) == 3 and record["dataset"]["limit"] == 3
        assert record["dataset"]["n_samples"] == 3

    def test_secim_deterministiktir_tohumlu_karistirma_farkli_ornekler_secer(self):
        first = [s.id for s in select_samples("v1", ("dev",), limit=5)]

        assert first == [s.id for s in select_samples("v1", ("dev",), limit=5)]
        seeded = [s.id for s in select_samples("v1", ("dev",), shuffle_seed=3, limit=5)]
        assert seeded == [s.id for s in select_samples("v1", ("dev",), shuffle_seed=3, limit=5)]
        assert seeded != first and len(seeded) == 5

    @pytest.mark.parametrize("value", [0, -2])
    def test_gecersiz_limit_reddedilir(self, tmp_path, value):
        with pytest.raises(ValueError, match="en az 1"):
            do_run(tmp_path, strategy_names=("rule_based",), limit=value)

        assert not any(tmp_path.iterdir())


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
        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("0.05"))
        record = run_json(run_dir)
        completed = record["dataset"]["n_samples_completed"]

        markdown, metrics = build_report(run_dir)

        assert 0 < completed < DEV_SAMPLES
        assert "ÇALIŞTIRMA YARIDA KALDI" in markdown
        assert "kalan harcama sınırını aşacaktı" in markdown
        assert f"{completed}/21 örnek tamamlandı" in markdown
        assert "sınır 0,050000 USD" in markdown and "Sınır yöntemi" in markdown
        assert metrics["stopped_early"]["reason"] == "budget"
        assert metrics["budget"]["conservative_charges"] == 0
        assert "MOCK SONUÇLAR" not in markdown  # gerçek stratejiler mock değildir

    def test_rapor_en_kotu_bedelle_sayilan_cagrilari_acikca_belirtir(self, tmp_path, monkeypatch):
        install_llm(monkeypatch, lambda r: llm_ok_response(usage={}))
        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("0.1"))

        markdown, _ = build_report(run_dir)

        assert "bilinemeyen ücret için en kötü durum bedeli" in markdown
        assert "ücretsiz de sayılmadı" in markdown

    def test_rapor_ihlal_durdurmasini_ve_nedenini_gosterir(self, tmp_path, monkeypatch):
        huge = usage_block(input_tokens=5_000_000)
        install_llm(monkeypatch, lambda r: llm_ok_response(usage=huge))
        run_dir = do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=Decimal("100"))

        markdown, _ = build_report(run_dir)

        assert "gerçek ücret rezerve edilen üst sınırı aştı" in markdown
        assert "1 çağrıda gerçek ücret rezervasyonu aştı" in markdown

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
        assert (
            jev.worst_usd > jev.typical_low_usd * 3
        )  # rezervasyon üst sınırı tipik kestirimden geniş
        assert llm.typical_low_usd > jev.typical_low_usd  # LLM'in çıktısı ücretli, fiyatı yüksek
        assert hybrid.typical_low_usd == jev.typical_low_usd  # alt sınır: yalnızca Jev
        # Üst sınır: her örnekte Jev + TEK LLM çağrısı, ama yalnızca karar soruları (altı değil dört
        # soru) gider; bu yüzden altı soruluk llm_only'den ucuzdur.
        assert jev.typical_low_usd < hybrid.typical_high_usd
        assert hybrid.typical_high_usd < jev.typical_low_usd + llm.typical_low_usd
        assert hybrid.worst_usd < jev.worst_usd + llm.worst_usd
        assert hybrid.worst_usd > jev.worst_usd
        assert plan.worst_usd == sum(line.worst_usd for line in plan.lines)

    def test_en_kotu_durum_ve_en_kucuk_sinir_butce_korumasiyla_ayni_hesaptan_gelir(self):
        samples = [s for s in load_samples("v1") if s.split == "dev"]
        llm, _ = llm_provider(lambda r: llm_ok_response())
        per_sample = [3 * max_call_cost(llm, s.to_input()) for s in samples]

        plan = estimate_plan(samples, ("llm_only",))

        assert plan.lines[0].worst_usd == sum(per_sample)
        assert plan.min_cap_usd == max(per_sample)  # en pahalı örnek: bu sınırın altında başlanamaz

    def test_en_kucuk_sinir_birden_cok_stratejide_ayni_ornegin_toplamidir(self):
        samples = [s for s in load_samples("v1") if s.split == "dev"][:3]
        jev, _ = jev_provider(lambda r: jev_ok_response())
        llm, _ = llm_provider(lambda r: llm_ok_response())
        decision_questions = tuple(q for q in ALL_QUESTIONS if q in DECISION_QUESTIONS)
        expected = max(
            3 * max_call_cost(jev, s.to_input())  # jev_only
            + 3 * max_call_cost(llm, s.to_input())  # llm_only
            # hibrit: Jev tüm sorularla, LLM aşaması yalnızca karar sorularıyla
            + 3
            * (
                max_call_cost(jev, s.to_input())
                + max_call_cost(llm, s.to_input(), decision_questions)
            )
            for s in samples
        )

        plan = estimate_plan(samples, PLANNABLE)

        assert plan.min_cap_usd == expected

    def test_plan_cikti_en_kucuk_siniri_ve_garanti_edilemeyenleri_soyler(self):
        samples = [s for s in load_samples("v1") if s.split == "dev"][:3]

        text = format_plan(estimate_plan(samples, ("llm_only",)))

        assert "Harcama sınırı en az" in text and "başlanamaz" in text
        assert "Garanti edilemeyenler" in text and "fiyat tablosunun güncelliği" in text

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

    def test_cli_plan_limit_ilk_n_ornegi_planlar(self, capsys):
        assert main(["plan", "--splits", "dev", "--limit", "3", "--strategies", "llm_only"]) == 0

        assert "Örnek sayısı: 3" in capsys.readouterr().out


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
                "--budget-id",
                "cli-deneme",
                "--budget-dir",
                str(budget_dir_for(tmp_path)),
                "--out",
                str(tmp_path),
            ]
        )

        assert code == 2
        assert "kapalı" in capsys.readouterr().err
        assert not any(tmp_path.iterdir())

    def test_gecersiz_limit_acik_hata(self, tmp_path, capsys):
        code = main(["run", "--strategies", "rule_based", "--limit", "0", "--out", str(tmp_path)])

        assert code == 2 and "Örnek sınırı" in capsys.readouterr().err

    @pytest.mark.parametrize("value", ["abc", "0", "-1", "nan"])
    def test_gecersiz_sinir_reddedilir(self, value):
        with pytest.raises(SystemExit) as caught:
            main(["run", "--strategies", "llm_only", "--max-cost-usd", value])

        assert caught.value.code == 2
