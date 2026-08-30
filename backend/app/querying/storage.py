"""
Storage Abstraction Layer (SRP, OCP, LSP, DIP).
Handles S3 and Object Storage persistence with zero coupling to business logic.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class IObjectStorage(ABC):
    """Contract for cloud object storage persistence."""

    @abstractmethod
    def upload_csv(self, key: str, csv_content: str) -> bool:
        """Uploads a CSV string to the target path."""
        pass

    @abstractmethod
    def download_csv(self, key: str) -> Optional[str]:
        """Downloads and returns the CSV string from the target path."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Checks if an object exists at the given key."""
        pass


class S3ObjectStorage(IObjectStorage):
    """AWS S3 Storage Provider implementation."""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region_name: Optional[str] = None,
    ) -> None:
        self._bucket = bucket_name or os.getenv("EVAL_S3_BUCKET_NAME", "agenticrag-eval-bucket")
        self._region = region_name or os.getenv("AWS_REGION", "ap-south-1")
        self._s3 = boto3.client("s3", region_name=self._region)

    def upload_csv(self, key: str, csv_content: str) -> bool:
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=csv_content.encode("utf-8"),
                ContentType="text/csv",
            )
            logger.info(f"✅ Uploaded dataset to s3://{self._bucket}/{key}")
            return True
        except (BotoCoreError, ClientError) as exc:
            logger.error(f"❌ S3 Upload Failed (s3://{self._bucket}/{key}): {exc}")
            return False

    def download_csv(self, key: str) -> Optional[str]:
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=key)
            content = response["Body"].read().decode("utf-8")
            logger.info(f"📥 Downloaded dataset from s3://{self._bucket}/{key}")
            return content
        except (BotoCoreError, ClientError) as exc:
            logger.error(f"❌ S3 Download Failed (s3://{self._bucket}/{key}): {exc}")
            return None

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False


class StorageFactory:
    """Factory to instantiate storage providers dynamically."""

    @staticmethod
    def create_storage() -> IObjectStorage:
        return S3ObjectStorage()