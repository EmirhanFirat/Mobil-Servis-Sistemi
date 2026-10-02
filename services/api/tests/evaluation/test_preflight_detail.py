from datetime import timedelta
from decimal import Decimal

import httpx
import pytest

from app.config import Settings
from app.decision.budget_ledger import BudgetLedger
from app.evaluation import cli as cli_module
from app.evaluation.cli import main
from app.evaluation.detail import build_detail
from app.evaluation.preflight import build_preflight
from app.evaluation.report import build_report
from app.evaluation.runner import ledger_path
from tests.decision.test_llm_anthropic import KEY, usage_block
from tests.decision.test_llm_anthropic import ok_response as llm_ok_response
from tests.evaluation.test_live_guard import (
    FIXED_NOW,
    LLM_CALL_COST,
    budget_dir_for,
    do_run,
    install_llm,
    live_settings,
)

CAP = Decimal("0.10")
JEV_KEY = "SIR-JEV-ANAHTAR-456"


def preflight(tmp_path, settings=None, **overrides):
    args = dict(
        settings=settings or live_settings(),
        version="v1",
        splits=("dev",),
        strategies=("jev_only", "llm_only", "hybrid"),
        max_cost_usd=CAP,
        budget_id="ilk-deneme",
        budget_dir=budget_dir_for(tmp_path),
        shuffle_seed=4,
        limit=5,
    )
    return build_preflight(**{**args, **overrides})


class TestPreflight:
    def test_hazir_oldugunda_anahtar_degerleri_asla_yazdirilmaz(self, tmp_path):
        text, ready = preflight(tmp_path)

        assert ready and "SONUÇ: HAZIR" in text
        assert KEY not in text and JEV_KEY not in text
        assert "TALEPAKIS_ANTHROPIC_API_KEY: tanımlı" in text
        assert "TALEPAKIS_JEV_API_KEY: tanımlı" in text
        assert "TALEPAKIS_PAID_MODEL_CALLS_ENABLED: açık" in text

    def test_eksik_anahtar_ve_kapali_bayrak_acikca_listelenir(self, tmp_path):
        settings = Settings(_env_file=None)  # hiçbir şey tanımlı değil

        text, ready = preflight(tmp_path, settings)

        assert not ready and "SONUÇ: EKSİK" in text
        assert "TANIMSIZ" in text and "KAPALI" in text
        for name in (
            "TALEPAKIS_ANTHROPIC_API_KEY",
            "TALEPAKIS_JEV_API_KEY",
            "TALEPAKIS_PAID_MODEL_CALLS_ENABLED=true",
        ):
            assert name in text.split("SONUÇ: EKSİK")[1]

    def test_yalniz_istenen_stratejilerin_anahtarlari_istenir(self, tmp_path):
        settings = Settings(_env_file=None, paid_model_calls_enabled=True, jev_api_key=JEV_KEY)

        text, ready = preflight(tmp_path, settings, strategies=("jev_only",))

        assert ready and "ANTHROPIC" not in text.split("Model ve fiyatlar")[0]

    def test_secilen_ornekler_modeller_fiyatlar_plan_ve_komut_gosterilir(self, tmp_path):
        text, _ = preflight(tmp_path)

        assert "Seçilen örnekler (5; bölüm: dev)" in text
        assert text.count("\n- s0") >= 5
        assert "jev-1.13.0" in text and "claude-haiku-4-5-20251001" in text
        assert "girdi 0.042" in text and "çıktı 5" in text and "2026-10-02" in text
        assert "YAKLAŞIK TAHMİN" in text and "Harcama sınırı en az" in text
        assert (
            "python -m app.evaluation run --splits dev --shuffle-seed 4 --limit 5 "
            "--strategies jev_only,llm_only,hybrid --max-cost-usd 0.10 --budget-id ilk-deneme"
        ) in text

    def test_nihai_test_bolumu_bu_denemede_kullanilamaz(self, tmp_path):
        text, ready = preflight(tmp_path, splits=("dev", "test"))

        assert not ready and "nihai test bölümü" in text

    def test_ayarli_model_fiyat_tablosunda_yoksa_hazir_degil(self, tmp_path):
        settings = live_settings(anthropic_model="claude-haiku-4-6")

        text, ready = preflight(tmp_path, settings)

        assert not ready and "FİYAT TABLOSUNDA YOK" in text

    def test_defter_yoksa_ilk_calistirmada_acilacagini_soyler(self, tmp_path):
        text, _ = preflight(tmp_path)

        assert "henüz yok; ilk çalıştırmada 0.10 USD ile açılır" in text

    def test_defter_varsa_onceki_harcama_ve_cozulmemis_rezervasyon_dusulmus_kalan_gosterilir(
        self, tmp_path
    ):
        path = ledger_path("ilk-deneme", budget_dir_for(tmp_path))
        ledger = BudgetLedger.open(path, budget_id="ilk-deneme", cap=CAP)
        done = ledger.begin("k", "anthropic", "m", Decimal("0.02"))
        ledger.settle(done, Decimal("0.003"), known=True)
        ledger.begin("k", "jev", "m", Decimal("0.01"))  # çözülmemiş
        ledger.release()

        text, ready = preflight(tmp_path)

        assert ready
        assert "kesinleşmiş harcama 0.003 (gerçek 0.003" in text
        assert "çözülmemiş rezervasyon 0.01" in text and "KALAN 0.087 USD" in text

    def test_defter_baska_sinirla_acilmissa_hazir_degil(self, tmp_path):
        path = ledger_path("ilk-deneme", budget_dir_for(tmp_path))
        BudgetLedger.open(path, budget_id="ilk-deneme", cap=Decimal("0.50")).release()

        text, ready = preflight(tmp_path)

        assert not ready and "defterdeki sınırdan (0.50) farklı" in text

    def test_bütce_bitmisse_hazir_degil(self, tmp_path):
        path = ledger_path("ilk-deneme", budget_dir_for(tmp_path))
        ledger = BudgetLedger.open(path, budget_id="ilk-deneme", cap=CAP)
        seq = ledger.begin("k", "anthropic", "m", CAP)
        ledger.settle(seq, CAP, known=False)
        ledger.release()

        text, ready = preflight(tmp_path)

        assert not ready and "kalan bütçe yok" in text

    def test_kilit_dosyasi_varsa_uyarir(self, tmp_path):
        path = ledger_path("ilk-deneme", budget_dir_for(tmp_path))
        BudgetLedger.open(path, budget_id="ilk-deneme", cap=CAP)  # kilit açık kalır

        text, ready = preflight(tmp_path)

        assert not ready and "kilit" in text.lower()

    def test_cli_cikis_kodu_hazirsa_0_degilse_3_ve_ag_istegi_yok(
        self, tmp_path, monkeypatch, capsys
    ):
        def no_network(self, request):
            raise AssertionError("ön kontrol ağ isteği yapmamalı")

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
        argv = [
            "preflight",
            "--splits",
            "dev",
            "--shuffle-seed",
            "4",
            "--limit",
            "5",
            "--max-cost-usd",
            "0.10",
            "--budget-id",
            "ilk-deneme",
            "--budget-dir",
            str(budget_dir_for(tmp_path)),
        ]
        monkeypatch.setattr(cli_module, "get_settings", lambda: live_settings())
        assert main(argv) == 0
        assert "SONUÇ: HAZIR" in capsys.readouterr().out

        monkeypatch.setattr(cli_module, "get_settings", lambda: Settings(_env_file=None))
        assert main(argv) == 3
        assert "SONUÇ: EKSİK" in capsys.readouterr().out


