import json
import random
from dataclasses import replace
from decimal import Decimal

import httpx
import pytest

from app.decision.budget import (
    SAFETY_SLACK_TOKENS,
    BudgetedProvider,
    BudgetGuard,
    max_call_cost,
    worst_decision_cost,
)
from app.decision.contract import (
    ALL_QUESTIONS,
    BudgetExhausted,
    CallStatus,
    Question,
    StrategyName,
)
from app.decision.llm_anthropic import MAX_TOKENS, AnthropicProvider
from app.decision.pricing import CLAUDE_HAIKU_4_5, JEV_1_13
from app.decision.providers import ProviderError
from app.decision.retry import RetryPolicy, classify_with_retry
from app.decision.rule_based import RuleBasedStrategy
from app.decision.strategies import HybridStrategy, HybridThresholds, ProviderStrategy
from app.evaluation.dataset import load_samples
from tests.decision.conftest import make_input
from tests.decision.test_jev import ok_response as jev_ok_response
from tests.decision.test_jev import provider as jev_provider
from tests.decision.test_llm_anthropic import DATA, usage_block
from tests.decision.test_llm_anthropic import ok_response as llm_ok_response
from tests.decision.test_llm_anthropic import provider as llm_provider

LLM_ACTUAL = Decimal("0.0019")  # test yanıtı: 1100 girdi + 160 çıktı token'ı
NO_WAIT = RetryPolicy()
S = StrategyName.LLM_ONLY


def reservation(provider, data=DATA) -> Decimal:
    return max_call_cost(provider, data)


class TestMaxCallCost:
    def test_anthropic_ust_siniri_bayt_sayisi_sabit_ek_pay_ve_cikti_tavanindan_hesaplanir(self):
        llm, _ = llm_provider(lambda r: llm_ok_response())
        body_bytes = len(
            json.dumps(llm.build_request(DATA, ALL_QUESTIONS), ensure_ascii=False).encode("utf-8")
        )

        cost = max_call_cost(llm, DATA)

        tokens = body_bytes + 588 + SAFETY_SLACK_TOKENS  # zorunlu araç çağrısı ek token'ları
        expected = (
            Decimal(tokens) / 1_000_000 * CLAUDE_HAIKU_4_5.input_usd_per_mtok
            + Decimal(MAX_TOKENS) / 1_000_000 * CLAUDE_HAIKU_4_5.output_usd_per_mtok
        )
        assert cost == expected

    def test_jev_ciktisi_ucretsiz_oldugu_icin_yalniz_girdi_sayilir(self):
        jev, _ = jev_provider(lambda r: jev_ok_response())
        body_bytes = len(
            json.dumps(jev.build_request(DATA, ALL_QUESTIONS), ensure_ascii=False).encode("utf-8")
        )

        cost = max_call_cost(jev, DATA)

        assert cost == Decimal(body_bytes + SAFETY_SLACK_TOKENS) / 1_000_000 * (
            JEV_1_13.input_usd_per_mtok
        )

    def test_turkce_karakterler_bayt_olarak_sayilir_karakter_olarak_degil(self):
        llm, _ = llm_provider(lambda r: llm_ok_response())
        ascii_text = make_input("a" * 500, "a" * 500)
        turkish_text = make_input("ş" * 500, "ş" * 500)  # aynı karakter sayısı, 2 kat bayt

        assert max_call_cost(llm, turkish_text) > max_call_cost(llm, ascii_text)

    def test_ust_sinir_tipik_gercek_ucretten_buyuktur_tum_veri_setinde(self):
        llm, _ = llm_provider(lambda r: llm_ok_response())
        jev, _ = jev_provider(lambda r: jev_ok_response())
        for sample in load_samples("v1"):
            data = sample.to_input()
            # Gerçekçi bir yanıtın (1100/160 token) ücretinden büyük olmalı; aksi hâlde rezervasyon
            # çağrıyı korumaz.
            assert max_call_cost(llm, data) > LLM_ACTUAL
            assert max_call_cost(jev, data) > Decimal("0.000016464")

    def test_fiyat_bilinmiyorsa_ucret_sinirlanamaz_cagri_yapilamaz(self):
        llm, _ = llm_provider(lambda r: llm_ok_response(), price=None)

        with pytest.raises(BudgetExhausted, match="fiyat bilinmiyor"):
            max_call_cost(llm, DATA)

    def test_cikti_ucreti_varsa_ama_cikti_tavani_bilinmiyorsa_cagri_yapilamaz(self):
        jev, _ = jev_provider(lambda r: jev_ok_response())
        jev.price = replace(JEV_1_13, output_usd_per_mtok=Decimal(1))

        with pytest.raises(BudgetExhausted, match="çıktı token üst sınırı"):
            max_call_cost(jev, DATA)

    def test_en_kotu_karar_ucreti_deneme_hakkiyla_carpilir_hibritte_iki_asama_toplanir(self):
        llm, _ = llm_provider(lambda r: llm_ok_response())
        jev, _ = jev_provider(lambda r: jev_ok_response())
        only = ProviderStrategy(S, llm, RetryPolicy(max_attempts=3))
        hybrid = HybridStrategy(jev, llm, HybridThresholds(), RetryPolicy(max_attempts=2))

        assert worst_decision_cost(only, DATA) == 3 * max_call_cost(llm, DATA)
        assert worst_decision_cost(hybrid, DATA) == 2 * (
            max_call_cost(jev, DATA) + max_call_cost(llm, DATA)
        )
        assert worst_decision_cost(RuleBasedStrategy(), DATA) == 0

    def test_sarmalanmis_saglayicida_da_ayni_sinir_hesaplanir(self):
        llm, _ = llm_provider(lambda r: llm_ok_response())
        wrapped = BudgetedProvider(llm, BudgetGuard(Decimal(1)))

        assert max_call_cost(wrapped, DATA) == max_call_cost(llm, DATA)


