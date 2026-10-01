from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import __version__
from app.config import Settings, get_settings

router = APIRouter(tags=["sistem"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse, summary="Servis ayakta mı?")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Yalnızca sürecin ayakta olduğunu söyler; veritabanı kontrolü içermez."""
    return HealthResponse(
        status="ok",
        service="talepakis-api",
        version=__version__,
        environment=settings.environment,
    )
