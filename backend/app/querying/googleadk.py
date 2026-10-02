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
from google.adk.agents import Agent

listoftools = []

firstAgentResponse = Agent(
    model = "gemini-3.6-flash",
    name = "firstAgent",
    description = "You are a helpful assistant that can create users in the system. Use the provided tools to perform actions",
    instruction = "You are a helpful assistant that can create users in the system. Use the provided tools to perform actions",
    tools = listoftools
)

from google.genai import types
from google.adk.runners import Runner
from google.adk.planners import BuiltInPlanner, PlanReActPlanner, BasePlanner
from google.adk.agents.llm_agent import LlmAgent
from google.adk.sessions import InMemorySessionService

thinkingConfig = types.ThinkingConfig(
    include_thoughts = True,
    thinking_budget = 1000
)

planner = BuiltInPlanner(
    thinking_config=thinkingConfig
)

secondAgentResponse = LlmAgent(
    model = "gemini-3.6-flash",
    name = "secondAgent",
    description = "You are a helpful assistant that can create users in the system. Use the provided tools to perform actions",
    instruction = "You are a helpful assistant that can create users in the system. Use the provided tools to perform actions",
    tools = listoftools,
    planner = planner,
    include_contents = True
)

session = InMemorySessionService()
session_services = session.create_session(app_name = "myapp", user_id= "user123", session_id = "session123")
runner = Runner(agent = secondAgentResponse, app_name = "myapp", session_service = session)

#.............................................
from google.adk.agents import LoopAgent, LlmAgent, SequentialAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.agents.callback_context import CallbackContext

# --- Constants ---
GEMINI_MODEL = "gemini-2.5-flash"

# --- State Keys ---
STATE_CURRENT_DOC = "current_document"
STATE_CRITICISM = "criticism"
# Define the exact phrase the Critic should use to signal completion
COMPLETION_PHRASE = "No major issues found."

# --- Tool Definition ---
def exit_loop(tool_context: ToolContext):
    """Call this function ONLY when the critique indicates no further changes are needed, signaling the iterative process should end."""
    print(f"  [Tool Call] exit_loop triggered by {tool_context.agent_name}")
    tool_context.actions.escalate = True
    tool_context.actions.skip_summarization = True
    # Return empty dict as tools should typically return JSON-serializable output
    return {}

# --- Before Agent Callback ---
def update_initial_topic_state(callback_context: CallbackContext):
    """Ensure 'initial_topic' is set in state before pipeline starts."""
    callback_context.state['initial_topic'] = callback_context.state.get('initial_topic', 'a robot developing unexpected emotions')

# --- Agent Definitions ---

# STEP 1: Initial Writer Agent (Runs ONCE at the beginning)
initial_writer_agent = LlmAgent(
    name="InitialWriterAgent",
    model=GEMINI_MODEL,
    include_contents='none',
    instruction=f"""
    You are a Creative Writing Assistant tasked with starting a story.
    Write a *very basic* first draft of a short story (just 1-2 simple sentences).
    Keep it plain and minimal - do NOT add descriptive language yet.
    Topic: {{initial_topic}}

    Output *only* the story/document text. Do not add introductions or explanations.
    """,
    description="Writes the initial document draft based on the topic, aiming for some initial substance.",
    output_key=STATE_CURRENT_DOC
)

# STEP 2a: Critic Agent (Inside the Refinement Loop)
critic_agent_in_loop = LlmAgent(
    name="CriticAgent",
    model=GEMINI_MODEL,
    include_contents='none',
    instruction=f"""
    You are a Constructive Critic AI reviewing a short story draft.

    **Document to Review:**
    ```
    {{current_document}}
    ```

    **Completion Criteria (ALL must be met):**
    1. At least 4 sentences long
    2. Has a clear beginning, middle, and end
    3. Includes at least one descriptive detail (sensory or emotional)

    **Task:**
    Check the document against the criteria above.

    IF any criteria is NOT met, provide specific feedback on what to add or improve.
    Output *only* the critique text.

    IF ALL criteria are met, respond *exactly* with: "{COMPLETION_PHRASE}"
    """,
    description="Reviews the current draft, providing critique if clear improvements are needed, otherwise signals completion.",
    output_key=STATE_CRITICISM
)

# STEP 2b: Refiner/Exiter Agent (Inside the Refinement Loop)
refiner_agent_in_loop = LlmAgent(
    name="RefinerAgent",
    model=GEMINI_MODEL,
    # Relies solely on state via placeholders
    include_contents='none',
    instruction=f"""
    You are a Creative Writing Assistant refining a document based on feedback OR exiting the process.
    **Current Document:**
    ```
    {{current_document}}
    ```
    **Critique/Suggestions:**
    {{criticism}}

    **Task:**
    Analyze the 'Critique/Suggestions'.
    IF the critique is *exactly* "{COMPLETION_PHRASE}":
    You MUST call the 'exit_loop' function. Do not output any text.
    ELSE (the critique contains actionable feedback):
    Carefully apply the suggestions to improve the 'Current Document'. Output *only* the refined document text.

    Do not add explanations. Either output the refined document OR call the exit_loop function.
    """,
    description="Refines the document based on critique, or calls exit_loop if critique indicates completion.",
    tools=[exit_loop], # Provide the exit_loop tool
    output_key=STATE_CURRENT_DOC # Overwrites state['current_document'] with the refined version
)

# STEP 2: Refinement Loop Agent
refinement_loop = LoopAgent(
    name="RefinementLoop",
    # Agent order is crucial: Critique first, then Refine/Exit
    sub_agents=[
        critic_agent_in_loop,
        refiner_agent_in_loop,
    ],
    max_iterations=5 # Limit loops
)

# STEP 3: Overall Sequential Pipeline
# For ADK tools compatibility, the root agent must be named `root_agent`
root_agent = SequentialAgent(
    name="IterativeWritingPipeline",
    sub_agents=[
        initial_writer_agent, # Run first to create initial doc
        refinement_loop       # Then run the critique/refine loop
    ],
    before_agent_callback=update_initial_topic_state, # set initial topic in state
    description="Writes an initial document and then iteratively refines it with critique using an exit tool."
)
#.............................................

from google.adk.agents import Agent
from google.adk.models import Gemini, LlmRequest, RoutedLlm
primary_model = Gemini(model_name="gemini-3.6-flash")
fallback_model = Gemini(model_name="gemini-3.6-flash")

def myrouter(models, request: LlmRequest, error_context=None):
    if error_context is None:
        return "primary"  # Initial attempt
    
    # Check if primary failed and fall back
    if "primary" in error_context.failed_keys:
        return "fallback"
        
    return None  # Stop retrying and propagate error

routedmodel = RoutedLlm(
    models = {
        "primary": primary_model, "fallback" : fallback_model
    },
    router = myrouter
)
agentwithfallback = Agent(
    name = "AgentWithFallback",
    model = routedmodel,
    description = "You are a helpful assistant that can create users in the system. Use the provided tools to perform actions"
)