class TestBudgetGuard:
    def test_rezervasyon_ve_kapanis_aritmetigi(self):
        guard = BudgetGuard(Decimal("1"))

        guard.reserve(Decimal("0.4"))
        assert guard.remaining() == Decimal("0.6")
        with pytest.raises(BudgetExhausted):
            guard.reserve(Decimal("0.7"))  # sığmaz
        guard.settle(Decimal("0.4"), Decimal("0.1"))

        assert guard.reserved == 0 and guard.spent == Decimal("0.1")
        assert guard.known_spent == Decimal("0.1") and guard.conservative_charges == 0
        assert guard.remaining() == Decimal("0.9")

    def test_bilinmeyen_ucret_sifir_sayilmaz_rezerve_edilen_en_kotu_bedel_yazilir(self):
        guard = BudgetGuard(Decimal("1"))
        guard.reserve(Decimal("0.3"))

        guard.settle(Decimal("0.3"), None)

        assert guard.spent == Decimal("0.3") and guard.known_spent == 0
        assert guard.conservative_charges == 1 and guard.remaining() == Decimal("0.7")

    def test_gercek_ucret_rezervasyonu_asarsa_ihlal_sayilir_ve_gercek_ucret_yazilir(self):
        guard = BudgetGuard(Decimal("1"))
        guard.reserve(Decimal("0.1"))

        guard.settle(Decimal("0.1"), Decimal("0.5"))

        assert guard.bound_violations == 1 and guard.spent == Decimal("0.5")

    def test_sinira_tam_esitlik_kabul_edilir_bir_kurus_fazlasi_edilmez(self):
        guard = BudgetGuard(Decimal("1"))

        guard.reserve(Decimal("1"))
        with pytest.raises(BudgetExhausted):
            guard.reserve(Decimal("0.0000001"))

    def test_rastgele_cagri_dizisinde_harcanan_artı_rezerve_siniri_asmaz(self):
        rng = random.Random(7)
        guard = BudgetGuard(Decimal("1"))
        for _ in range(500):
            amount = Decimal(rng.randint(1, 300)) / 1000
            try:
                guard.reserve(amount)
            except BudgetExhausted:
                continue
            assert guard.spent + guard.reserved <= guard.cap
            # Gerçek ücret rezervasyonun altında; bazen bilinmiyor (en kötü bedel).
            actual = None if rng.random() < 0.3 else amount / rng.randint(2, 6)
            guard.settle(amount, actual)
            assert guard.spent + guard.reserved <= guard.cap
        assert guard.bound_violations == 0 and guard.reserved == 0

    def test_ozet_kayda_yazilacak_alanlari_icerir(self):
        guard = BudgetGuard(Decimal("2"))
        guard.reserve(Decimal("0.5"))
        guard.settle(Decimal("0.5"), None)

        assert guard.summary() == {
            "max_cost_usd": "2",
            "spent_usd": "0.5",
            "known_spent_usd": "0",
            "conservative_charges": 1,
            "bound_violations": 0,
            "calls": 1,
        }


