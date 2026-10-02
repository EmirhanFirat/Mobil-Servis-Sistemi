from app.decision.assemble import assemble
from app.decision.contract import (
    UNCLEAR,
    ConfidenceKind,
    DecisionInput,
    Judgment,
    Question,
    StrategyName,
)
from app.domain.vocabulary import Category, MissingInfo, Priority
from tests.decision.conftest import make_input


def build(judgments, data: DecisionInput | None = None):
    return assemble(
        strategy=StrategyName.HYBRID,
        data=data or make_input("Lavabo akıtıyor", "B blok lavabo akıtıyor, su yayılıyor."),
        judgments=judgments,
        calls=[],
        providers=("p",),
        model_versions=("m",),
    )


def test_yalniz_benimsenen_yargilar_karara_girer_sira_onemli_degil():
    adopted = Judgment(Question.CATEGORY, "electrical", adopted=True)
    rejected = Judgment(Question.CATEGORY, "plumbing", adopted=False)

    # Reddedilen yargı listede SONRA gelse de karara girmez.
    assert build([adopted, rejected]).category is Category.ELECTRICAL
    assert build([rejected, adopted]).category is Category.ELECTRICAL


def test_yalniz_reddedilmis_yargi_varsa_kategori_belirsiz_kalir():
    decision = build([Judgment(Question.CATEGORY, "plumbing", adopted=False)])

    assert decision.category is None
    assert "category_unclear" in decision.review_reasons
    # Reddedilen yargı izlenebilirlik için kayıtta durur.
    assert len(decision.judgments) == 1


def test_belirsiz_gecersiz_veya_yanlis_tipte_yanit_kategori_vermez():
    for answer in (UNCLEAR, "bilinmeyen_kategori", None, True):
        decision = build([Judgment(Question.CATEGORY, answer)])

        assert decision.category is None, answer


def test_eksik_bilgi_kararli_sirada_ve_yalniz_true_olanlar():
    decision = build(
        [
            Judgment(Question.MISSING_TIMING, True),
            Judgment(Question.MISSING_CONTACT, False),
            Judgment(Question.MISSING_LOCATION, None),
            Judgment(Question.MISSING_DETAIL, True),
        ]
    )

    assert decision.missing_info == (MissingInfo.DETAIL, MissingInfo.TIMING)
    assert "detail_missing" in decision.review_reasons  # engelleyici eksik
    assert "timing_missing" not in decision.review_reasons  # engelleyici değil


def test_guvenlik_kapisi_dusuk_oncelikli_yargiyi_yukseltir_ve_nedeni_yazar():
    data = make_input("Prizden kıvılcım", "Odadaki prizden kıvılcım çıktı.")

    decision = build(
        [
            Judgment(Question.CATEGORY, "electrical"),
            Judgment(Question.PRIORITY, "low"),
        ],
        data,
    )

    assert decision.priority is Priority.HIGH
    assert decision.review_required
    assert "safety:kivilcim" in decision.review_reasons


def test_guvenlik_kapisi_oncelik_belirsizken_de_yuksek_yapar():
    data = make_input("Gaz kokusu", "Mutfakta gaz kokusu var.")

    decision = build(
        [Judgment(Question.CATEGORY, "other"), Judgment(Question.PRIORITY, UNCLEAR)], data
    )

    assert decision.priority is Priority.HIGH


def test_saglayiciya_ozgu_sinyaller_karar_alanlarindan_ayri_saklanir():
    jev = Judgment(
        Question.CATEGORY,
        "plumbing",
        probabilities={"plumbing": 0.9, "unclear": 0.1},
        confidence=0.88,
        confidence_kind=ConfidenceKind.JEV_CONFIDENCE,
        n_options=6,
        source="jev",
    )

    decision = build([jev, Judgment(Question.PRIORITY, "normal")])

    assert decision.category is Category.PLUMBING
    assert decision.judgments[0].probabilities == {"plumbing": 0.9, "unclear": 0.1}
    assert decision.judgments[0].confidence_kind is ConfidenceKind.JEV_CONFIDENCE
    assert not hasattr(decision, "confidence")  # tek bir "güven" alanı uydurulmaz
