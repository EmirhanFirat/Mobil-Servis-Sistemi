"""Hibritin LLM'e geçiş politikası: yalnızca ürün kararını etkileyen sorular ücretli çağrı başlatır.

Bağlam: 2026-10-02'deki ilk gerçek bağlantı denemesinde hibrit 5 örneğin 5'inde LLM'e geçti ve her
seferinde yalnızca `missing_contact` için (Jev'in türetilmiş marj güveni 0,22–0,52 < 0,6). Bu soru
etiketsizdir ve kararı engellemez; geçişlerin hiçbir ölçülen sonucu değiştirmeden ücretin ~%97'sini
oluşturduğu görüldü. Buradaki testler yeni davranışı ağ isteği olmadan doğrular (gerçek model
davranışını ÖLÇMEZ).
"""

import dataclasses
import json
from decimal import Decimal

import pytest

from app.decision.assemble import assemble
from app.decision.budget import BudgetedProvider, BudgetGuard, max_call_cost
from app.decision.contract import (
    ALL_QUESTIONS,
    BLOCKING_MISSING,
    DECISION_QUESTIONS,
    INFORMATIONAL_QUESTIONS,
    MISSING_QUESTIONS,
    QUESTION_ROLES,
    BudgetExhausted,
    CallStatus,
    DecisionUnavailable,
    Judgment,
    Question,
    QuestionRole,
    StrategyName,
    probability_floor,
    unresolved_questions,
)
from app.decision.registry import build_free_strategy
from app.decision.retry import RetryPolicy
from app.decision.routing import Route, route_decision
from app.decision.serialize import decision_to_dict
from app.decision.strategies import (
    DEFAULT_JEV_MIN_CONFIDENCE,
    HYBRID_ROUTING_VERSION,
    HybridStrategy,
    HybridThresholds,
    ProviderStrategy,
)
from app.domain.vocabulary import MissingInfo
from tests.decision.conftest import make_input
from tests.decision.scripted import ScriptedJev, ScriptedLLM
from tests.decision.test_jev import ok_response as jev_ok_response
from tests.decision.test_jev import provider as jev_provider
from tests.decision.test_llm_anthropic import ok_response as llm_ok_response
from tests.decision.test_llm_anthropic import provider as llm_provider

DATA = make_input(
    "Lavabo akıtıyor", "B blok ikinci kattaki lavabo akıtıyor, su koridora yayılıyor."
)
NO_WAIT = RetryPolicy(max_attempts=3)
NO_GIT = lambda: {"source_commit": "test", "git_dirty": False}  # noqa: E731

C = Question


def hybrid(jev=None, llm=None, thresholds=None):
    jev = jev or ScriptedJev()
    llm = llm or ScriptedLLM()
    strategy = HybridStrategy(jev, llm, thresholds, NO_WAIT, lambda s: None)
    return strategy, jev, llm


