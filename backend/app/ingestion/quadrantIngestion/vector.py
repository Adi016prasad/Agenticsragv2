import os
import uuid
import time
import functools
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from dotenv import load_dotenv
from qdrant_client import QdrantClient, models

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
    def insertVectorsInBatch(self, doc: Any, chunks_data: List[Dict[str, Any]], collectionName : str) -> bool:
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
        dense_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        sparse_model: str = "qdrant/bm25",
        dense_vector_size: int = 384,
        batch_size: int = 40,
        version: Optional[str] = None,
    ):
        self.client = client
        self.dense_model = dense_model
        self.sparse_model = sparse_model
        self.dense_vector_size = dense_vector_size
        self.batch_size = batch_size
        self.version = version or os.getenv("VERSION")
        self.dense_name = "dense"
        self.sparse_name = "sparse"

    @retry(max_attempts = 3, delay = 2, backoff = 2, exceptions = (Exception,))
    def ensure_collection_exists(self, collectionName : str) -> bool :
        """Creates a hybrid (dense + sparse) collection if it does not exist."""

        if self.client.collection_exists(collectionName):
            return True

        else :
            try :
                logger.info("Collection '%s' not found Creating hybrid collection...", collectionName)
                self.client.create_collection(
                    collection_name=collectionName,
                    vectors_config={
                        self.dense_name: models.VectorParams(
                            size=self.dense_vector_size,
                            distance=models.Distance.COSINE,
                        )
                    },
                    sparse_vectors_config={
                        self.sparse_name: models.SparseVectorParams(
                            modifier=models.Modifier.IDF,
                        )
                    }
                )
                logger.info("Hybrid Collection '%s' created successfully.", collectionName)
                return True

            except Exception as e :
                logger.error(f"An exception has occured {e}")
                return False

    @retry(max_attempts = 3, delay = 2, backoff = 2, exceptions = (Exception,))
    def insertVectorsInBatch(self, doc: Any, chunks_data: List[Dict[str, Any]], collectionName : str) -> bool:
        try:
            batch_ids = []
            batch_dense = []
            batch_sparse = []
            batch_payloads = []

            for chunk in chunks_data:
                text = chunk.get("text")
                if not text:
                    logger.warning("Skipping chunk with no text: %s", chunk.get("chunk_id"))
                    continue

                point_id = self._generate_uuid(chunk.get("chunk_id"))
                batch_ids.append(point_id)
                
                # Assign inference models to dense and sparse representations
                batch_dense.append(models.Document(text=text, model=self.dense_model))
                batch_sparse.append(models.Document(text=text, model=self.sparse_model))

                batch_payloads.append({
                    "chunk_type": chunk.get("chunk_type"),
                    "text": text,
                    "parent_text": chunk.get("parent_text"),
                    "version": self.version,
                    "time": datetime.now(timezone.utc).isoformat()
                })

                if len(batch_ids) == self.batch_size:
                    self._upsert_batch(batch_ids, batch_dense, batch_sparse, batch_payloads, collectionName)
                    # Reset batches
                    batch_ids, batch_dense, batch_sparse, batch_payloads = [], [], [], []

            # Upsert any remaining points in the final partial batch
            if batch_ids:
                self._upsert_batch(batch_ids, batch_dense, batch_sparse, batch_payloads, collectionName)
                batch_ids, batch_dense, batch_sparse, batch_payloads = [], [], [], []

            return True

        except Exception as e:
            logger.exception("Failed to insert vectors in batch: %s", e)
            self.closeTheClient()
            return False

    @retry(max_attempts = 3, delay = 2, backoff = 2, exceptions = (Exception,))
    def _upsert_batch(self, ids: list, dense_docs: list, sparse_docs: list, payloads: list, collectionName : str) -> None:
        self.client.upsert(
            collection_name = collectionName,
            points = models.Batch(
                ids = ids,
                vectors = {
                    self.dense_name: dense_docs,
                    self.sparse_name: sparse_docs
                },
                payloads = payloads,
            ),
        )
        logger.info("Upserted batch of %d hybrid points into '%s'", len(ids), collectionName)

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