def budgeted(handler, cap, **kwargs):
    llm, seen = llm_provider(handler, **kwargs)
    guard = BudgetGuard(cap)
    return BudgetedProvider(llm, guard), guard, seen


class TestBudgetedProvider:
    def test_yetersiz_butcede_istek_hic_gonderilmez(self):
        wrapped, guard, seen = budgeted(lambda r: llm_ok_response(), Decimal("0.001"))

        with pytest.raises(BudgetExhausted):
            wrapped.classify(DATA, ALL_QUESTIONS, S)

        assert seen == [] and guard.spent == 0 and guard.reserved == 0

    def test_basarili_cagrida_rezervasyon_gercek_ucretle_degisir(self):
        wrapped, guard, seen = budgeted(lambda r: llm_ok_response(), Decimal("1"))

        wrapped.classify(DATA, ALL_QUESTIONS, S)

        assert len(seen) == 1 and guard.reserved == 0
        assert guard.spent == guard.known_spent == LLM_ACTUAL
        assert guard.conservative_charges == 0 and guard.calls == 1

    def test_kullanim_bildirilmeyen_basarili_yanit_en_kotu_bedelle_sayilir(self):
        wrapped, guard, _ = budgeted(lambda r: llm_ok_response(usage={}), Decimal("1"))
        worst = reservation(wrapped)

        wrapped.classify(DATA, ALL_QUESTIONS, S)

        assert guard.spent == worst and guard.known_spent == 0
        assert guard.conservative_charges == 1  # ücretsiz SAYILMADI

    def test_http_hatasi_ve_ag_hatasi_ucretsiz_sayilmaz(self):
        for handler in (lambda r: httpx.Response(529), self._timeout):
            wrapped, guard, _ = budgeted(handler, Decimal("1"))
            worst = reservation(wrapped)

            with pytest.raises(ProviderError):
                wrapped.classify(DATA, ALL_QUESTIONS, S)

            assert guard.spent == worst and guard.conservative_charges == 1

    @staticmethod
    def _timeout(request):
        raise httpx.ReadTimeout("yavaş", request=request)

    def test_sema_hatasi_yaniti_kullanim_bildirdigi_icin_gercek_ucretle_sayilir(self):
        broken = {"category": {"answer": "bilinmeyen", "confidence": 0.5}}
        wrapped, guard, _ = budgeted(lambda r: llm_ok_response(broken), Decimal("1"))

        with pytest.raises(ProviderError) as caught:
            wrapped.classify(DATA, ALL_QUESTIONS, S)

        assert caught.value.status is CallStatus.SCHEMA_ERROR
        assert guard.spent == guard.known_spent == LLM_ACTUAL and guard.conservative_charges == 0

    def test_farkli_model_surumuyle_gelen_yanit_en_kotu_bedelle_sayilir(self):
        wrapped, guard, _ = budgeted(
            lambda r: llm_ok_response(model="claude-haiku-4-6"), Decimal("1")
        )
        worst = reservation(wrapped)

        wrapped.classify(DATA, ALL_QUESTIONS, S)

        assert guard.spent == worst and guard.conservative_charges == 1

    def test_gercek_ucret_rezervasyonu_asarsa_ihlal_kaydedilir(self):
        wrapped, guard, _ = budgeted(
            lambda r: llm_ok_response(usage=usage_block(input_tokens=5_000_000)), Decimal("100")
        )

        wrapped.classify(DATA, ALL_QUESTIONS, S)

        assert guard.bound_violations == 1 and guard.spent > reservation(wrapped)

    def test_beklenmeyen_kesintide_cagri_en_kotu_bedelle_sayilir_ve_hata_yeniden_firlar(self):
        def interrupted(request):
            raise KeyboardInterrupt

        wrapped, guard, _ = budgeted(interrupted, Decimal("1"))
        worst = reservation(wrapped)

        with pytest.raises(KeyboardInterrupt):
            wrapped.classify(DATA, ALL_QUESTIONS, S)

        assert guard.spent == worst and guard.reserved == 0  # istek gitmiş olabilir

    def test_fiyati_bilinmeyen_saglayici_hic_cagrilmaz(self):
        wrapped, guard, seen = budgeted(lambda r: llm_ok_response(), Decimal("1"), price=None)

        with pytest.raises(BudgetExhausted):
            wrapped.classify(DATA, ALL_QUESTIONS, S)

        assert seen == [] and guard.spent == 0

    def test_saglayici_ozellikleri_yonlendirilir(self):
        wrapped, _, _ = budgeted(lambda r: llm_ok_response(), Decimal("1"))

        assert wrapped.name == "anthropic" and wrapped.model == "claude-haiku-4-5-20251001"
        assert wrapped.price is CLAUDE_HAIKU_4_5 and wrapped.temperature == 0.0
        assert wrapped.prompt_version.startswith("llm-istem-v1-")
        assert isinstance(wrapped.inner, AnthropicProvider)
        wrapped.close()  # asıl istemciyi kapatır