class TestQuestionRoles:
    def test_roller_ve_engelleyici_eksik_bilgiler_birbirinden_turetilir(self):
        assert DECISION_QUESTIONS == {C.CATEGORY, C.PRIORITY, C.MISSING_LOCATION, C.MISSING_DETAIL}
        assert INFORMATIONAL_QUESTIONS == {C.MISSING_CONTACT, C.MISSING_TIMING}
        assert DECISION_QUESTIONS | INFORMATIONAL_QUESTIONS == set(ALL_QUESTIONS)
        assert not DECISION_QUESTIONS & INFORMATIONAL_QUESTIONS
        # Eksik bilgi sorusu, ancak ve ancak yanıtı otomatik yönlendirmeyi engelliyorsa karar sorusudur.
        for question, label in MISSING_QUESTIONS.items():
            is_decision = QUESTION_ROLES[question] is QuestionRole.DECISION
            assert is_decision == (label in BLOCKING_MISSING), question

    def test_bilgi_amacli_sorunun_cevabi_yonlendirmeyi_ve_incelemeyi_degistirmez(self):
        def judge(contact, timing):
            return [
                Judgment(C.CATEGORY, "plumbing"),
                Judgment(C.PRIORITY, "normal"),
                Judgment(C.MISSING_LOCATION, False),
                Judgment(C.MISSING_DETAIL, False),
                Judgment(C.MISSING_CONTACT, contact),
                Judgment(C.MISSING_TIMING, timing),
            ]

        def decide(judgments):
            return assemble(
                strategy=StrategyName.JEV_ONLY,
                data=DATA,
                judgments=judgments,
                calls=[],
                providers=("x",),
                model_versions=("x",),
            )

        eksik, tam = decide(judge(True, True)), decide(judge(False, False))

        assert eksik.missing_info == (
            MissingInfo.CONTACT,
            MissingInfo.TIMING,
        )  # etiket olarak yazılır
        assert not eksik.review_required and not tam.review_required
        assert route_decision(eksik).route is route_decision(tam).route is Route.TEAM_QUEUE

    def test_engelleyici_eksik_bilgi_incelemeye_gider(self):
        decision = assemble(
            strategy=StrategyName.JEV_ONLY,
            data=DATA,
            judgments=[
                Judgment(C.CATEGORY, "plumbing"),
                Judgment(C.PRIORITY, "normal"),
                Judgment(C.MISSING_LOCATION, True),
                Judgment(C.MISSING_DETAIL, False),
            ],
            calls=[],
            providers=("x",),
            model_versions=("x",),
        )

        assert decision.review_reasons == ("location_missing",)
        assert route_decision(decision).route is Route.NEEDS_REVIEW


class TestThresholdDefaultsAndConfig:
    def test_varsayilan_esik_provizyonel_0_6_ve_degismedi(self):
        # İlk deneme yalnızca 5 örnekti; bu eşik onlara bakılarak DÜŞÜRÜLMEDİ.
        assert DEFAULT_JEV_MIN_CONFIDENCE == 0.6
        assert HybridThresholds().jev_min_confidence == dict.fromkeys(ALL_QUESTIONS, 0.6)
        assert HybridThresholds().escalate_on == DECISION_QUESTIONS

    def test_esikler_soru_bazinda_ayarlanir_digerleri_ayni_kalir(self):
        base = HybridThresholds()
        tuned = base.with_confidence({C.MISSING_LOCATION: 0.8, C.CATEGORY: 0.5})

        assert tuned is not base
        assert tuned.jev_min_confidence[C.MISSING_LOCATION] == 0.8
        assert tuned.jev_min_confidence[C.CATEGORY] == 0.5
        others = set(ALL_QUESTIONS) - {C.MISSING_LOCATION, C.CATEGORY}
        assert all(tuned.jev_min_confidence[q] == 0.6 for q in others)
        # Özgün nesne (ve dolayısıyla onu paylaşan her strateji) değişmez.
        assert base.jev_min_confidence == dict.fromkeys(ALL_QUESTIONS, 0.6)

    @pytest.mark.parametrize("question", sorted(INFORMATIONAL_QUESTIONS, key=lambda q: q.value))
    def test_bilgi_amacli_soru_llm_e_gecisi_tetikleyecek_sekilde_ayarlanamaz(self, question):
        with pytest.raises(ValueError, match="tetikleyemez"):
            HybridThresholds(escalate_on=frozenset({C.CATEGORY, question}))

    def test_karar_sorularinin_alt_kumesi_gecerli_bos_kume_de(self):
        assert HybridThresholds(escalate_on=frozenset({C.CATEGORY})).escalate_on == {C.CATEGORY}
        assert HybridThresholds(escalate_on=frozenset()).escalate_on == frozenset()

    def test_eksik_esik_erken_ve_acik_hata_verir(self):
        with pytest.raises(ValueError, match="missing_timing"):
            HybridThresholds({q: 0.6 for q in ALL_QUESTIONS if q is not C.MISSING_TIMING})

    def test_yonlendirme_surumu_kayitli(self):
        assert HYBRID_ROUTING_VERSION == "hibrit-yonlendirme-v2"
        assert HybridStrategy.routing_version == HYBRID_ROUTING_VERSION


