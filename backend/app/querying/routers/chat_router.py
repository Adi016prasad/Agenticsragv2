"""
APIRouter handling conversational, stateful LangGraph workflows.
"""
from __future__ import annotations

import logging
import uuid
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from container import get_container, AppContainer
from nodes import GraphState

logger = logging.getLogger("ChatRouter")
router = APIRouter(prefix="/chat", tags=["Conversational Engine"])


class RequestStructure(BaseModel):
    session_id: str
    user_input: str
    collection_name: str


@router.post("")
async def chat_endpoint(
    request: RequestStructure,
    container: AppContainer = Depends(get_container),
):
    if not request.user_input.strip():
        raise HTTPException(status_code=400, detail="user_input cannot be empty.")

    new_request_id = uuid.uuid4().hex[:8]
    initial_state: GraphState = {
        "session_id": request.session_id,
        "collection_name": request.collection_name,
        "messages": [HumanMessage(content=request.user_input)],
        "request_id": new_request_id
    }
    config = {"configurable": {"thread_id": f"user_name_{request.session_id}"}}

    try:
        final_state = await container.query_graph.ainvoke(initial_state, config=config)
        if "__interrupt__" in final_state:
            return {"status": "awaiting_approval", "detail": final_state["__interrupt__"][0].value}

        content = final_state["messages"][-1].content
        try:
            parsed = json.loads(content)
            output = parsed["llm_responseLanggraph"] if isinstance(parsed, dict) and "llm_responseLanggraph" in parsed else content
        except json.JSONDecodeError:
            output = content

        return {
            "output" : output,
            "agentName" : final_state.get("agent_name", "basicRagAgent"),
            "maximum_agentic_effort_reached" : final_state.get("maximum_agentic_effort_reached")
        }
    except Exception as e:
        logger.error(f"Error in chat_endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approve")
async def approve_endpoint(
    session_id: str,
    decision: str,
    container: AppContainer = Depends(get_container),
):
    config = {"configurable": {"thread_id": f"user_name_{session_id}"}}
    try:
        final_state = await container.query_graph.ainvoke(Command(resume=decision), config=config)
        status = "approved" if decision.lower() in ("yes", "true", "approve", "approved") else "denied"
        output = final_state["messages"][-1].content if final_state.get("messages") else ""

        firestore_client = container.query_graph.checkpointer.client
        firestore_client.collection("approval_status").document(session_id).set({
            "session_id": session_id,
            "status": status,
            "output": output,
        })

        return {"status": status, "output": output}
    except Exception as e:
        logger.error(f"Error resuming graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approval-status")
async def approval_status(
    session_id: str,
    container: AppContainer = Depends(get_container),
):
    try:
        firestore_client = container.query_graph.checkpointer.client
        doc = firestore_client.collection("approval_status").document(session_id).get()
        if not doc.exists:
            return {"status": "awaiting_approval"}
        data = doc.to_dict()
        return {"status": data.get("status", "awaiting_approval"), "output": data.get("output", "")}
    except Exception as e:
        logger.error(f"Error checking approval: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))