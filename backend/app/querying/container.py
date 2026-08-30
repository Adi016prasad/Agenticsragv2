import os
import logging
from dataclasses import dataclass
from typing import Optional
from google.cloud import firestore
from prompt import PromptFactory, Prompt
from history import ConversationHistory, InMemoryConversationHistory
from classesForllm import LLMFactory, LLMSelection
from graph import create_query_graph, save_graph_image
from classesForQudrant import VectorDatabase, QudrantVectorDatabase
from qdrant_client import QdrantClient, models
from firestore_checkpointer import FirestoreSaver
from agenticPipeline.crewai_agents.prompt_loader import prompt_loader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class AppContainer:
    prompt_provider: Prompt
    history: ConversationHistory
    llm: LLMSelection
    vector_db: VectorDatabase
    query_graph: object
    checkpointer: FirestoreSaver
    pathtosavegraphimage: str = "query_graph.png"

_container: Optional[AppContainer] = None


def get_firestore_client() -> firestore.Client:
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    if key_path:
        return firestore.Client.from_service_account_json(key_path)
    return firestore.Client(project=project_id)


async def build_container() -> AppContainer:
    global _container

    logger.info("Initilaizing the prompt")
    prompt_provider = PromptFactory.create(os.getenv("PROMPT_PROVIDER", "default"))
    logger.info("the prompt got initialized")

    logger.info("Initilaizing the history")
    history = InMemoryConversationHistory()
    logger.info("the history got initialized")

    logger.info("Initilaizing the llm")
    llm = LLMFactory.create(
        os.getenv("LLM_PROVIDER", "bedrock"), prompt_provider, history
    )
    logger.info("the llm got initialized")

    logger.info("Initilaizing the qudrant client")
    client = QdrantClient(
        url=os.getenv("QUADRANT_CLUSTERENDPOINT"),
        api_key=os.getenv("QUADRANTAPIKEY"),
        cloud_inference=True
    )
    vectordatabase = QudrantVectorDatabase(client=client)
    logger.info("the qudrant vector database got initialized")

    logger.info("Initilaizing the firebase client")
    firestore_client = get_firestore_client()
    checkpointer = FirestoreSaver(client=firestore_client)
    logger.info("the firebase client got initialized")

    logger.info("Pre loading prompt templates using active Firestore client...")
    promptloaded = prompt_loader.load_all_prompts(db=firestore_client, collection_name="prompt_template")
    if promptloaded > 0 :
        logger.info("Prompt templates cached in memory")
    else :
        logger.info("Some are missed")

    logger.info("Going to initialize the graph")
    query_graph = create_query_graph(checkpointer=checkpointer)
    logger.info("Graph is initialized")

    logger.info(f"Using prompt provider: {prompt_provider.__class__.__name__}")
    logger.info(f"Using LLM provider: {llm.__class__.__name__}")
    logger.info("Query graph compiled successfully with Firestore checkpointer!")

    _container = AppContainer(
        prompt_provider=prompt_provider,
        history=history,
        llm=llm,
        vector_db=vectordatabase,
        query_graph=query_graph,
        checkpointer=checkpointer,
    )

    logger.info(f"Saving query graph image to: {_container.pathtosavegraphimage}")
    save_graph_image(query_graph, _container.pathtosavegraphimage)
    logger.info(f"Graph image saved successfully to: {_container.pathtosavegraphimage}")
    logger.info(f"AppContainer built successfully {_container}")
    return _container


def get_container() -> AppContainer:
    if _container is None:
        raise RuntimeError(
            "Container not initialized. build_container() must run "
            "in lifespan before any request is handled."
        )
    return _container


async def close_container() -> None:
    if _container is not None:
        await _container.llm.close()