class TestInformationalUncertaintyStartsNoCall:
    def test_yalniz_bilgi_amacli_belirsizlik_ucretli_cagri_baslatmaz(self):
        # Karar soruları emin; iletişim ve zaman çok düşük güvenli.
        jev = ScriptedJev({C.MISSING_CONTACT: 0.05, C.MISSING_TIMING: 0.1})
        strategy, _, llm = hybrid(jev)

        decision = strategy.decide(DATA)

        assert llm.call_count == 0
        assert decision.providers == ("jev",) and len(decision.calls) == 1
        assert not decision.review_required  # bilgi amaçlı belirsizlik incelemeye de göndermez
        assert route_decision(decision).route is Route.TEAM_QUEUE

    def test_tum_bilgi_amacli_sorular_asla_tek_basina_cagri_baslatmaz_en_dusuk_guvende_bile(self):
        for confidence in (0.0, 0.2, 0.59):
            jev = ScriptedJev(dict.fromkeys(INFORMATIONAL_QUESTIONS, confidence))
            strategy, _, llm = hybrid(jev)

            strategy.decide(DATA)

            assert llm.call_count == 0, confidence

    def test_esik_1_in_ustunde_olsa_bile_bilgi_amacli_soru_cagri_baslatmaz(self):
        # Eşiği hiçbir yanıtın geçemeyeceği bir değere çekmek bile bilgi amaçlı soruyu aktarmaz.
        thresholds = HybridThresholds(dict.fromkeys(ALL_QUESTIONS, 1.01))
        strategy, _, llm = hybrid(thresholds=thresholds)

        strategy.decide(DATA)

        # Yalnızca dört karar sorusu aktarılır; iletişim/zaman asla.
        assert llm.calls == [tuple(q for q in ALL_QUESTIONS if q in DECISION_QUESTIONS)]

    def test_gercek_adaptorlerle_butce_korumali_bilgi_amacli_belirsizlik_rezervasyon_bile_yapmaz(
        self,
    ):
        # Standart sahte Jev yanıtında zaman sorusunun kenar payı 0,30 (< 0,6): belirsiz ama bilgi amaçlı.
        jev_inner, jev_seen = jev_provider(lambda r: jev_ok_response())
        llm_inner, llm_seen = llm_provider(lambda r: llm_ok_response())
        guard = BudgetGuard(Decimal(1))
        jev = BudgetedProvider(jev_inner, guard)
        llm = BudgetedProvider(llm_inner, guard)
        # Bütçe yalnızca Jev çağrısına yeter: LLM aşaması için rezervasyon denense BudgetExhausted olurdu.
        guard.cap = max_call_cost(jev, DATA) + max_call_cost(llm, DATA) / 10
        strategy = HybridStrategy(jev, llm, None, NO_WAIT, lambda s: None)

        decision = strategy.decide(DATA)  # BudgetExhausted fırlamamalı

        assert len(jev_seen) == 1 and llm_seen == []
        assert guard.summary()["calls"] == 1  # LLM için rezervasyon hiç denenmedi
        timing = [j for j in decision.judgments if j.question is C.MISSING_TIMING]
        assert [(j.adopted, j.confidence < 0.6) for j in timing] == [(False, True)]


