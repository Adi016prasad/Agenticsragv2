import os
import uuid
import time
import functools
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Union
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

def retry(max_attempts=3, delay=1, backoff=2, exceptions=(Exception,)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    logger.warning(
                        "Attempt %d/%d failed for %s: %s",
                        attempt, max_attempts, func.__name__, e
                    )
                    if attempt < max_attempts:
                        time.sleep(current_delay)
                        current_delay *= backoff

            logger.error("All %d attempts failed for %s", max_attempts, func.__name__)
            raise last_exception

        return wrapper
    return decorator


class VectorDatabase(ABC):

    @abstractmethod
    def searchInVectorDatabase(self, query: str, collectionName: str, limit: Optional[int] = None) -> list[str]:
        pass

    @abstractmethod
    def batch_search_with_top_k_grouping(self, agent_plan_data: Any, collectionName: str) -> list[str]:
        pass

    @abstractmethod
    def closeTheClient(self) -> None:
        pass

    @abstractmethod
    def ensure_collection_exists(self, collectionName: str) -> bool:
        pass


class QudrantVectorDatabase(VectorDatabase):

    def __init__(
        self,
        client: QdrantClient,
        version: Optional[str] = None
    ):
        self.client = client
        self.version = version or os.getenv("VERSION")
        self.dense_name = "dense"
        self.sparse_name = "sparse"

    @retry(max_attempts=3, delay=2, backoff=2, exceptions=(Exception,))
    def ensure_collection_exists(self, collectionName: str) -> bool:
        if self.client.collection_exists(collectionName):
            return True
        return False

    def _build_search_request(self, query: str, limit: int) -> models.QueryRequest:
        """Helper to build a hybrid (dense + sparse with RRF) query request."""
        return models.QueryRequest(
            prefetch=[
                models.Prefetch(
                    query=models.Document(
                        text=query,
                        model=os.getenv("DENSEMODEL")
                    ),
                    using="dense",
                    score_threshold=float(os.getenv("SCORETHRESHOLD", 0.5))
                ),
                models.Prefetch(
                    query=models.Document(
                        text=query,
                        model=os.getenv("SPARESEMODEL")
                    ),
                    using="sparse",
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit
        )

    @retry(max_attempts=3, delay=2, backoff=2, exceptions=(Exception,))
    def searchInVectorDatabase(self, query: str, collectionName: str, limit: Optional[int] = None) -> list[str]:
        """Performs a single hybrid vector search."""
        try:
            actual_limit = limit if limit is not None else int(os.getenv("LIMIT", 5))
            result = self.client.query_points(
                collection_name=collectionName,
                prefetch=[
                    models.Prefetch(
                        query=models.Document(
                            text=query,
                            model=os.getenv("DENSEMODEL")
                        ),
                        using="dense",
                        score_threshold=float(os.getenv("SCORETHRESHOLD", 0.5))
                    ),
                    models.Prefetch(
                        query=models.Document(
                            text=query,
                            model=os.getenv("SPARESEMODEL")
                        ),
                        using="sparse",
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=actual_limit
            )
            parent_texts = [point.payload.get("parent_text") for point in result.points if point.payload]
            unique = set(parent_texts)
            logger.info(f"Single search for '{query[:30]}...' -> Retrieved {len(parent_texts)} ({len(unique)} unique) with top_k={actual_limit}")
            return list(unique)
        except Exception as e:
            logger.error(f"Error during search in vector database: {e}")
            raise e

    @retry(max_attempts=3, delay=2, backoff=2, exceptions=(Exception,))
    def batch_search_with_top_k_grouping(self, agent_plan_data: Any, collectionName: str) -> list[str]:
        """
        Parses sub-queries from the AI agent, groups queries by matching top_k, 
        performs batch querying in Qdrant for matching top_k groups, executes 
        single queries independently, and returns globally deduplicated text.
        """
        # 1. Parse and extract (query, top_k) pairs from agent output
        extracted_pairs: List[tuple[str, int]] = []

        # Handle SubQueryPlan Pydantic object
        if hasattr(agent_plan_data, "sub_queries"):
            for sq in agent_plan_data.sub_queries:
                q = getattr(sq, "query", "")
                k = getattr(sq, "top_k", int(os.getenv("LIMIT", 5)))
                if q:
                    extracted_pairs.append((q.strip(), int(k)))

        # Handle Dictionary or List format
        elif isinstance(agent_plan_data, dict) and "sub_queries" in agent_plan_data:
            for sq in agent_plan_data["sub_queries"]:
                q = sq.get("query", "")
                k = sq.get("top_k", int(os.getenv("LIMIT", 5)))
                if q:
                    extracted_pairs.append((q.strip(), int(k)))

        elif isinstance(agent_plan_data, list):
            for item in agent_plan_data:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    extracted_pairs.append((str(item[0]).strip(), int(item[1])))
                elif hasattr(item, "query"):
                    extracted_pairs.append((item.query.strip(), int(getattr(item, "top_k", 5))))

        if not extracted_pairs:
            logger.warning("No valid sub-queries found in agent plan data.")
            return []

        # 2. Group queries by top_k
        top_k_groups: Dict[int, List[str]] = defaultdict(list)
        for q, k in extracted_pairs:
            top_k_groups[k].append(q)

        logger.info(f"Grouped {len(extracted_pairs)} sub-queries into {len(top_k_groups)} distinct top_k groups: {dict(top_k_groups)}")

        all_parent_texts: List[str] = []

        # 3. Process each top_k group
        for top_k, queries in top_k_groups.items():
            # If multiple queries share the same top_k -> BATCH SEARCH
            if len(queries) > 1:
                logger.info(f"⚡ Batch searching {len(queries)} queries with matched top_k={top_k}")
                requests = [self._build_search_request(q, limit=top_k) for q in queries]
                try:
                    batch_results = self.client.query_batch_points(
                        collection_name=collectionName,
                        requests=requests
                    )
                    for res in batch_results:
                        texts = [point.payload.get("parent_text") for point in res.points if point.payload]
                        all_parent_texts.extend(texts)
                except Exception as e:
                    logger.error(f"Batch query failed for top_k={top_k}: {e}. Falling back to independent searches.")
                    for q in queries:
                        all_parent_texts.extend(self.searchInVectorDatabase(q, collectionName, limit=top_k))

            # If only 1 query has this top_k -> INDEPENDENT SEARCH
            else:
                q = queries[0]
                logger.info(f"🔍 Searching single query independently with unique top_k={top_k}: '{q[:30]}...'")
                all_parent_texts.extend(self.searchInVectorDatabase(q, collectionName, limit=top_k))

        # 4. Global Deduplication across all sub-queries
        seen = set()
        unique_texts = [t for t in all_parent_texts if t and not (t in seen or seen.add(t))]
        logger.info(f"🎉 Total retrieved chunks: {len(all_parent_texts)} | Globally unique chunks returned: {len(unique_texts)}")
        return unique_texts

    @retry(max_attempts=3, delay=2, backoff=2, exceptions=(Exception,))
    def closeTheClient(self) -> None:
        self.client.close()

    @staticmethod
    def _generate_uuid(raw_id: Optional[str]) -> str:
        point_id = raw_id or str(uuid.uuid4())
        try:
            uuid.UUID(str(point_id))
            return str(point_id)
        except ValueError:
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(point_id)))