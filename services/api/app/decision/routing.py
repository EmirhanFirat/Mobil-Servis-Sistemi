"""Karardan yönlendirme: model ekibi ÖNERİR, yerleştirmeyi deterministik kural yapar.

Model çıktısı atama, erişim veya yetki vermez. Karar belirsiz, güvenlik işaretli, eksik bilgili
veya enjeksiyon şüpheliyse talep insan incelemesine (needs_review) gider; aksi halde kategorinin
varsayılan ekip kuyruğuna düşer (sözlükteki tek kaynak). Görevli seçimi insanındır.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.decision.contract import Decision
from app.domain.vocabulary import CATEGORY_DEFAULT_TEAM, TeamCode


class Route(StrEnum):
    NEEDS_REVIEW = "needs_review"
    TEAM_QUEUE = "team_queue"


@dataclass(frozen=True)
class RouteOutcome:
    route: Route
    team_code: TeamCode | None
    reasons: tuple[str, ...]


def route_decision(decision: Decision) -> RouteOutcome:
    if decision.review_required or decision.category is None or decision.priority is None:
        return RouteOutcome(Route.NEEDS_REVIEW, None, decision.review_reasons)
    return RouteOutcome(Route.TEAM_QUEUE, CATEGORY_DEFAULT_TEAM[decision.category], ())
