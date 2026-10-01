from fastapi import APIRouter

from app.domain import vocabulary as v
from app.schemas import LabeledValue, Vocabulary

router = APIRouter(prefix="/meta", tags=["sözlük"])


def _labeled(labels: dict) -> list[LabeledValue]:
    return [LabeledValue(code=code.value, label=label) for code, label in labels.items()]


@router.get("/vocabulary", response_model=Vocabulary, summary="Kodlar ve Türkçe görünen adlar")
def vocabulary() -> Vocabulary:
    """İstemciler Türkçe adları buradan alır; kodlar kararlıdır, adlar değişebilir."""
    return Vocabulary(
        roles=_labeled(v.ROLE_LABELS),
        statuses=_labeled(v.STATUS_LABELS),
        priorities=_labeled(v.PRIORITY_LABELS),
        categories=_labeled(v.CATEGORY_LABELS),
        teams=_labeled(v.TEAM_NAMES),
        missing_info=_labeled(v.MISSING_INFO_LABELS),
        category_default_team={
            category.value: team.value for category, team in v.CATEGORY_DEFAULT_TEAM.items()
        },
    )
