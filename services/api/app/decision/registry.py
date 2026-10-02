"""Ücretsiz (ağ isteği yapmayan) stratejilerin kayıt defteri. Hem değerlendirme çalıştırıcısı hem
karar worker'ı bunu kullanır; gerçek (ücretli) stratejiler burada YOKTUR ve harcama korumasıyla
yalnızca değerlendirme çalıştırıcısında bulunur (bkz. app/evaluation/runner.py)."""

from collections.abc import Callable

from app.decision.contract import StrategyName
from app.decision.mock import MockProvider
from app.decision.rule_based import RuleBasedStrategy
from app.decision.strategies import HybridStrategy, ProviderStrategy

FREE_STRATEGY_BUILDERS: dict[str, Callable[[], object]] = {
    "rule_based": RuleBasedStrategy,
    "mock_jev": lambda: ProviderStrategy(StrategyName.JEV_ONLY, MockProvider("jev")),
    "mock_llm": lambda: ProviderStrategy(StrategyName.LLM_ONLY, MockProvider("llm")),
    "mock_hybrid": lambda: HybridStrategy(MockProvider("jev"), MockProvider("llm")),
}


class UnknownStrategy(ValueError):
    """Kayıt defterinde olmayan (veya ücretli) bir strateji istendi."""


def build_free_strategy(name: str) -> object:
    try:
        builder = FREE_STRATEGY_BUILDERS[name]
    except KeyError:
        raise UnknownStrategy(f"Bilinmeyen veya ücretsiz olmayan strateji: {name!r}") from None
    return builder()
