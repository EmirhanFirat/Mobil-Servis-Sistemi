"""Bütçenin süreçler/çalıştırmalar arası KALICILIĞI: aynı bütçe kimliği = tek toplam sınır."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest

from app.decision.budget_ledger import BudgetLedger, LedgerCapMismatch, LedgerLocked
from app.evaluation.cli import main
from app.evaluation.report import build_report
from app.evaluation.runner import LIVE_STRATEGY_BUILDERS, LiveRunGuard, ledger_path
from tests.decision.test_llm_anthropic import ok_response as llm_ok_response
from tests.evaluation.test_live_guard import (
    FIXED_NOW,
    LLM_CALL_COST,
    budget_dir_for,
    do_run,
    install_llm,
    run_json,
)

CAP = Decimal("0.10")
BID = "ilk-deneme"


def run(tmp_path, offset_minutes, **kwargs):
    """Aynı bütçe kimliğiyle ardışık 'süreç' (her biri ayrı run_id ve ayrı defter açılışı)."""
    return do_run(
        tmp_path,
        strategy_names=("llm_only",),
        max_cost_usd=kwargs.pop("max_cost_usd", CAP),
        budget_id=BID,
        now=lambda: FIXED_NOW + timedelta(minutes=offset_minutes),
        **kwargs,
    )


def ledger_dir(tmp_path):
    return budget_dir_for(tmp_path)


class TestAcrossRuns:
    def test_ikinci_calisma_oncekinin_harcamasini_dusmeden_yeni_butce_acmaz(
        self, tmp_path, monkeypatch
    ):
        # Başarılı ama kullanımı bildirilmeyen yanıtlar: her çağrı en kötü bedelle sayılır → bütçe
        # hızla tükenir (başarısızlık sayılmadığı için devre kesici devreye girmez).
        build = install_llm(monkeypatch, lambda r: llm_ok_response(usage={}))
        first = run_json(run(tmp_path, 0))
        sent_by_first = len(build.requests)

        second = run_json(run(tmp_path, 1))

        assert first["stopped_early"]["reason"] == "budget" and sent_by_first > 0
        assert second["budget"]["prior_spent_usd"] == first["budget"]["spent_usd"]
        total = Decimal(first["budget"]["spent_usd"]) + Decimal(second["budget"]["spent_usd"])
        assert total <= CAP  # İKİ çalıştırmanın toplamı sınırı aşmaz
        assert Decimal(second["budget"]["remaining_usd"]) < CAP
        assert len(build.requests) <= sent_by_first + 3  # kalan bütçeyle en fazla birkaç istek
        # Yeni 0,10 USD açılsaydı ikinci çalıştırma da birincisi kadar harcardı.
        assert Decimal(second["budget"]["spent_usd"]) < Decimal(first["budget"]["spent_usd"])

    def test_butce_bitmisse_ikinci_calisma_hicbir_istek_gondermez_sonuclari_kaydedip_durur(
        self, tmp_path, monkeypatch
    ):
        build = install_llm(monkeypatch, lambda r: llm_ok_response(usage={}))
        for minute in range(4):  # defteri tüket
            run(tmp_path, minute)
        sent_before = len(build.requests)

        record = run_json(run(tmp_path, 10))

        assert len(build.requests) == sent_before  # ikinci/üçüncü açılışta tek istek yok
        assert record["stopped_early"]["reason"] == "budget"
        assert record["stopped_early"]["samples_completed"] == 0
        total = BudgetLedger.read(ledger_path(BID, ledger_dir(tmp_path))).status()
        assert Decimal(total["settled_total_usd"]) <= CAP and Decimal(total["remaining_usd"]) >= 0

    def test_kalan_butceyle_devam_eder_defter_toplami_iki_calismanin_toplamidir(
        self, tmp_path, monkeypatch
    ):
        install_llm(monkeypatch, lambda r: llm_ok_response())
        first = run_json(run(tmp_path, 0, limit=2))

        second = run_json(run(tmp_path, 1, limit=3))

        assert Decimal(first["budget"]["spent_usd"]) == LLM_CALL_COST * 2
        assert second["budget"]["prior_spent_usd"] == first["budget"]["spent_usd"]
        assert Decimal(second["budget"]["total_spent_usd"]) == LLM_CALL_COST * 5
        assert second["stopped_early"] is None

    def test_farkli_sinirla_yeniden_calistirma_reddedilir_ve_hicbir_cikti_yazilmaz(
        self, tmp_path, monkeypatch
    ):
        install_llm(monkeypatch, lambda r: llm_ok_response())
        run(tmp_path, 0, limit=1)
        before = sorted(p.name for p in tmp_path.iterdir())

        with pytest.raises(LedgerCapMismatch, match="kendiliğinden değiştirilmez"):
            run(tmp_path, 1, max_cost_usd=Decimal("0.50"), limit=1)

        assert sorted(p.name for p in tmp_path.iterdir()) == before  # yeni çıktı klasörü yok
        assert not ledger_path(BID, ledger_dir(tmp_path)).with_suffix(".lock").exists()

    def test_cozulmemis_rezervasyon_sonraki_calismada_dusulur_ve_gercek_harcamadan_ayri_raporlanir(
        self, tmp_path, monkeypatch
    ):
        # Önceki süreç bir çağrıyı rezerve etti, istek gitti, süreç ÇÖKTÜ (settle yok).
        crashed = BudgetLedger.open(ledger_path(BID, ledger_dir(tmp_path)), budget_id=BID, cap=CAP)
        crashed.begin("onceki-kosu", "anthropic", "claude-haiku-4-5-20251001", Decimal("0.04"))
        ledger_path(BID, ledger_dir(tmp_path)).with_suffix(".lock").unlink()
        install_llm(monkeypatch, lambda r: llm_ok_response())

        record = run_json(run(tmp_path, 0, limit=3))

        budget = record["budget"]
        assert budget["prior_unresolved_reserved_usd"] == "0.04"
        assert budget["prior_spent_usd"] == "0"  # çözülmemiş, gerçek harcama DEĞİL
        assert Decimal(budget["spent_usd"]) == LLM_CALL_COST * 3  # bu çalıştırmanın gerçek ücreti
        assert Decimal(budget["remaining_usd"]) == CAP - Decimal("0.04") - LLM_CALL_COST * 3
        markdown, _ = build_report(tmp_path / record["run_id"])
        assert "çözülmemiş rezervasyon" in markdown and "0,040000 USD" in markdown

    def test_cozulmemis_rezervasyon_butceyi_kuculttugu_icin_calisma_daha_erken_durur(
        self, tmp_path, monkeypatch
    ):
        crashed = BudgetLedger.open(ledger_path(BID, ledger_dir(tmp_path)), budget_id=BID, cap=CAP)
        crashed.begin("onceki-kosu", "anthropic", "m", Decimal("0.095"))
        ledger_path(BID, ledger_dir(tmp_path)).with_suffix(".lock").unlink()
        build = install_llm(monkeypatch, lambda r: llm_ok_response())

        record = run_json(run(tmp_path, 0))

        assert build.requests == [] and record["stopped_early"]["reason"] == "budget"

    def test_kilit_kalmissa_calisma_reddedilir_ve_cikti_yazilmaz(self, tmp_path, monkeypatch):
        install_llm(monkeypatch, lambda r: llm_ok_response())
        BudgetLedger.open(ledger_path(BID, ledger_dir(tmp_path)), budget_id=BID, cap=CAP)  # açık

        with pytest.raises(LedgerLocked):
            run(tmp_path, 0, limit=1)

        assert not any(tmp_path.iterdir())

    def test_kilit_calisma_bitince_ve_hata_olsa_da_birakilir(self, tmp_path, monkeypatch):
        install_llm(monkeypatch, lambda r: llm_ok_response())
        run(tmp_path, 0, limit=1)
        lock = ledger_path(BID, ledger_dir(tmp_path)).with_suffix(".lock")
        assert not lock.exists()

        def explode(request):
            raise RuntimeError("beklenmeyen")

        install_llm(monkeypatch, explode)
        with pytest.raises(RuntimeError):
            run(tmp_path, 1, limit=1)

        assert not lock.exists()

    def test_rezervasyon_istek_gonderilmeden_once_diske_yazilmistir(self, tmp_path, monkeypatch):
        seen_states = []

        def handler(request):
            rows = json.loads(ledger_path(BID, ledger_dir(tmp_path)).read_text(encoding="utf-8"))
            seen_states.append([e["state"] for e in rows["entries"]])
            return llm_ok_response()

        install_llm(monkeypatch, handler)

        run(tmp_path, 0, limit=2)

        assert seen_states == [["pending"], ["settled", "pending"]]  # istek anında kayıt zaten var

    def test_defter_gercek_ve_en_kotu_bedelli_kalemleri_ayri_isaretler(self, tmp_path, monkeypatch):
        responses = iter([llm_ok_response(), llm_ok_response(usage={})])
        install_llm(monkeypatch, lambda r: next(responses))

        run(tmp_path, 0, limit=2)

        status = BudgetLedger.read(ledger_path(BID, ledger_dir(tmp_path))).status()
        assert Decimal(status["settled_known_usd"]) == LLM_CALL_COST
        assert Decimal(status["settled_conservative_usd"]) > LLM_CALL_COST  # en kötü bedel
        assert status["pending_entries"] == 0

    def test_defterde_cikti_dosyasinda_ve_raporda_anahtar_yok(self, tmp_path, monkeypatch):
        from tests.decision.test_llm_anthropic import KEY

        install_llm(monkeypatch, lambda r: llm_ok_response())
        record = run_json(run(tmp_path, 0, limit=2))

        files = list(ledger_dir(tmp_path).iterdir()) + list((tmp_path / record["run_id"]).iterdir())
        for path in files:
            assert KEY not in path.read_text(encoding="utf-8")


class TestBudgetId:
    def test_gercek_calistirma_butce_kimligi_olmadan_calismaz(self, tmp_path, monkeypatch):
        def must_not_build(_settings):
            raise AssertionError("kimlik yokken strateji kurulmamalı")

        monkeypatch.setitem(LIVE_STRATEGY_BUILDERS, "llm_only", must_not_build)

        with pytest.raises(LiveRunGuard, match="--budget-id"):
            do_run(
                tmp_path,
                strategy_names=("llm_only",),
                max_cost_usd=CAP,
                budget_id=None,
            )

        assert not any(tmp_path.iterdir())

    @pytest.mark.parametrize("bad", ["../kacis", "a/b", "a b", "", "x" * 61])
    def test_gecersiz_butce_kimligi_reddedilir(self, tmp_path, bad):
        with pytest.raises((ValueError, LiveRunGuard)):
            do_run(tmp_path, strategy_names=("llm_only",), max_cost_usd=CAP, budget_id=bad)

        assert not any(tmp_path.iterdir())

    @pytest.mark.parametrize("bad", ["../kacis", "a/b", "a\b", "", "x" * 61, None])
    def test_defter_yolu_gecersiz_kimlikle_hic_uretilmez(self, tmp_path, bad):
        with pytest.raises(ValueError, match="bütçe kimliği"):
            ledger_path(bad, tmp_path)

    def test_ucretsiz_stratejiler_butce_defteri_olusturmaz(self, tmp_path):
        do_run(tmp_path, strategy_names=("rule_based", "mock_jev"), budget_id=None)

        assert not ledger_dir(tmp_path).exists()


class TestBudgetCli:
    def test_butce_komutu_defter_durumunu_gosterir(self, tmp_path, monkeypatch, capsys):
        install_llm(monkeypatch, lambda r: llm_ok_response())
        run(tmp_path, 0, limit=2)

        code = main(["budget", "--budget-id", BID, "--budget-dir", str(ledger_dir(tmp_path))])

        out = capsys.readouterr().out
        assert code == 0 and f"budget_id: {BID}" in out and "cap_usd: 0.10" in out
        assert "settled_known_usd: 0.0038" in out and "remaining_usd:" in out

    def test_olmayan_defter_acik_hata(self, tmp_path, capsys):
        code = main(["budget", "--budget-id", "yok", "--budget-dir", str(tmp_path)])

        assert code == 2 and "yok" in capsys.readouterr().err

    def test_run_komutu_butce_kimligi_olmadan_acik_hata(self, tmp_path, capsys, monkeypatch):
        from app.evaluation import runner
        from tests.evaluation.test_live_guard import live_settings

        monkeypatch.setattr(runner, "get_settings", lambda: live_settings())

        code = main(
            ["run", "--strategies", "llm_only", "--max-cost-usd", "0.1", "--out", str(tmp_path)]
        )

        assert code == 2 and "--budget-id" in capsys.readouterr().err
        assert not any(tmp_path.iterdir())

    def test_run_komutu_farkli_sinirla_acik_hata(self, tmp_path, capsys, monkeypatch):
        from app.evaluation import runner
        from tests.evaluation.test_live_guard import live_settings

        monkeypatch.setattr(runner, "get_settings", lambda: live_settings())
        BudgetLedger.open(
            ledger_path("cli", ledger_dir(tmp_path)), budget_id="cli", cap=CAP
        ).release()

        code = main(
            [
                "run",
                "--strategies",
                "llm_only",
                "--max-cost-usd",
                "0.5",
                "--budget-id",
                "cli",
                "--budget-dir",
                str(ledger_dir(tmp_path)),
                "--out",
                str(tmp_path),
            ]
        )

        assert code == 2 and "kendiliğinden değiştirilmez" in capsys.readouterr().err
        assert not any(tmp_path.iterdir())