class TestDecisionQuestionsEscalate:
    def test_karar_sorusundaki_belirsizlik_llm_e_aktarilir(self):
        jev = ScriptedJev({C.MISSING_DETAIL: 0.3})
        strategy, _, llm = hybrid(jev, ScriptedLLM({C.MISSING_DETAIL: True}))

        decision = strategy.decide(DATA)

        assert llm.calls == [(C.MISSING_DETAIL,)]
        assert decision.providers == ("jev", "anthropic")
        detail = [j for j in decision.judgments if j.question is C.MISSING_DETAIL]
        assert [(j.source, j.adopted, j.answer) for j in detail] == [
            ("jev", False, False),  # Jev'in yargısı kayıtta kalır, karara girmez
            ("anthropic", True, True),  # LLM'inki benimsenir
        ]
        assert MissingInfo.DETAIL in decision.missing_info
        assert "detail_missing" in decision.review_reasons  # LLM cevabı kararı etkiledi
        assert route_decision(decision).route is Route.NEEDS_REVIEW

    @pytest.mark.parametrize("question", sorted(DECISION_QUESTIONS, key=lambda q: q.value))
    def test_her_karar_sorusu_tek_basina_cagri_baslatabilir(self, question):
        strategy, _, llm = hybrid(ScriptedJev({question: 0.1}))

        strategy.decide(DATA)

        assert llm.calls == [(question,)]

    def test_bilgi_amacli_belirsizlik_karar_sorusuna_yapismaz(self):
        # Karar sorusu belirsiz → LLM'e gider. Aynı çağrıya bilgi amaçlı sorular EKLENMEZ (ücretsiz
        # eklenmez: her soru girdi/çıktı token'ıdır).
        jev = ScriptedJev({C.MISSING_LOCATION: 0.2, C.MISSING_CONTACT: 0.1, C.MISSING_TIMING: 0.1})
        strategy, _, llm = hybrid(jev)

        decision = strategy.decide(DATA)

        assert llm.calls == [(C.MISSING_LOCATION,)]
        asked = {
            q for call in decision.calls for q in call.questions if call.provider == "anthropic"
        }
        assert not asked & INFORMATIONAL_QUESTIONS

    def test_birden_cok_belirsiz_karar_sorusu_tek_llm_cagrisinda_sorulur(self):
        jev = ScriptedJev({C.CATEGORY: 0.2, C.PRIORITY: 0.2, C.MISSING_DETAIL: 0.2})
        strategy, _, llm = hybrid(jev)

        strategy.decide(DATA)

        assert llm.calls == [(C.CATEGORY, C.PRIORITY, C.MISSING_DETAIL)]

    def test_esikler_soru_bazinda_bagimsiz_uygulanir(self):
        # Aynı Jev güveni (0,8): kategori için eşik 0,9 (belirsiz), öncelik için 0,5 (emin).
        jev = ScriptedJev({C.CATEGORY: 0.8, C.PRIORITY: 0.8})
        thresholds = HybridThresholds().with_confidence({C.CATEGORY: 0.9, C.PRIORITY: 0.5})
        strategy, _, llm = hybrid(jev, thresholds=thresholds)

        strategy.decide(DATA)

        assert llm.calls == [(C.CATEGORY,)]

    def test_esikle_tam_ayni_guven_emin_sayilir_sinirin_altindaki_degil(self):
        jev = ScriptedJev({C.CATEGORY: 0.6, C.PRIORITY: 0.5999})
        strategy, _, llm = hybrid(jev)

        strategy.decide(DATA)

        assert llm.calls == [(C.PRIORITY,)]

    def test_llm_stage_yoksa_eminse_hic_cagri_yok(self):
        strategy, _, llm = hybrid()

        decision = strategy.decide(DATA)

        assert llm.call_count == 0 and decision.providers == ("jev",)

    def test_karar_sorusu_aktarimi_kapatilirsa_sorulmaz_ama_bilinmiyor_incelemeye_gider(self):
        # Yapılandırma "açıklama yetersiz mi?" sorusunu LLM'e aktarmıyor ve Jev emin değil: bu soru
        # SESSİZCE "eksik değil" sayılmaz; açıklama bilinmiyor → insan bakar.
        escalate = frozenset({C.CATEGORY, C.PRIORITY, C.MISSING_LOCATION})
        thresholds = HybridThresholds(escalate_on=escalate)
        strategy, _, llm = hybrid(ScriptedJev({C.MISSING_DETAIL: 0.1}), thresholds=thresholds)

        decision = strategy.decide(DATA)

        assert llm.call_count == 0
        assert MissingInfo.DETAIL not in decision.missing_info
        assert "detail_unknown" in decision.review_reasons
        assert route_decision(decision).route is Route.NEEDS_REVIEW


