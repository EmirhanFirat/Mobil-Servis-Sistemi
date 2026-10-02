import pytest

from app.decision.contract import DecisionInput


def make_input(
    title: str, description: str = "", location: str = "B Blok, 2. kat koridor"
) -> DecisionInput:
    return DecisionInput(
        title=title,
        description=description or f"{title}, birkaç gündür devam ediyor.",
        location=location,
    )


@pytest.fixture
def sleeps() -> list[float]:
    """Gerçekten beklemeyen sahte uyku; çağrılan gecikmeleri kaydeder."""
    return []


@pytest.fixture
def fake_sleep(sleeps: list[float]):
    return sleeps.append
