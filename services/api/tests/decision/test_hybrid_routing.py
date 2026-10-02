import pytest

from app.decision.contract import (
    ALL_QUESTIONS,
    CallStatus,
    DecisionUnavailable,
    Question,
    StrategyName,
    known_cost,
)
from app.decision.mock import MockProvider
from app.decision.retry import RetryPolicy
from app.decision.routing import Route, route_decision
from app.decision.rule_based import RuleBasedStrategy
from app.decision.strategies import HybridStrategy, HybridThresholds, ProviderStrategy
from app.domain.vocabulary import CATEGORY_DEFAULT_TEAM, Category, TeamCode
from tests.decision.conftest import make_input

CLEAR = make_input(
    "Lavabo akıtıyor", "B blok ikinci kattaki lavabo akıtıyor, su koridora yayılıyor."
)
VAGUE = make_input("Bir sorun var", "Bir sorun var ama ne olduğunu tam bilmiyorum.")


def hybrid(jev=None, llm=None, thresholds=None, sleep=lambda s: None):
    jev = jev or MockProvider("jev")
    llm = llm or MockProvider("llm")
    return HybridStrategy(jev, llm, thresholds, RetryPolicy(max_attempts=3), sleep), jev, llm


class TestHybridFlow:
    def test_jev_yeterince_eminse_llm_hic_cagrilmaz(self):
        strategy, jev, llm = hybrid(thresholds=HybridThresholds({q: 0.0 for q in ALL_QUESTIONS}))

        decision = strategy.decide(CLEAR)

        assert llm.call_count == 0
        assert decision.providers == ("mock-jev",)
        assert decision.model_versions == ("mock-jev-1",)
        assert decision.strategy is StrategyName.HYBRID
        assert len(decision.calls) == 1
        assert decision.category is Category.PLUMBING

    def test_yalniz_guvenilmeyen_karar_sorulari_llm_e_gider(self):
        # Jev kategori ve önceliğe güvenir (eşik 0.3); diğer tüm sorulara (eşik 1.01) güvenmez.
        # Güvenilmeyenlerden yalnızca KARAR soruları (konum, açıklama) LLM'e gider; iletişim ve zaman
        # bilgi amaçlıdır, belirsiz olsalar da ücretli çağrıya dahil edilmez.
        thresholds = HybridThresholds(
            {
                **dict.fromkeys(ALL_QUESTIONS, 1.01),
                Question.CATEGORY: 0.3,
                Question.PRIORITY: 0.3,
            }
        )
        strategy, jev, llm = hybrid(thresholds=thresholds)

        decision = strategy.decide(CLEAR)

        assert llm.call_count == 1
        llm_call = [c for c in decision.calls if c.provider == "mock-llm"][0]
        assert set(llm_call.questions) == {Question.MISSING_LOCATION, Question.MISSING_DETAIL}
        assert decision.providers == ("mock-jev", "mock-llm")

    def test_jevin_reddedilen_yargisi_kayitta_kalir_ama_karara_girmez(self):
        strategy, _, _ = hybrid(thresholds=HybridThresholds(dict.fromkeys(ALL_QUESTIONS, 1.01)))

        decision = strategy.decide(CLEAR)

        category = [j for j in decision.judgments if j.question is Question.CATEGORY]
        assert {j.source for j in category} == {"mock-jev", "mock-llm"}
        jev_judgment = next(j for j in category if j.source == "mock-jev")
        llm_judgment = next(j for j in category if j.source == "mock-llm")
        assert not jev_judgment.adopted and llm_judgment.adopted
        # Sağlayıcı sinyalleri ayrı kalır: Jev'de olasılık var, LLM'de yok.
        assert jev_judgment.probabilities and llm_judgment.probabilities is None

    def test_belirsiz_metinde_llm_de_belirsizse_cozulemeyen_insana_gider(self):
        strategy, jev, llm = hybrid()

        decision = strategy.decide(VAGUE)

        assert llm.call_count == 1
        assert decision.category is None
        assert "category_unclear" in decision.review_reasons
        assert route_decision(decision).route is Route.NEEDS_REVIEW

    def test_llm_nin_kendi_yazdigi_guven_jev_guveniyle_kiyaslanmaz(self):
        # LLM %99 güven yazsa bile kabul kapısı yalnızca "belirsiz demedi mi?"ye bakar.
        strategy, _, _ = hybrid(thresholds=HybridThresholds(dict.fromkeys(ALL_QUESTIONS, 1.01)))

        decision = strategy.decide(CLEAR)

        llm_judgments = [j for j in decision.judgments if j.source == "mock-llm"]
        assert llm_judgments and all(
            j.confidence_kind.value == "self_reported" for j in llm_judgments
        )
        assert decision.category is Category.PLUMBING  # kabul edildi

    def test_isteğe_bagli_llm_cekimserlik_kapisi(self):
        thresholds = HybridThresholds(
            dict.fromkeys(ALL_QUESTIONS, 1.01), llm_min_self_reported=0.9999
        )
        strategy, _, _ = hybrid(thresholds=thresholds)

        decision = strategy.decide(CLEAR)

        assert decision.category is None  # LLM kendi güvenini yeterli bulmadı → çekimser
        assert decision.review_required


