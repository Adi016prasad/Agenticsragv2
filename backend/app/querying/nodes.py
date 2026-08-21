import logging
from typing import Any, Optional
from pydantic import ValidationError
from langgraph.graph import MessagesState
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, RemoveMessage
from langchain_core.exceptions import OutputParserException
import tiktoken
import os
import uuid  # <-- ADDED THIS CRITICAL IMPORT TO PREVENT NameError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DELTA_INCREAMENT = int(os.getenv("DELTA_INCREAMENT", "400"))
max_attempts = int(os.getenv("MAXIMUMCLARIFICATIONATTEMPTS", "3"))

class GraphState(MessagesState):
    session_id : str
    collection_name : str
    tool_needed : bool
    inputTokens : int
    outputTokens : int
    totalTokens : int
    approved: bool
    conversationSummary : str
    messagesForLLM : list
    lastSummaryIndex: int
    document_found : bool
    clarification_attempts : int
    rewrittenQueryforVectorsearch : Optional[str]
    MAXIMUM_TOTAL_TOKENS_THRESHOLD : int

def _count_tokens(messages) -> int:
    """Approximate token count using tiktoken's cl100k_base encoding."""
    encoding = tiktoken.get_encoding("cl100k_base")
    total = 0
    for m in messages:
        content = m.content if isinstance(m.content, str) else str(m.content)
        total += len(encoding.encode(content))
    return total

async def token_calculator(state: GraphState) -> dict[str, Any]:
    logger.info("Inside token_calculator")
    messages = state.get("messages", [])
    total_tokens = _count_tokens(messages)
    logger.info(f"Total tokens in conversation so far: {total_tokens}")
    return {
        "totalTokens": total_tokens
    }

def route_after_token_calculator(state: GraphState) -> str:
    threshold = state.get("MAXIMUM_TOTAL_TOKENS_THRESHOLD") or 400
    if state.get("totalTokens", 0) >= threshold :
        return "human_approval"
    return "generate_response"

async def send_approval_email_node(
    state: GraphState,
    runtime: Runtime
) -> dict[str, Any]:

    from email_utils import send_approval_email

    session_id = state.get("session_id")
    total_tokens = state.get("totalTokens")

    logger.info(
        f"Sending approval email for session_id={session_id}"
    )

    try:
        await send_approval_email(
            session_id=session_id,
            total_tokens=total_tokens
        )
        logger.info(f"Approval email sent for session_id={session_id}")
    except Exception as e:
        logger.error(
            f"Failed to send approval email: {e}",
            exc_info=True
        )

    return {}

async def human_approval_node(state: GraphState, runtime: Runtime) -> dict[str, Any]:
    logger.info("Inside human_approval_node — waiting for human approval")

    decision = interrupt({
        "reason": "token_threshold_exceeded",
        "totalTokens": state.get("totalTokens"),
        "session_id": state.get("session_id"),
        "message": "Waiting for human approval before continuing (token budget exceeded)",
    })

    approved = str(decision).strip().lower() in (
        "yes", "true", "approve", "approved"
    )

    logger.info(
        f"human_approval_node resumed with decision={decision!r}"
        f"-> approved={approved}"
    )

    current_threshold = (
        state.get("MAXIMUM_TOTAL_TOKENS_THRESHOLD") or 400
    )
    new_threshold = current_threshold + DELTA_INCREAMENT

    return {
        "approved": approved,
        "MAXIMUM_TOTAL_TOKENS_THRESHOLD": new_threshold
    }

def route_after_human_approval(state: GraphState) -> str:
    return "generate_response" if state.get("approved") else "__end__"

async def _summarize_messages(older_messages, previous_summary: str = "") -> str:
    logger.info("=================== INSIDE _summarize_messages node for the summarization ===================")
    from container import get_container
    container = get_container()

    convo_text = "\n".join(
        f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content}"
        for m in older_messages
    )

    previous_summary_block = (
        f"Previous summary (carry forward any still relevant facts):\n{previous_summary}\n\n"
        if previous_summary else ""
    )

    summary_prompt = (
        "This is the previous conversation history\n\n"
        f"{previous_summary_block}"
        f"Now Conversation to summarize is \n{convo_text}"
    )

    try:
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", "You are a conversation summarizer, analyze it carefully and extract each important conversation keywords which took place between user and assistant, give the summary in detail covering each point in string"),
            ("human", "{summary_prompt}"),
        ])
        structuredllm = container.llm.rawllm()
        chain = prompt_template | structuredllm

        logger.info("************************ Previous summary are ********************************************")
        logger.info(previous_summary)
        logger.info("************************ Previous summary ends here ********************************************")

        logger.info("************************ The messages will is sent to be summarized are ********************************************")
        for olderMessage in older_messages :
            logger.info(olderMessage)
        logger.info("************************ The messages are sent to be summarized ********************************************")

        config = {
            "headers": {
                "X-Request-ID": str(uuid.uuid4())
            }
        }
        
        output = await chain.ainvoke({"summary_prompt": summary_prompt}, config = config)

        if output:
            summary = output.content
            logger.info(f"[_summarize_messages] Generated summary ({len(summary)} chars)")
            return summary
        return previous_summary
    except Exception as e:
        logger.error(f"[_summarize_messages] Failed to generate summary: {e}", exc_info=True)
        return previous_summary

