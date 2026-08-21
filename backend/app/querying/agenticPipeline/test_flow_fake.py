from crewai_agents.flow import QueryOrchestrationFlow
from crewai_agents.models import SearchDecision, SearchType, SubQuery, SubQueryPlan
from crewai_agents.strategies import IQueryClassifier, IQueryRewriter
from crewai_agents.registry import RewriterRegistry
from crewai_agents.config import DEFAULT_CONFIG


class FakeClassifier(IQueryClassifier):
    def classify(self, state):
        return SearchDecision(
            search_type=SearchType.HYBRID,
            reasoning="contains an invoice number",
            requires_decomposition=True,
        )


class FakeHybridRewriter(IQueryRewriter):
    def rewrite(self, state):
        return SubQueryPlan(
            search_type=SearchType.HYBRID,
            sub_queries=[
                SubQuery(query="Fe500D vs Fe550D yield strength", top_k=5),
                SubQuery(query="warranty period invoice SRMB-2291", top_k=3),
            ],
        )


registry = RewriterRegistry(DEFAULT_CONFIG)
registry.register(SearchType.HYBRID, lambda cfg: FakeHybridRewriter())

flow = QueryOrchestrationFlow(classifier=FakeClassifier(), rewriter_registry=registry)
flow.state.current_message = "Compare Fe500D vs Fe550D, and warranty for invoice #SRMB-2291"
flow.kickoff()

assert flow.state.error is None
assert flow.state.decision.search_type == SearchType.HYBRID
assert len(flow.state.plan.sub_queries) == 2
print("✅ routing works:", flow.result().model_dump())