class TestUnresolvedIsNotPresentedAsCertain:
    @pytest.mark.parametrize("jev_answer", [True, False])
    def test_aktarilmayan_belirsiz_bilgi_amacli_cevap_ne_eksik_ne_tam_diye_sunulur(
        self, jev_answer
    ):
        jev = ScriptedJev({C.MISSING_CONTACT: 0.1}, answers={C.MISSING_CONTACT: jev_answer})
        strategy, _, _ = hybrid(jev)

        decision = strategy.decide(DATA)

        contact = [j for j in decision.judgments if j.question is C.MISSING_CONTACT]
        assert [(j.answer, j.adopted) for j in contact] == [
            (jev_answer, False)
        ]  # kayıtta, karar dışı
        assert MissingInfo.CONTACT not in decision.missing_info  # "eksik" diye sunulmaz
        assert C.MISSING_CONTACT in unresolved_questions(decision.judgments)  # "tam" da denmez
        # Aynı yargı benimsenmiş olsaydı çözülmüş sayılırdı: fark yalnızca benimsenmemesindendir.
        adopted = [dataclasses.replace(contact[0], adopted=True)]
        assert C.MISSING_CONTACT not in unresolved_questions(adopted)

    def test_benimsenen_kesin_yanit_cozulmus_sayilir(self):
        resolved = [Judgment(C.MISSING_CONTACT, True, adopted=True)]
        rejected = [Judgment(C.MISSING_CONTACT, True, adopted=False)]
        abstained = [Judgment(C.MISSING_CONTACT, None), Judgment(C.CATEGORY, "unclear")]

        assert C.MISSING_CONTACT not in unresolved_questions(resolved)
        assert C.MISSING_CONTACT in unresolved_questions(rejected)
        assert {C.MISSING_CONTACT, C.CATEGORY} <= set(unresolved_questions(abstained))
        assert unresolved_questions([]) == ALL_QUESTIONS

    def test_ham_cevap_ve_guven_denetim_icin_kayitta_kalir(self):
        jev = ScriptedJev({C.MISSING_CONTACT: 0.12}, answers={C.MISSING_CONTACT: True})
        strategy, _, _ = hybrid(jev)

        payload = decision_to_dict(strategy.decide(DATA))

        contact = [j for j in payload["judgments"] if j["question"] == "missing_contact"]
        assert contact == [
            {
                "question": "missing_contact",
                "answer": True,
                "probabilities": {"yes": 0.5, "no": 0.5},
                "confidence": 0.12,
                "confidence_kind": "derived_margin",
                "n_options": 2,
                "source": "jev",
                "adopted": False,
            }
        ]

    def test_llm_gecici_olarak_yoksa_karar_sorusu_cozulmemis_kalir_ve_incelemeye_gider(self):
        jev = ScriptedJev({C.MISSING_LOCATION: 0.2, C.MISSING_CONTACT: 0.1})
        llm = ScriptedLLM(script=[CallStatus.UNAVAILABLE] * 3)
        strategy, _, _ = hybrid(jev, llm)

        decision = strategy.decide(DATA)

        assert llm.call_count == 3  # sınırlı retry
        assert "llm_unavailable" in decision.review_reasons
        assert "location_unknown" in decision.review_reasons
        assert MissingInfo.LOCATION not in decision.missing_info  # "konum eksik değil" denmez
        assert route_decision(decision).route is Route.NEEDS_REVIEW
        assert {C.MISSING_LOCATION, C.MISSING_CONTACT} <= set(
            unresolved_questions(decision.judgments)
        )
        # Başarısız denemelerin ücreti bilinmez (sıfır sayılıp gizlenmez).
        assert sum(c.cost_usd is None for c in decision.calls) == 3

    def test_llm_cekimserlik_kapisi_karar_sorusunu_cozulmemis_birakir(self):
        thresholds = HybridThresholds(llm_min_self_reported=0.99)  # LLM 0,9 yazıyor → çekimser
        jev = ScriptedJev({C.MISSING_DETAIL: 0.1})
        strategy, _, llm = hybrid(jev, thresholds=thresholds)

        decision = strategy.decide(DATA)

        assert llm.call_count == 1
        assert "detail_unknown" in decision.review_reasons
        assert decision.review_required

    def test_kategori_belirsizse_inceleme_nedeni_degismedi(self):
        jev = ScriptedJev({C.CATEGORY: 0.1})
        llm = ScriptedLLM({C.CATEGORY: "unclear"})
        strategy, _, _ = hybrid(jev, llm)

        decision = strategy.decide(DATA)

        assert decision.category is None and "category_unclear" in decision.review_reasons
        assert route_decision(decision).route is Route.NEEDS_REVIEW