class TestNoSilentSwitching:
    def test_jev_kalici_basarisizsa_llm_e_gecilmez(self):
        strategy, jev, llm = hybrid(jev=MockProvider("jev", script=[CallStatus.UNAVAILABLE] * 3))

        with pytest.raises(DecisionUnavailable) as caught:
            strategy.decide(CLEAR)

        assert llm.call_count == 0  # sessiz sağlayıcı değişimi yok
        assert len(caught.value.calls) == 3
        assert {c.provider for c in caught.value.calls} == {"mock-jev"}

    def test_llm_ikinci_asamada_basarisizsa_jevin_guvenli_yanitlari_korunur(self):
        thresholds = HybridThresholds(
            {
                **dict.fromkeys(ALL_QUESTIONS, 1.01),
                Question.CATEGORY: 0.3,
                Question.PRIORITY: 0.3,
            }
        )
        llm = MockProvider("llm", script=[CallStatus.UNAVAILABLE] * 3)
        strategy, jev, _ = hybrid(llm=llm, thresholds=thresholds)

        decision = strategy.decide(CLEAR)

        assert decision.category is Category.PLUMBING  # Jev'in güvenli yargısı korundu
        assert "llm_unavailable" in decision.review_reasons
        assert decision.review_required
        assert llm.call_count == 3  # sınırlı retry
        providers = [c.provider for c in decision.calls]
        assert providers.count("mock-jev") == 1 and providers.count("mock-llm") == 3
        assert unknown_failed(decision) == 3  # başarısız denemelerin maliyeti bilinmez, gizlenmez
        assert known_cost(decision.calls) == 0


def unknown_failed(decision):
    return sum(c.cost_usd is None for c in decision.calls if c.status is not CallStatus.OK)


class TestRetryCostsInTotals:
    def test_hibrit_toplam_tum_cagrilari_icerir(self):
        llm = MockProvider("llm", script=[CallStatus.TIMEOUT])
        strategy, _, _ = hybrid(
            llm=llm, thresholds=HybridThresholds(dict.fromkeys(ALL_QUESTIONS, 1.01))
        )

        decision = strategy.decide(CLEAR)

        # Jev (1) + LLM zaman aşımı (1) + LLM başarılı (1)
        assert [c.provider for c in decision.calls] == ["mock-jev", "mock-llm", "mock-llm"]
        assert [c.attempt for c in decision.calls] == [1, 1, 2]


class TestRoutingRules:
    def test_her_kategori_sozlukteki_varsayilan_ekibe_gider(self):
        examples = {
            Category.ELECTRICAL: make_input(
                "Ampul yanmıyor", "Koridordaki ampul yanmıyor, akşamları karanlık oluyor."
            ),
            Category.PLUMBING: CLEAR,
            Category.IT_NETWORK: make_input(
                "Wi-Fi koptu", "Yurt Wi-Fi bağlantısı akşamları sürekli kopuyor."
            ),
            Category.CLEANING: make_input(
                "Çöp taştı", "Üçüncü kat koridordaki çöp kutuları iki gündür boşaltılmadı."
            ),
            Category.OTHER: make_input(
                "Asansör bozuk", "Asansör iki gündür çalışmıyor, merdiven kullanıyoruz."
            ),
        }
        for category, data in examples.items():
            decision = RuleBasedStrategy().decide(data)
            outcome = route_decision(decision)

            assert decision.category is category
            assert outcome.route is Route.TEAM_QUEUE
            assert outcome.team_code is CATEGORY_DEFAULT_TEAM[category]
        assert {c for c in CATEGORY_DEFAULT_TEAM.values()} == set(TeamCode)

    def test_model_ciktisi_gorevli_atamaz_yalniz_ekip_kuyrugu(self):
        decision = ProviderStrategy(StrategyName.JEV_ONLY, MockProvider("jev")).decide(CLEAR)

        outcome = route_decision(decision)

        assert outcome.route is Route.TEAM_QUEUE
        assert not hasattr(outcome, "assignee")  # görevli seçimi insanındır

    def test_eksik_konum_otomatik_ekip_kuyrugunu_engeller(self):
        data = make_input(
            "Lavabo akıtıyor",
            "B blok ikinci kattaki lavabo akıtıyor, su koridora yayılıyor.",
            location="?",
        )

        outcome = route_decision(RuleBasedStrategy().decide(data))

        assert outcome.route is Route.NEEDS_REVIEW
        assert "location_missing" in outcome.reasons

    def test_guvenlik_isaretli_talep_otomatik_dusmez_ama_oncelik_yuksek(self):
        data = make_input("Prizden kıvılcım", "Odadaki prizden kıvılcım çıktı, yanık kokusu var.")

        for strategy in (
            RuleBasedStrategy(),
            ProviderStrategy(StrategyName.JEV_ONLY, MockProvider("jev")),
            hybrid()[0],
        ):
            decision = strategy.decide(data)

            assert route_decision(decision).route is Route.NEEDS_REVIEW, strategy
            assert decision.priority.value == "high"