class TestDetail:
    def run_live(self, tmp_path, monkeypatch, handler, limit=2, **kwargs):
        install_llm(monkeypatch, handler)
        return do_run(
            tmp_path,
            strategy_names=("rule_based", "llm_only"),
            max_cost_usd=CAP,
            budget_id="ayrinti",
            limit=limit,
            **kwargs,
        )

    def test_her_ornek_icin_beklenen_etiket_tahmin_token_sure_retry_ve_ucret_gosterilir(
        self, tmp_path, monkeypatch
    ):
        run_dir = self.run_live(tmp_path, monkeypatch, lambda r: llm_ok_response())

        text = build_detail(run_dir)

        assert "### s001 — Lavabo akıtıyor" in text
        assert "**Beklenen etiket:** kategori `plumbing`, öncelik `high`" in text
        assert "| `llm_only` | `plumbing` ✓ | `high` ✓" in text  # tahmin + etiketle eşleşme
        assert "| 1 / 0 | 1100 | 160 | 0,001900 | 0 |" in text  # çağrı/retry, token, ücret
        assert "anthropic / claude-haiku-4-5-20251001" in text and "req_011abc" in text
        assert "| `rule_based` |" in text  # kurallı taban: çağrı yok
        assert "Birkaç örnekten genel doğruluk" in text

    def test_basarisiz_cagri_retry_sayisi_bildirilmeyen_token_ve_bilinmeyen_ucretle_gorunur(
        self, tmp_path, monkeypatch
    ):
        run_dir = self.run_live(tmp_path, monkeypatch, lambda r: httpx.Response(529), limit=1)

        text = build_detail(run_dir)

        assert "**BAŞARISIZ**" in text
        assert "| 3 / 3 | bildirilmedi | bildirilmedi | — | 3 |" in text  # 3 deneme, 3 retry
        assert "unavailable" in text  # çağrı kayıtları

    def test_kullanimi_bildirilmeyen_basarili_cagri_sifir_sayilmaz(self, tmp_path, monkeypatch):
        run_dir = self.run_live(tmp_path, monkeypatch, lambda r: llm_ok_response(usage={}), limit=1)

        text = build_detail(run_dir)

        assert "| 1 / 0 | bildirilmedi | bildirilmedi | — | 1 |" in text
        assert "bilinmiyor" in text

    def test_yanlis_tahmin_capraz_isaretle_gorunur(self, tmp_path, monkeypatch):
        wrong = {
            "category": {"answer": "electrical", "confidence": 0.9},
            "priority": {"answer": "low", "confidence": 0.9},
            "missing_location": {"answer": False, "confidence": 0.9},
            "missing_detail": {"answer": False, "confidence": 0.9},
            "missing_contact": {"answer": False, "confidence": 0.9},
            "missing_timing": {"answer": False, "confidence": 0.9},
        }
        run_dir = self.run_live(tmp_path, monkeypatch, lambda r: llm_ok_response(wrong), limit=1)

        text = build_detail(run_dir)

        assert "`electrical` ✗" in text and "`low` ✗" in text

    def test_kismen_tamamlanan_cagrida_eksik_token_isaretlenir(self, tmp_path, monkeypatch):
        responses = iter([llm_ok_response(usage=usage_block()), llm_ok_response(usage={})])
        run_dir = self.run_live(tmp_path, monkeypatch, lambda r: next(responses), limit=2)

        text = build_detail(run_dir)

        assert "1100 | 160 |" in text and "bildirilmedi |" in text

    def test_rapor_kucuk_calistirmalarda_ayrinti_ve_kucuk_orneklem_uyarisi_icerir(
        self, tmp_path, monkeypatch
    ):
        run_dir = self.run_live(tmp_path, monkeypatch, lambda r: llm_ok_response(), limit=3)

        markdown, _ = build_report(run_dir)

        assert "KÜÇÜK ÖRNEKLEM (3 örnek)" in markdown
        assert "Doğruluk, güvenilirlik veya maliyet tasarrufu sonucu çıkarılamaz" in markdown
        assert "## Örnek bazında ayrıntı" in markdown
        assert "bilinen ücret" in markdown.lower()

    def test_rapor_buyuk_calistirmada_ayrinti_bolumunu_eklemez(self, tmp_path):
        run_dir = do_run(
            tmp_path, strategy_names=("rule_based",), now=lambda: FIXED_NOW + timedelta(hours=1)
        )

        markdown, _ = build_report(run_dir)  # dev = 21 örnek > 20

        assert "## Örnek bazında ayrıntı" not in markdown

    def test_cli_detail_komutu_model_cagirmadan_yazdirir(self, tmp_path, monkeypatch, capsys):
        run_dir = self.run_live(tmp_path, monkeypatch, lambda r: llm_ok_response(), limit=1)

        def no_network(self, request):
            raise AssertionError("detail ağ isteği yapmamalı")

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)

        assert main(["detail", "--run", str(run_dir)]) == 0

        assert "Örnek bazında ayrıntı" in capsys.readouterr().out

    def test_ayrinti_bildirilen_ucreti_toplam_ile_tutarli_gosterir(self, tmp_path, monkeypatch):
        run_dir = self.run_live(tmp_path, monkeypatch, lambda r: llm_ok_response(), limit=2)

        text = build_detail(run_dir)

        assert text.count("0,001900") >= 2  # iki örnek × 1 çağrı
        assert LLM_CALL_COST == Decimal("0.0019")
        assert "gizli" not in text.lower() and KEY not in text


@pytest.mark.parametrize("limit", [1, 3])
def test_ayrinti_her_limitte_uretilir(tmp_path, monkeypatch, limit):
    install_llm(monkeypatch, lambda r: llm_ok_response())
    run_dir = do_run(
        tmp_path,
        strategy_names=("llm_only",),
        max_cost_usd=CAP,
        budget_id="her-limit",
        limit=limit,
    )

    assert build_detail(run_dir).count("\n### s0") == limit
