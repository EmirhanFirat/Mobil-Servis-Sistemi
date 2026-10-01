from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.config import Settings, get_settings
from app.deps import DbSession

router = APIRouter(tags=["sistem"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]


@router.get("/health", response_model=HealthResponse, summary="Servis ayakta mı?")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Yalnızca sürecin ayakta olduğunu söyler; veritabanı kontrolü içermez."""
    return HealthResponse(
        status="ok",
        service="talepakis-api",
        version=__version__,
        environment=settings.environment,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    summary="Servis istek almaya hazır mı? (veritabanı dahil)",
)
def readiness(db: DbSession, response: Response) -> ReadinessResponse:
    try:
        db.execute(text("select 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return ReadinessResponse(status="unavailable", database="unavailable")
    return ReadinessResponse(status="ok", database="ok")
