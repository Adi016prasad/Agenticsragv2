"""
Registry mapping SearchType -> IQueryRewriter implementation.

This indirection is what gives the system the Open/Closed Principle
in practice: registering a third strategy (e.g. SearchType.GRAPH) is
a one-line `register(...)` call, with no change to flow.py's routing
logic and no growing if/elif chain anywhere.
"""
from __future__ import annotations

from typing import Callable, Dict

from .config import OrchestrationConfig
from .crews import HybridQueryRewriter, SemanticQueryRewriter
from .models import SearchType
from .strategies import IQueryRewriter

RewriterFactory = Callable[[OrchestrationConfig], IQueryRewriter]


class RewriterRegistry:
    """Looks up the correct IQueryRewriter for a given SearchType.

    Defaults to the two production rewriters (semantic, hybrid) but
    accepts additional registrations at runtime, e.g. for tests
    (fakes) or future strategies.
    """

    def __init__(self, config: OrchestrationConfig) -> None:
        self._config = config
        self._factories: Dict[SearchType, RewriterFactory] = {
            SearchType.SEMANTIC: SemanticQueryRewriter,
            SearchType.HYBRID: HybridQueryRewriter,
        }

    def register(self, search_type: SearchType, factory: RewriterFactory) -> None:
        self._factories[search_type] = factory

    def get(self, search_type: SearchType) -> IQueryRewriter:
        try:
            factory = self._factories[search_type]
        except KeyError as exc:
            raise ValueError(f"No rewriter registered for search_type={search_type!r}") from exc
        return factory(self._config)