class TestErrorAndBudgetPathsPreserved:
    def test_jev_kalici_basarisizsa_llm_e_sessizce_gecilmez(self):
        jev = ScriptedJev(script=[CallStatus.UNAVAILABLE] * 3)
        strategy, _, llm = hybrid(jev)

        with pytest.raises(DecisionUnavailable):
            strategy.decide(DATA)

        assert llm.call_count == 0

    def test_karar_sorusu_llm_asamasinda_butce_biterse_durur_ve_jev_kaydi_tasinir(self):
        jev_inner, jev_seen = jev_provider(lambda r: jev_ok_response())
        llm_inner, llm_seen = llm_provider(lambda r: llm_ok_response())
        guard = BudgetGuard(Decimal(1))
        jev = BudgetedProvider(jev_inner, guard)
        llm = BudgetedProvider(llm_inner, guard)
        stage = tuple(q for q in ALL_QUESTIONS if q in DECISION_QUESTIONS)
        guard.cap = max_call_cost(jev, DATA) + max_call_cost(llm, DATA, stage) / 2
        # Konum sorusunu belirsiz yapacak kadar yüksek eşik → LLM aşaması gerekir.
        thresholds = HybridThresholds().with_confidence({C.MISSING_LOCATION: 0.99})
        strategy = HybridStrategy(jev, llm, thresholds, NO_WAIT, lambda s: None)

        with pytest.raises(BudgetExhausted) as caught:
            strategy.decide(DATA)

        assert llm_seen == [] and len(jev_seen) == 1  # LLM isteği hiç gönderilmedi
        assert [c.provider for c in caught.value.calls] == ["jev"]

    def test_llm_rezervasyonu_yalniz_aktarilan_sorularin_istek_govdesiyle_yapilir(self):
        llm_inner, _ = llm_provider(lambda r: llm_ok_response())
        guard = BudgetGuard(Decimal(1))
        llm = BudgetedProvider(llm_inner, guard)

        one = max_call_cost(llm, DATA, (C.MISSING_LOCATION,))
        stage = max_call_cost(llm, DATA, tuple(q for q in ALL_QUESTIONS if q in DECISION_QUESTIONS))
        everything = max_call_cost(llm, DATA)

        assert one < stage < everything


class TestSharedOutputContractUnchanged:
    def test_uc_strateji_ayni_karar_sozlesmesini_ve_alanlarini_uretir(self):
        jev, llm = ScriptedJev({C.MISSING_CONTACT: 0.1}), ScriptedLLM()
        decisions = [
            ProviderStrategy(StrategyName.JEV_ONLY, jev, NO_WAIT, lambda s: None).decide(DATA),
            ProviderStrategy(StrategyName.LLM_ONLY, llm, NO_WAIT, lambda s: None).decide(DATA),
            HybridStrategy(jev, llm, None, NO_WAIT, lambda s: None).decide(DATA),
        ]

        assert {type(d) for d in decisions} == {type(decisions[0])}
        assert {tuple(decision_to_dict(d)) for d in decisions} == {
            tuple(decision_to_dict(decisions[0]))
        }
        for decision in decisions:
            asked = {j.question for j in decision.judgments}
            assert asked == set(ALL_QUESTIONS)  # her strateji altı sorunun hepsini kayda geçirir

    def test_jev_only_kendi_dusuk_guvenli_cevabini_oldugu_gibi_benimser(self):
        # Eşik yalnızca hibritin ücretli aşamasını yönetir; jev_only tanımı gereği Jev'e güvenir.
        jev = ScriptedJev({C.MISSING_CONTACT: 0.1})

        decision = ProviderStrategy(StrategyName.JEV_ONLY, jev, NO_WAIT, lambda s: None).decide(
            DATA
        )

        assert MissingInfo.CONTACT in decision.missing_info
        assert unresolved_questions(decision.judgments) == ()