class TestRetryAndHybridIntegration:
    def test_retry_sirasinda_butce_biterse_ikinci_istek_gonderilmez_ilk_deneme_kaydi_tasinir(self):
        wrapped, guard, seen = budgeted(lambda r: httpx.Response(529), Decimal("1"))
        worst = reservation(wrapped)
        guard.cap = worst + worst / 2  # bir çağrıya yeter, ikisine yetmez

        with pytest.raises(BudgetExhausted) as caught:
            classify_with_retry(wrapped, DATA, ALL_QUESTIONS, S, NO_WAIT, lambda s: None)

        assert len(seen) == 1  # ikinci deneme için rezervasyon yapılamadı → istek yok
        assert guard.spent == worst  # ilk denemenin bedeli (bilinmediği için en kötü durum) sayıldı
        assert [c.attempt for c in caught.value.calls] == [1]
        assert caught.value.calls[0].status is CallStatus.UNAVAILABLE

    def test_hibritte_llm_asamasinda_butce_biterse_jev_cagri_kaydi_kaybolmaz(self):
        jev_inner, jev_seen = jev_provider(lambda r: jev_ok_response())
        llm_inner, llm_seen = llm_provider(lambda r: llm_ok_response())
        guard = BudgetGuard(Decimal("1"))
        jev = BudgetedProvider(jev_inner, guard)
        llm = BudgetedProvider(llm_inner, guard)
        # Jev'e yeter ama LLM aşamasının rezervasyonuna yetmez.
        guard.cap = max_call_cost(jev, DATA) + max_call_cost(llm, DATA) / 2
        thresholds = HybridThresholds(dict.fromkeys(ALL_QUESTIONS, 0.99))  # hepsi LLM'e gider
        strategy = HybridStrategy(jev, llm, thresholds, NO_WAIT, lambda s: None)

        with pytest.raises(BudgetExhausted) as caught:
            strategy.decide(DATA)

        assert len(jev_seen) == 1 and llm_seen == []  # LLM isteği hiç gönderilmedi
        assert [c.provider for c in caught.value.calls] == ["jev"]  # harcanan Jev çağrısı kayıtlı
        assert guard.spent > 0


def test_tek_soru_cagrisi_tum_sorulardan_ucuz_rezerve_edilir():
    llm, _ = llm_provider(lambda r: llm_ok_response())

    one = max_call_cost(llm, DATA, (Question.MISSING_TIMING,))
    everything = max_call_cost(llm, DATA, ALL_QUESTIONS)

    assert one < everything  # hibritte yalnızca güvenilmeyen sorular sorulur: rezervasyon da küçük
