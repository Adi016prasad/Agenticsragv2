import os
import uuid
import time
import functools
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
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
    def searchInVectorDatabase(self, query : str, collectionName : str) -> list[str]:
        pass

    @abstractmethod
    def closeTheClient(self) -> None:
        pass

    @abstractmethod
    def ensure_collection_exists(self, collectionName : str) -> bool:
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

    @retry(max_attempts = 3, delay = 2, backoff = 2, exceptions = (Exception,))
    def ensure_collection_exists(self, collectionName : str) -> bool :
        if self.client.collection_exists(collectionName):
            return True
        return False

    @retry(max_attempts = 3, delay = 2, backoff = 2, exceptions = (Exception,))
    def searchInVectorDatabase(self, query : str, collectionName : str) -> list[str]:
        try :
            result = self.client.query_points(
                collection_name = collectionName,
                prefetch = [
                    models.Prefetch(
                        query = models.Document(
                                text = query,
                                model = os.getenv("DENSEMODEL")
                        ),
                        using = "dense",
                        score_threshold = float(os.getenv("SCORETHRESHOLD", 0.5))
                    ),
                    models.Prefetch(
                        query=models.Document(
                            text = query,
                            model = os.getenv("SPARESEMODEL")
                        ),
                        using = "sparse",
                    ),
                ],
                query = models.FusionQuery(fusion = models.Fusion.RRF),
                limit = int(os.getenv("LIMIT", 5))
            )
            parent_texts = [point.payload.get("parent_text") for point in result.points]

            unique = set(parent_texts)
            logger.info(f"Length of the retrieved result is {len(parent_texts)}")
            logger.info(f"Length of the unique retrieved result is {len(unique)}")
            return list(unique)
        except Exception as e :
            logger.error(f"Error during search in vector database: {e}")
            raise e

    @retry(max_attempts = 3, delay = 2, backoff = 2, exceptions = (Exception,))
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

if __name__ == "__main__":
    client = QdrantClient(
        url = os.getenv("QUADRANT_CLUSTERENDPOINT"),
        api_key = os.getenv("QUADRANTAPIKEY"),
        cloud_inference = True
    )
    vector_db = QudrantVectorDatabase(client = client)
    collection_name = "hdfclifesmartpensionplan"
    query = "what is the utilization of death benefit ?"

    if vector_db.ensure_collection_exists(collection_name):
        results = vector_db.searchInVectorDatabase(query, collection_name)
        logger.info("-------------------------------------------")
        logger.info(results)
        logger.info("-------------------------------------------")

    else:
        logger.warning(f"Collection of name {collection_name} does not exist")