async def conversation_summary_node(state: GraphState, runtime: Runtime) -> dict[str, Any]:
    logger.info("=================== INSIDE conversation_summary_node ===================")
    messages = state["messages"]

    if len(messages) <= 10:
        return {}

    logger.info("Going to summarize the message as the history has crossed more than 10 messages")
    logger.info(f"Message count = {len(messages)} — summarizing older messages")
    previous_summary = state.get("conversationSummary", "")
    older_messages = messages[:-1]

    new_summary = await _summarize_messages(older_messages, previous_summary)
    logger.info(f"New conversation summary: {new_summary}")

    return {
        "conversationSummary": new_summary,
        "messages": [RemoveMessage(id=m.id) for m in older_messages]
    }

async def generate_response_node(state: GraphState, runtime: Runtime) -> dict[str, Any]:
    from container import get_container
    try:
        logger.info("=================== INSIDE generate_response_node ===================")
        container = get_container()

        summary = state.get("conversationSummary", "")
        system_prompt = container.prompt_provider.systemprompt()
        if summary:
            logger.info("Got the conversation summary, appending in the system message")
            system_prompt += f"\n\nConversation summary so far: {summary}"

        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ])

        formatted_messages = await prompt_template.aformat_messages(messages=state["messages"])

        logger.info(f"-------- CURRENT CONVERSATION HISTORY SENT TO LLM ({len(formatted_messages)} messages | Summary present: {bool(summary)}) --------")
        for idx, msg in enumerate(formatted_messages):
            logger.info(f"[{idx}] TYPE: {msg.type.upper()} | CONTENT:\n{msg.content}\n{'-'*40}")

        logger.info(f"-------- CURRENT CONVERSATION HISTORY SENT TO LLM ENDS HERE --------")
        
        structuredLLM = container.llm.structuredllm()
        chain = prompt_template | structuredLLM

        config = {
            "headers": {
                "X-Request-ID": str(uuid.uuid4())
            }
        }
        
        output = await chain.ainvoke({"messages": state["messages"]}, config = config)
        logger.info(f"--- LLM RAW OUTPUT ---\n{output}")
        logger.info("=======================================================================")

        is_tool_needed = getattr(output, "tool_needed", False)
        rewrittenQueryforVectorsearch = getattr(output, "rewrittenQueryforVectorsearch", "")

        if rewrittenQueryforVectorsearch :
            logger.info("-------------------------------------------------------------------")
            logger.info(f"Rewritten query is \n{rewrittenQueryforVectorsearch}")
            logger.info("-------------------------------------------------------------------")

        return {
            "messages": [AIMessage(content=output.model_dump_json())],
            "tool_needed": is_tool_needed,
            "rewrittenQueryforVectorsearch" : rewrittenQueryforVectorsearch
        }

    except (ValidationError, OutputParserException) as e:
        logger.warning(f"Model declined/failed structured output: {e}")
        return {
            "messages": [AIMessage(content="I can't provide an answer to this request")],
            "tool_needed": False
        }

    except Exception as e:
        logger.error(f"Error in generate_response_node: {e}", exc_info=True)
        return {
            "messages": [AIMessage(content="An error occurred while generating the response")],
            "tool_needed": False
        }

def route_after_generate(state: GraphState) -> str:
    return "tool_node" if state.get("tool_needed") else "__end__"

async def tool_node(state: GraphState, runtime: Runtime) -> dict[str, Any]:
    logger.info("Inside tool_node")
    collection_name = state.get("collection_name", "")
    if not collection_name:
        logger.warning("No collection name provided in state")
        return {"messages": [AIMessage(content="No collection name provided in state")]}

    queryForVectorSearch = state.get("rewrittenQueryforVectorsearch", "")
    if queryForVectorSearch.strip() == "":
        logger.warning("No query found for vector search")
        return {"messages": [AIMessage(content = "The query is missing for vector search")]}

    from container import get_container
    container = get_container()
    isPresent = container.vector_db.ensure_collection_exists(collectionName=collection_name)
    if not isPresent:
        logger.warning(f"Collection '{collection_name}' does not exist in the vector database")
        return {"messages": [AIMessage(content=f"Collection '{collection_name}' does not exist in the vector database")]}

    result = container.vector_db.searchInVectorDatabase(query=queryForVectorSearch, collectionName=collection_name)
    realResult = await container.llm.filteringresultwithLLM(result, queryForVectorSearch)
    new_attempts = 0 if realResult.isAnswerFound else state.get("clarification_attempts", 0) + 1

    logger.info(f"realResult output is {realResult.output}")
    logger.info(f"realResult isAnswerFound is {realResult.isAnswerFound}")
    logger.info(f"Clarification attempts is {state.get('clarification_attempts', 0)}")
    logger.info(f"New attempt currently going is {new_attempts}")

    return {
        "messages": [AIMessage(content=realResult.output)],
        "document_found": realResult.isAnswerFound,
        "clarification_attempts": new_attempts
    }

def after_tool_node_execution_decision(state : GraphState) -> str :
    if state.get("clarification_attempts", 0) >= max_attempts :
        logger.info("AGENTIC PIPELINE HAS CAME INTO ACTION")
        return "trigger_agentic_group"
    return "__end__"

async def trigger_agentic_group(state: GraphState, runtime: Runtime) -> dict[str, Any]:
    logger.info("Inside trigger_agentic_group")
    logger.info(state)
    return {
        "messages": [AIMessage(content="AGENTIC PIPELINE HAS CAME INTO ACTION")],
        "clarification_attempts": 0
    }