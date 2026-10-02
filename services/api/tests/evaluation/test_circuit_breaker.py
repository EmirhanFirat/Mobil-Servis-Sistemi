"""Hızlı durdurma: sistematik hata bütçeyi boşuna yakmasın (yalnızca gerçek/bütçeli çalıştırmalar)."""

from decimal import Decimal

import httpx
import pytest

from app.evaluation.report import build_report
from tests.decision.test_llm_anthropic import ok_response as llm_ok_response
from tests.evaluation.test_live_guard import do_run, install_llm, predictions, run_json

CAP = Decimal("0.10")


def live(tmp_path, **kwargs):
    return do_run(
        tmp_path, strategy_names=("llm_only",), max_cost_usd=CAP, budget_id="kesici", **kwargs
    )


class TestFatalErrors:
    @pytest.mark.parametrize(
        ("code", "status"),
        [(401, "auth_error"), (403, "auth_error"), (400, "bad_request"), (413, "bad_request")],
    )
    def test_kalici_istemci_hatasi_ilk_istekte_calismayi_durdurur(
        self, tmp_path, monkeypatch, code, status
    ):
        build = install_llm(monkeypatch, lambda r: httpx.Response(code))

        record = run_json(live(tmp_path))

        assert len(build.requests) == 1  # yeniden denenmez, sonraki örneğe geçilmez
        assert record["stopped_early"]["reason"] == "provider_error"
        assert record["stopped_early"]["status"] == status
        assert record["stopped_early"]["provider"] == "anthropic"
        # Maliyeti bilinemeyen çağrı ücretsiz sayılmadı (en kötü bedel) ama yalnızca BİR çağrı.
        assert record["budget"]["calls"] == 1 and record["budget"]["conservative_charges"] == 1
        assert Decimal(record["budget"]["spent_usd"]) < Decimal("0.02")

    def test_durma_nedeni_raporda_acikca_yazilir(self, tmp_path, monkeypatch):
        install_llm(monkeypatch, lambda r: httpx.Response(401))
        run_dir = live(tmp_path)

        markdown, _ = build_report(run_dir)

        assert "anahtar veya istek hatası" in markdown
        assert "ÇALIŞTIRMA YARIDA KALDI" in markdown

    def test_kalici_hata_ucretsiz_stratejiyi_etkilemez_yarim_ornek_rapordan_cikar(
        self, tmp_path, monkeypatch
    ):
        install_llm(monkeypatch, lambda r: httpx.Response(401))

        run_dir = do_run(
            tmp_path,
            strategy_names=("rule_based", "llm_only"),
            max_cost_usd=CAP,
            budget_id="kesici",
        )

        record = run_json(run_dir)
        assert record["stopped_early"]["reason"] == "provider_error"
        assert record["stopped_early"]["samples_completed"] == 0  # yarım örnek sayılmadı
        _, metrics = build_report(run_dir)
        assert metrics["splits"]["dev"]["llm_only"]["n"] == 0  # yarım örnek rapor dışı


class TestConsecutiveFailures:
    def test_ardisik_iki_basarisiz_karar_calismayi_durdurur(self, tmp_path, monkeypatch):
        build = install_llm(monkeypatch, lambda r: httpx.Response(529))

        record = run_json(live(tmp_path))

        assert record["stopped_early"]["reason"] == "provider_unavailable"
        assert len(build.requests) == 6  # 2 karar × 3 deneme; üçüncü örneğe geçilmedi
        assert len(predictions(tmp_path / record["run_id"])) == 2

    def test_arada_basari_sayaci_sifirlar_calisma_surer(self, tmp_path, monkeypatch):
        # örnek 1: 3 × 529 (başarısız karar), örnek 2: başarılı, örnek 3: 3 × 529, örnek 4: başarılı
        pattern = iter(
            [httpx.Response(529)] * 3
            + [llm_ok_response()]
            + [httpx.Response(529)] * 3
            + [llm_ok_response()]
        )
        install_llm(monkeypatch, lambda r: next(pattern))

        record = run_json(live(tmp_path, limit=4))

        assert record["stopped_early"] is None  # hiçbir zaman İKİ ardışık başarısızlık olmadı
        assert record["dataset"]["n_samples_completed"] == 4

    def test_gecici_hatalar_sonrasi_basari_ilerler(self, tmp_path, monkeypatch):
        pattern = iter([httpx.Response(529), httpx.Response(529), llm_ok_response()] * 3)
        install_llm(monkeypatch, lambda r: next(pattern))

        record = run_json(live(tmp_path, limit=3))

        assert record["stopped_early"] is None and record["dataset"]["n_samples_completed"] == 3

    def test_basarili_cagrilarda_kesici_tetiklenmez(self, tmp_path, monkeypatch):
        install_llm(monkeypatch, lambda r: llm_ok_response())

        record = run_json(live(tmp_path))

        assert record["stopped_early"] is None


class TestFreeRunsUnaffected:
    def test_ucretsiz_calistirmada_kesici_yok_tum_ornekler_denenir(self, tmp_path, monkeypatch):
        from app.decision.contract import DecisionUnavailable, StrategyName
        from app.evaluation.runner import STRATEGY_BUILDERS

        class Failing:
            name = StrategyName.RULE_BASED

            def decide(self, data):
                raise DecisionUnavailable("hep başarısız")

        monkeypatch.setitem(STRATEGY_BUILDERS, "rule_based", Failing)

        record = run_json(do_run(tmp_path, strategy_names=("rule_based",), budget_id=None))

        assert record["stopped_early"] is None and record["dataset"]["n_samples_completed"] == 21
