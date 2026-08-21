"""
Strategy interfaces for query classification and rewriting.

The Flow (flow.py) depends ONLY on these abstractions, never on
concrete Agent/Task/Crew objects (Dependency Inversion Principle).
That indirection is also what gives us the Open/Closed Principle in
practice: a brand-new retrieval strategy (e.g. "graph" search) is a
new class implementing IQueryRewriter plus one registry entry —
zero changes to flow.py.

Both interfaces are intentionally narrow (Interface Segregation): a
classifier only classifies, a rewriter only rewrites. Nothing is
forced to implement methods it doesn't need.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .models import OrchestrationState, SearchDecision, SubQueryPlan


class IQueryClassifier(ABC):
    """Decides which retrieval strategy a query needs."""

    @abstractmethod
    def classify(self, state: OrchestrationState) -> SearchDecision:
        """Return a SearchDecision for the current turn in `state`."""
        raise NotImplementedError


class IQueryRewriter(ABC):
    """Rewrites/decomposes a query into executable sub-queries.

    Any concrete implementation (LSP) must be substitutable wherever
    an IQueryRewriter is expected — the registry and the Flow never
    branch on *which* concrete class they hold.
    """

    @abstractmethod
    def rewrite(self, state: OrchestrationState) -> SubQueryPlan:
        """Return a SubQueryPlan for the current turn in `state`."""
        raise NotImplementedError