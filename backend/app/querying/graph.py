# ============================================================
# graph.py
# ============================================================
import os
import logging
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import RetryPolicy, TimeoutPolicy
from nodes import GraphState, generate_response_node, route_after_generate, tool_node, token_calculator, route_after_token_calculator, human_approval_node, route_after_human_approval, send_approval_email_node, conversation_summary_node, after_tool_node_execution_decision, trigger_agentic_group
from agenticPipeline.crewai_agents import trigger_master_orchestration_agent_node, trigger_semantic_agent_node, trigger_hybrid_agent_node, trigger_tool_specific_agent_node

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
global_timeout_policy = TimeoutPolicy(run_timeout=int(os.getenv("GLOBAL_TIMEOUT", 60)), idle_timeout=int(os.getenv("GLOBAL_IDLE_TIMEOUT", 15)))
global_retry_policy = RetryPolicy(
    max_attempts=int(os.getenv("GLOBAL_MAX_ATTEMPTS", 3)),
    initial_interval=float(os.getenv("GLOBAL_INITIAL_INTERVAL", 1.0)),
    backoff_factor=float(os.getenv("GLOBAL_BACKOFF_FACTOR", 2.0))
)

def create_query_graph(checkpointer: BaseCheckpointSaver):
    builder = StateGraph(GraphState)

    builder.add_node(
        "token_calculator",
        token_calculator,
        timeout=global_timeout_policy,
        retry_policy=global_retry_policy
    )

    builder.add_node(
        "send_approval_email",
        send_approval_email_node,
        timeout=global_timeout_policy,
        retry_policy=global_retry_policy
    )

    builder.add_node(
        "human_approval",
        human_approval_node,
        timeout=global_timeout_policy,
        retry_policy=global_retry_policy
    )

    builder.add_node(
        "generate_response",
        generate_response_node,
        timeout=global_timeout_policy,
        retry_policy=global_retry_policy
    )

    builder.add_node(
        "tool_node",
        tool_node,
        timeout=global_timeout_policy,
        retry_policy=global_retry_policy
    )

    builder.add_node("conversation_summary_node", conversation_summary_node, timeout=global_timeout_policy, retry_policy=global_retry_policy)

    builder.add_node("trigger_agentic_group", trigger_agentic_group, timeout=global_timeout_policy, retry_policy=global_retry_policy)

    # Agentic nodes here
    builder.add_node("trigger_master_orchestration_agent_node", trigger_master_orchestration_agent_node, timeout=global_timeout_policy, retry_policy=global_retry_policy)

    builder.add_edge(START, "token_calculator")

    builder.add_conditional_edges(
        "token_calculator",
        route_after_token_calculator,
        {
            "human_approval": "send_approval_email",
            "generate_response": "conversation_summary_node"
        }
    )

    builder.add_edge("send_approval_email", "human_approval")

    builder.add_conditional_edges(
        "human_approval",
        route_after_human_approval,
        {
            "generate_response": "conversation_summary_node",
            "__end__": END
        }
    )

    builder.add_edge("conversation_summary_node", "generate_response")
    
    builder.add_conditional_edges(
        "generate_response",
        route_after_generate,
        {
            "tool_node": "tool_node",
            "__end__": END
        }
    )

    builder.add_conditional_edges(
        "tool_node",
        after_tool_node_execution_decision,
        {
            "__end__" : END,
            "trigger_agentic_group" : "trigger_agentic_group"
        }
    )

    graph = builder.compile(checkpointer=checkpointer)

    logger.info(graph)
    return graph

def save_graph_image(graph, output_path: str) -> None:
    try:
        png_bytes = graph.get_graph().draw_mermaid_png()
        with open(output_path, "wb") as f:
            f.write(png_bytes)
        logger.info(f"Graph successfully saved to: {os.path.abspath(output_path)}")
    except Exception as e:
        logger.error(f"Failed to generate graph PNG: {e}")