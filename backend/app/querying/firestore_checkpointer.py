# ============================================================
# firestore_checkpointer.py
# ============================================================
import asyncio
from typing import Any, AsyncIterator, Iterator, Optional, Sequence, Tuple
import json
from google.cloud import firestore
from google.cloud.firestore_v1.async_client import AsyncClient
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
    get_checkpoint_id,
)
from langgraph.checkpoint.serde.base import SerializerProtocol
from langchain_core.runnables import RunnableConfig


class FirestoreSaver(BaseCheckpointSaver):
    """
    Firestore-backed checkpointer.

    Layout:
      threads/{thread_id}/checkpoints/{checkpoint_id}
      threads/{thread_id}/writes/{checkpoint_id}__{task_id}__{idx}
    """

    def __init__(
        self,
        client: firestore.Client,
        async_client: Optional[AsyncClient] = None,
        serde: Optional[SerializerProtocol] = None,
    ):
        super().__init__(serde=serde)
        self.client = client
        self.async_client = async_client  # required for aput/aget/alist

    # ------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------
    def _thread_ref(self, thread_id: str):
        return self.client.collection("threads").document(thread_id)

    def _checkpoints_col(self, thread_id: str):
        return self._thread_ref(thread_id).collection("checkpoints")

    def _writes_col(self, thread_id: str):
        return self._thread_ref(thread_id).collection("writes")

    def _serialize_checkpoint(self, checkpoint: Checkpoint, metadata: CheckpointMetadata) -> dict:
        ckpt_type, ckpt_data = self.serde.dumps_typed(checkpoint)
        meta_type, meta_data = self.serde.dumps_typed(metadata)
        return {
            "type": ckpt_type,
            "checkpoint": ckpt_data,
            "metadata_type": meta_type,
            "metadata": meta_data,
        }

    def _deserialize_checkpoint(self, doc: dict) -> Tuple[Checkpoint, CheckpointMetadata]:
        checkpoint = self.serde.loads_typed((doc["type"], doc["checkpoint"]))
        metadata = self.serde.loads_typed((doc["metadata_type"], doc["metadata"]))
        return checkpoint, metadata

    # ------------------------------------------------------------
    # sync API
    # ------------------------------------------------------------
    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")

        doc = self._serialize_checkpoint(checkpoint, metadata)
        doc.update({
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": parent_checkpoint_id,
            "channel_versions": json.dumps(new_versions, default=str),
        })

        self._checkpoints_col(thread_id).document(checkpoint_id).set(doc)

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"]["checkpoint_id"]

        batch = self.client.batch()
        for idx, (channel, value) in enumerate(writes):
            type_, data = self.serde.dumps_typed(value)
            doc_id = f"{checkpoint_id}__{task_id}__{idx}"
            ref = self._writes_col(thread_id).document(doc_id)
            batch.set(ref, {
                "checkpoint_id": checkpoint_id,
                "task_id": task_id,
                "task_path": task_path,
                "idx": idx,
                "channel": channel,
                "type": type_,
                "value": data,
            })
        batch.commit()

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = get_checkpoint_id(config)

        if checkpoint_id:
            snap = self._checkpoints_col(thread_id).document(checkpoint_id).get()
            if not snap.exists:
                logger.warning(f"[FirestoreSaver] No checkpoint found for thread={thread_id}, checkpoint_id={checkpoint_id}")
                return None
            doc = snap.to_dict()
        else:
            docs = (
                self._checkpoints_col(thread_id)
                .order_by("checkpoint_id", direction=firestore.Query.DESCENDING)
                .limit(1)
                .stream()
            )
            docs = list(docs)
            if not docs:
                logger.warning(f"[FirestoreSaver] No checkpoints exist yet for thread={thread_id}")
                return None
            doc = docs[0].to_dict()

        logger.info(
            f"[FirestoreSaver] LOADED checkpoint from Firestore | "
            f"thread_id={thread_id} | checkpoint_id={doc.get('checkpoint_id')} | "
            f"parent_checkpoint_id={doc.get('parent_checkpoint_id')}"
        )

        checkpoint, metadata = self._deserialize_checkpoint(doc)

        writes_query = self._writes_col(thread_id).where(
            "checkpoint_id", "==", doc["checkpoint_id"]
        ).stream()
        pending_writes = [
            (w.to_dict()["task_id"], w.to_dict()["channel"],
            self.serde.loads_typed((w.to_dict()["type"], w.to_dict()["value"])))
            for w in writes_query
        ]

        parent_config = None
        if doc.get("parent_checkpoint_id"):
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": doc["parent_checkpoint_id"],
                }
            }

        return CheckpointTuple(
            config={"configurable": {"thread_id": thread_id, "checkpoint_id": doc["checkpoint_id"]}},
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=pending_writes,
        )

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        query = self._checkpoints_col(thread_id).order_by(
            "checkpoint_id", direction=firestore.Query.DESCENDING
        )

        if before:
            query = query.where("checkpoint_id", "<", before["configurable"]["checkpoint_id"])
        if limit:
            query = query.limit(limit)

        for snap in query.stream():
            doc = snap.to_dict()
            checkpoint, metadata = self._deserialize_checkpoint(doc)
            if filter and not all(metadata.get(k) == v for k, v in filter.items()):
                continue
            parent_config = None
            if doc.get("parent_checkpoint_id"):
                parent_config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": doc["parent_checkpoint_id"],
                    }
                }
            yield CheckpointTuple(
                config={"configurable": {"thread_id": thread_id, "checkpoint_id": doc["checkpoint_id"]}},
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=parent_config,
            )

    def delete_thread(self, thread_id: str) -> None:
        for snap in self._checkpoints_col(thread_id).stream():
            snap.reference.delete()
        for snap in self._writes_col(thread_id).stream():
            snap.reference.delete()

    # ------------------------------------------------------------
    # async API — wraps sync calls via a thread executor since the
    # google-cloud-firestore async client (AsyncClient) has a parallel
    # but differently-shaped API; wrapping sync is simplest/safest here
    # ------------------------------------------------------------
    async def aput(self, config, checkpoint, metadata, new_versions) -> RunnableConfig:
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config, writes, task_id, task_path="") -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in await asyncio.to_thread(
            lambda: list(self.list(config, filter=filter, before=before, limit=limit))
        ):
            yield item

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)