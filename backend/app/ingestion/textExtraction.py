import logging
from abc import ABC, abstractmethod
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from google.cloud import storage
# from azure.storage.blob import BlobServiceClient

logger = logging.getLogger(__name__)

class DownloadFileFromCloud(ABC):

    @abstractmethod
    def parse_file_path(self, cloud_uri: str):
        pass

    @abstractmethod
    def download_file(self, bucket_or_container: str, key_or_blob: str) -> Path:
        pass

    @abstractmethod
    def upload_bytes(self, bucket: str, key: str, data: bytes) -> None :
        pass
    
    @abstractmethod
    def delete_temporary_memory(self) -> None:
        pass

class S3Downloader(DownloadFileFromCloud):

    def __init__(self, download_directory: str = "/tmp/pdfs", s3_client=None):
        self.client = s3_client or boto3.client("s3")
        self.download_directory = Path(download_directory)
        self.download_directory.mkdir(parents=True, exist_ok=True)
        self.downloaded_file: Path | None = None

    def parse_file_path(self, cloud_uri: str):
        if not cloud_uri.startswith("s3://"):
            raise ValueError(f"Invalid S3 URI: {cloud_uri}")

        bucket, key = cloud_uri[5:].split("/", 1)
        return bucket, key

    def download_file(self, bucket: str, key: str) -> Path:
        local_file = self.download_directory / Path(key).name

        logger.info("Downloading s3://%s/%s", bucket, key)

        try:
            self.client.download_file(Bucket=bucket, Key=key, Filename=str(local_file))

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            if error_code in ("404", "NoSuchKey"):
                raise FileNotFoundError(f"s3://{bucket}/{key} not found.") from e

            if error_code == "AccessDenied":
                raise PermissionError(f"Access denied for s3://{bucket}/{key}") from e

            raise RuntimeError(f"Failed to download s3://{bucket}/{key}") from e

        except BotoCoreError as e:
            raise RuntimeError("AWS SDK error") from e

        logger.info("Downloaded to %s", local_file)
        self.downloaded_file = local_file
        return local_file

    def upload_bytes(self, bucket: str, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=bucket, Key=key, Body=data)
    
    def delete_temporary_memory(self) -> None:
        if self.downloaded_file and self.downloaded_file.exists():
            logger.info("Deleting %s", self.downloaded_file)
            self.downloaded_file.unlink()
            self.downloaded_file = None

class GCSDownloader(DownloadFileFromCloud):

    def __init__(self, download_directory: str = "/tmp/pdfs", gcs_client=None):
        self.client = gcs_client or storage.Client()
        self.download_directory = Path(download_directory)
        self.download_directory.mkdir(parents=True, exist_ok=True)
        self.downloaded_file: Path | None = None

    def parse_file_path(self, cloud_uri: str):
        if not cloud_uri.startswith("gs://"):
            raise ValueError(f"Invalid GCS URI: {cloud_uri}")

        bucket, blob = cloud_uri[5:].split("/", 1)
        return bucket, blob

    def download_file(self, bucket: str, blob_name: str) -> Path:
        local_file = self.download_directory / Path(blob_name).name

        logger.info("Downloading gs://%s/%s", bucket, blob_name)

        try:
            bucket_ref = self.client.bucket(bucket)
            blob = bucket_ref.blob(blob_name)

            if not blob.exists():
                raise FileNotFoundError(f"gs://{bucket}/{blob_name} not found.")

            blob.download_to_filename(str(local_file))

        except Exception as e:
            raise RuntimeError(f"Failed to download gs://{bucket}/{blob_name}") from e

        logger.info("Downloaded to %s", local_file)
        self.downloaded_file = local_file
        return local_file

    def delete_temporary_memory(self) -> None:
        if self.downloaded_file and self.downloaded_file.exists():
            logger.info("Deleting %s", self.downloaded_file)
            self.downloaded_file.unlink()
            self.downloaded_file = None

class AzureBlobDownloader(DownloadFileFromCloud):

    def __init__(self, connection_string: str, download_directory: str = "/tmp/pdfs"):
        self.client = BlobServiceClient.from_connection_string(connection_string)
        self.download_directory = Path(download_directory)
        self.download_directory.mkdir(parents=True, exist_ok=True)
        self.downloaded_file: Path | None = None

    def parse_file_path(self, cloud_uri: str):
        if not cloud_uri.startswith("azure://"):
            raise ValueError(f"Invalid Azure Blob URI: {cloud_uri}")

        container, blob = cloud_uri[8:].split("/", 1)
        return container, blob

    def download_file(self, container: str, blob_name: str) -> Path:
        local_file = self.download_directory / Path(blob_name).name

        logger.info("Downloading azure://%s/%s", container, blob_name)

        try:
            blob_client = self.client.get_blob_client(container=container, blob=blob_name)

            with open(local_file, "wb") as file:
                download_stream = blob_client.download_blob()
                file.write(download_stream.readall())

        except Exception as e:
            raise RuntimeError(f"Failed to download azure://{container}/{blob_name}") from e

        logger.info("Downloaded to %s", local_file)
        self.downloaded_file = local_file
        return local_file

    def delete_temporary_memory(self) -> None:
        if self.downloaded_file and self.downloaded_file.exists():
            logger.info("Deleting %s", self.downloaded_file)
            self.downloaded_file.unlink()
            self.downloaded_file = None