class TestMockHybridProductFlow:
    def test_mock_hibrit_urun_akisinda_iletisim_icin_mock_llm_cagirmaz(self):
        # Mock Jev, iletişim/zaman için ~0,4 marj güveni üretir (< 0,6); eskiden bu her talepte mock LLM
        # çağrısı demekti.
        strategy = build_free_strategy("mock_hybrid")
        data = make_input(
            "Lavabo akıtıyor", "B blok ikinci kattaki lavabo akıtıyor, su koridora yayılıyor."
        )

        decision = strategy.decide(data)

        assert decision.providers == ("mock-jev",)
        assert decision.is_mock  # mock olarak işaretli kalır
        timing = [j for j in decision.judgments if j.question is C.MISSING_TIMING]
        assert timing and not any(j.adopted for j in timing)


class TestProbabilityFloor:
    @pytest.mark.parametrize(("n", "expected"), [(2, 0.8), (4, 0.7), (6, 0.6 * 5 / 6 + 1 / 6)])
    def test_ayni_esik_soru_turune_gore_farkli_olasilik_ister(self, n, expected):
        assert probability_floor(0.6, n) == pytest.approx(expected)

    def test_jev_guven_formulunun_tersidir(self):
        for n in (2, 4, 6):
            for p in (1 / n, 0.55, 0.77, 0.9, 1.0):
                if p < 1 / n:
                    continue
                confidence = (p - 1 / n) / (1 - 1 / n)
                assert probability_floor(confidence, n) == pytest.approx(p)

    def test_ikili_sorularda_turetilen_marj_jev_formuluyle_ayni_sayidir(self):
        for p_yes in (0.1, 0.35, 0.5, 0.8, 0.97):
            p_max = max(p_yes, 1 - p_yes)
            assert abs(2 * p_yes - 1) == pytest.approx((p_max - 0.5) / 0.5)

    def test_gecersiz_secenek_sayisi_reddedilir(self):
        with pytest.raises(ValueError):
            probability_floor(0.6, 1)


# İlk gerçek bağlantı denemesinde (2026-10-02, dev, tohum 4) hibritin KENDİ Jev çağrısının soru
# bazında güvenleri. Yalnızca sayılar: kullanıcı metni, etiket ve model çıktısı yoktur.
# (kategori, öncelik, konum, açıklama, iletişim, zaman)
FIRST_TRIAL_JEV_CONFIDENCES = {
    "s023": (1.00, 0.79, 0.90, 0.84, 0.52, 0.80),
    "s051": (1.00, 0.72, 0.90, 0.82, 0.48, 0.80),
    "s020": (1.00, 0.90, 0.92, 0.76, 0.26, 0.84),
    "s009": (1.00, 0.74, 0.90, 0.80, 0.36, 0.76),
    "s003": (1.00, 0.99, 0.94, 0.86, 0.22, 0.70),
}


class TestReplayOfFirstTrial:
    @pytest.mark.parametrize("sample", sorted(FIRST_TRIAL_JEV_CONFIDENCES))
    def test_ilk_denemenin_jev_guvenleriyle_yeni_politika_llm_cagrisi_uretmez(self, sample):
        values = FIRST_TRIAL_JEV_CONFIDENCES[sample]
        jev = ScriptedJev(dict(zip(ALL_QUESTIONS, values, strict=True)))
        strategy, _, llm = hybrid(jev)

        decision = strategy.decide(DATA)

        # Eskiden (v1) her örnekte iletişim sorusu için LLM çağrısı yapıldı; şimdi hiçbiri.
        uncertain = [q for q, c in zip(ALL_QUESTIONS, values, strict=True) if c < 0.6]
        assert uncertain == [C.MISSING_CONTACT]
        assert llm.call_count == 0
        assert MissingInfo.CONTACT not in decision.missing_info
        assert C.MISSING_CONTACT in unresolved_questions(decision.judgments)


