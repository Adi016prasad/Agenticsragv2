from google.adk.agents.llm_agent import Agent, LlmAgent
from google.genai import types
from google.adk.planners import BuiltInPlanner, PlanReActPlanner
agent1 = LlmAgent(
    model = "gemini-3.6-flash",
    description = "You are a helpful assistant that can create users in the system. Use the provided tools to perform actions",
    instruction = "You are a helpful assistant that can create users in the system. Use the provided tools to perform actions",
    name = "agent1",
    tools = [],
    generate_content_config = types.GenerateContentConfig(
        top_p = 0.9,
        temperature = 0.7,
        max_output_tokens = 1024,
        stop_sequences = ["\n\n"],
        temperature = 0.7,
        top_k = 40,
        repetition_penalty = 1.2,
        thinking_config = types.ThinkingConfig(
            include_thoughts = True,
            thinking_budget = 1
        )
    )
)

agent2 = LlmAgent(
    model = "gemini-3.6-flash",
    description = "You are a helpful assistant that can create users in the system. Use the provided tools to perform actions",
    instruction = "You are a helpful assistant that can create users in the system. Use the provided tools to perform actions",
    name = "agent2",
    tools = [],
    generate_content_config = types.GenerateContentConfig(
        top_p = 0.9,
        temperature = 0.7,
        max_output_tokens = 1024,
        stop_sequences = ["\n\n"],
        temperature = 0.7,
        top_k = 40,
        repetition_penalty = 1.2,
        thinking_config = types.ThinkingConfig(
            include_thoughts = True,
            thinking_budget = 1
        )
    ),
    planner = BuiltInPlanner(
        thinking_config = types.ThinkingConfig(
            include_thoughts = True,
            thinking_budget = -1
        )
    )
)


# ------------------------
from google.adk import Workflow, Event

# ============================================================================
# 1. NODE FUNCTIONS & STATE MANAGEMENT
# ============================================================================

def generate_draft_node(node_input, ctx):
    """
    NODE 1: Generates or revises content.
    Reads persistent state to know attempt count and previous feedback.
    """
    # Read persistent session state
    attempts = ctx.state.get("attempts", 0) + 1
    feedback = ctx.state.get("feedback", "Initial draft - focus on accuracy.")
    
    # Generate content based on current iteration
    draft_content = f"Draft v{attempts}: ADK Graph Workflows manage state and routes."
    print(f"\n[Writer Node] Attempt #{attempts} | Feedback used: '{feedback}'")

    # Pass output to next node AND update persistent state
    return Event(
        output={"draft": draft_content},
        state={"attempts": attempts} # Updates ctx.state['attempts']
    )


def evaluate_draft_node(node_input, ctx):
    """
    NODE 2: Evaluates the draft quality.
    """
    draft = node_input["draft"]
    attempts = ctx.state.get("attempts", 1)
    
    # Simulated quality score logic (improves on attempt 2)
    score = 65 if attempts == 1 else 85
    feedback_notes = "Needs more depth." if score < 80 else "Quality standards met."
    
    print(f"[Grader Node] Assessed Draft. Score: {score}/100")

    # Return structured output for the router and save feedback to state
    return Event(
        output={"score": score, "draft": draft},
        state={"feedback": feedback_notes} # Persists feedback for next iteration if looped
    )


def quality_router_node(node_input, ctx):
    """
    NODE 3: Conditional Routing & Looping Logic.
    Emits a 'route' signal deciding which node to transition to next.
    """
    score = node_input["score"]
    attempts = ctx.state.get("attempts", 0)

    if score >= 80:
        print("[Router Node] Routing Decision: -> APPROVED")
        return Event(route="approved", output=node_input["draft"])
    
    elif attempts < 3:
        print(f"[Router Node] Routing Decision: -> RETRY (Attempt {attempts}/3)")
        # ROUTE 'retry' points back to generate_draft_node in the workflow graph (LOOP)
        return Event(route="retry", output="Re-drafting required.")
    
    else:
        print("[Router Node] Routing Decision: -> FAILED (Max attempts reached)")
        return Event(route="failed", output="Draft failed quality check after 3 attempts.")


def publish_node(node_input, ctx):
    """NODE 4A: Terminal node on success."""
    print(f"\n PUBLISHED CONTENT: {node_input}")
    return Event(output="Workflow finished successfully.")


def escalate_node(node_input, ctx):
    """NODE 4B: Terminal node on failure."""
    print(f"\n ESCALATED TO HUMAN: {node_input}")
    return Event(output="Workflow failed and escalated.")


# ============================================================================
# 2. WORKFLOW GRAPH DEFINITION (EDGES & ROUTING)
# ============================================================================

# Define conditional route mappings
router_edges = {
    "retry": "generate_draft",   # LOOPING BACK to Node 1!
    "approved": "publish",        # ROUTE to Success Node
    "failed": "escalate"          # ROUTE to Fallback Node
}

# Construct the Workflow Graph
workflow = Workflow(
    name="content_refinement_pipeline",
    edges=[
        # Sequential Flow: Draft -> Evaluate -> Router
        ("START", generate_draft_node, "generate_draft"),
        ("generate_draft", evaluate_draft_node, "evaluate_draft"),
        ("evaluate_draft", quality_router_node, "quality_router"),
        
        # Conditional Flow: Router uses router_edges dictionary to branch
        ("quality_router", router_edges),
        
        # Terminal Node transitions to END
        ("publish", "END"),
        ("escalate", "END")
    ]
)
# ------------------------