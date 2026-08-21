import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from nodes import GraphState
from container import build_container, close_container, get_container, AppContainer
from fastapi.middleware.cors import CORSMiddleware
from langgraph.types import Command
import uuid
import json

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = await build_container()
    logger.info("-----------------------------------------------")
    logger.info(container)
    logger.info("-----------------------------------------------")

    # logger.info("Warming up LLM connection (TLS/Credentials)...")
    # try:
    #     await container.llm.sendMessagestollm("warmup_session", "Hi")
    #     logger.info("LLM connection warmed up successfully!")
    # except Exception as e:
    #     logger.warning(f"LLM warmup failed (continuing anyway): {e}")

    yield

    await close_container()


app = FastAPI(
    title="LangGraph Complex Workflow Example",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # your frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RequestStructure(BaseModel):
    session_id: str
    user_input: str
    collection_name: str

@app.get("/approve")
async def approve_endpoint(
    session_id: str,
    decision: str,
    container: AppContainer = Depends(get_container),
):
    config = {
        "configurable": {
            "thread_id": f"user_name_{session_id}"
        }
    }

    try:
        final_state = await container.query_graph.ainvoke(
            Command(resume=decision),
            config=config
        )

        is_approved = decision.lower() in (
            "yes",
            "true",
            "approve",
            "approved"
        )

        status = "approved" if is_approved else "denied"

        output = ""

        if final_state.get("messages"):
            output = final_state["messages"][-1].content

        # Store approval result separately in Firestore
        firestore_client = container.query_graph.checkpointer.client

        firestore_client \
            .collection("approval_status") \
            .document(session_id) \
            .set({
                "session_id": session_id,
                "status": status,
                "output": output,
            })

        logger.info(
            f"Approval stored | session_id={session_id} "
            f"| status={status}"
        )

        return {
            "status": status,
            "output": output
        }

    except Exception as e:
        logger.error(
            f"Error resuming graph for session_id={session_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@app.get("/approval-status")
async def approval_status(
    session_id: str,
    container: AppContainer = Depends(get_container),
):
    try:
        firestore_client = container.query_graph.checkpointer.client

        doc = (
            firestore_client
            .collection("approval_status")
            .document(session_id)
            .get()
        )

        if not doc.exists:
            return {
                "status": "awaiting_approval"
            }

        data = doc.to_dict()

        return {
            "status": data.get("status", "awaiting_approval"),
            "output": data.get("output", "")
        }

    except Exception as e:
        logger.error(
            f"Error checking approval status for "
            f"session_id={session_id}: {e}",
            exc_info=True
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@app.post("/chat")
async def chat_endpoint(
    request: RequestStructure,
    container: AppContainer = Depends(get_container),
):
    if not request.user_input.strip():
        raise HTTPException(status_code=400, detail="user_input cannot be empty.")

    initial_state: GraphState = {
        "session_id": request.session_id,
        "collection_name": request.collection_name,
        "messages": [HumanMessage(content=request.user_input)]
    }

    config = {
        "configurable": {"thread_id": f"user_name_{request.session_id}"}
    }

    try:
        final_state = await container.query_graph.ainvoke(initial_state, config = config)
        if "__interrupt__" in final_state:
            interrupt_info = final_state["__interrupt__"][0].value
            return {"status": "awaiting_approval", "detail": interrupt_info}

        content = final_state["messages"][-1].content

        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "llm_responseLanggraph" in parsed:
                output = parsed["llm_responseLanggraph"]
            else:
                output = content
        except json.JSONDecodeError:
            output = content

        return {
            "output": output
        }

    except Exception as e:
        logger.error(f"Error in chat_endpoint: {e}")
        raise HTTPException(status_code = 500, detail = str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host = "0.0.0.0",
        port = 8001,
        reload = True
    )