class TestEvaluationRecordsRoutingVersion:
    def test_calistirma_kaydi_yonlendirme_surumunu_ve_tetikleyen_sorulari_yazar(self, tmp_path):
        from app.evaluation import runner

        out = runner.run_evaluation(
            strategy_names=("mock_hybrid",),
            splits=("dev",),
            limit=2,
            out_root=tmp_path,
            hybrid_thresholds=HybridThresholds().with_confidence({C.MISSING_LOCATION: 0.77}),
            git=NO_GIT,
        )

        record = json.loads((out / "run.json").read_text(encoding="utf-8"))
        info = record["strategies"][0]
        assert info["routing_version"] == HYBRID_ROUTING_VERSION
        assert info["escalate_on"] == ["category", "priority", "missing_location", "missing_detail"]
        assert info["thresholds"]["missing_location"] == 0.77
        assert info["thresholds"]["category"] == 0.6  # verilmeyenler varsayılanda kalır

    def test_rapor_yonlendirme_surumunu_yazar_eski_kayitta_satir_eklemez(self, tmp_path):
        from app.evaluation import runner
        from app.evaluation.report import build_report

        out = runner.run_evaluation(
            strategy_names=("mock_hybrid",),
            splits=("dev",),
            limit=2,
            out_root=tmp_path,
            hybrid_thresholds=HybridThresholds().with_confidence({C.MISSING_DETAIL: 0.7}),
            git=NO_GIT,
        )

        text, _ = build_report(out)

        assert f"Hibrit yönlendirme `{HYBRID_ROUTING_VERSION}`" in text
        assert "category, priority, missing_location, missing_detail" in text
        assert "missing_detail=0.7" in text and "missing_contact=0.6" in text
        # v1 kaydı (routing_version alanı yok): satır eklenmez, rapor aynı kalır ve hata vermez.
        record = json.loads((out / "run.json").read_text(encoding="utf-8"))
        for strategy in record["strategies"]:
            for key in ("routing_version", "escalate_on"):
                strategy.pop(key, None)
        (out / "run.json").write_text(json.dumps(record), encoding="utf-8")
        old_text, _ = build_report(out)
        assert "Hibrit yönlendirme" not in old_text

    def test_hybrid_olmayan_stratejiye_esik_uygulanmaz_hata_vermez(self, tmp_path):
        from app.evaluation import runner

        out = runner.run_evaluation(
            strategy_names=("rule_based", "mock_hybrid"),
            splits=("dev",),
            limit=1,
            out_root=tmp_path,
            hybrid_thresholds=HybridThresholds(dict.fromkeys(ALL_QUESTIONS, 0.9)),
            git=NO_GIT,
        )

        record = json.loads((out / "run.json").read_text(encoding="utf-8"))
        kinds = {s["name"]: s for s in record["strategies"]}
        assert "thresholds" not in kinds["rule_based"]
        assert kinds["mock_hybrid"]["thresholds"]["category"] == 0.9


class TestCliThresholdOption:
    def test_gecerli_esikler_run_json_a_yazilir(self, tmp_path, capsys):
        from app.evaluation.cli import main

        code = main(
            [
                "run",
                "--strategies",
                "mock_hybrid",
                "--splits",
                "dev",
                "--limit",
                "1",
                "--out",
                str(tmp_path),
                "--hybrid-threshold",
                "missing_detail=0.7",
                "--hybrid-threshold",
                "priority=0.55",
            ]
        )

        assert code == 0

        run_dir = next(tmp_path.iterdir())
        info = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["strategies"][0]
        assert info["thresholds"]["missing_detail"] == 0.7
        assert info["thresholds"]["priority"] == 0.55
        assert info["thresholds"]["category"] == 0.6
        assert "Çalıştırma kaydedildi" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "value",
        [
            "missing_detail",
            "missing_detail=abc",
            "olmayan_soru=0.5",
            "category=1.5",
            "category=-0.1",
            "category=nan",
        ],
    )
    def test_gecersiz_esik_reddedilir(self, value, tmp_path, capsys):
        from app.evaluation.cli import main

        with pytest.raises(SystemExit) as exit_info:
            main(
                [
                    "run",
                    "--strategies",
                    "mock_hybrid",
                    "--out",
                    str(tmp_path),
                    "--hybrid-threshold",
                    value,
                ]
            )

        assert exit_info.value.code == 2
        assert list(tmp_path.iterdir()) == []  # hiçbir şey çalışmadı
