import json
import logging
import time
from pollingtheevent import PollingEvent
from textExtraction import DownloadFileFromCloud
from new.main import process_single_file, get_chunks_data, DocumentParsingPipeline
from pathlib import Path
from quadrantIngestion.vector import VectorDatabase, QudrantVectorDatabase
logger = logging.getLogger(__name__)

class PdfWorker:

    def __init__(
        self,
        poller: PollingEvent,
        downloader: DownloadFileFromCloud,
        pipeline : DocumentParsingPipeline,
        vectordb : VectorDatabase
    ):
        self.poller = poller
        self.downloader = downloader
        self.pipeline = pipeline
        self.vector_db = vectordb

    def start(self):

        logger.info("Worker started")

        while True:
            
            messages = self.poller.poll_messages()

            logger.info(f"Messages recieved are {messages}")
            
            if not messages:
                logger.info("No message found")
                continue

            logger.info("Received %d message(s)", len(messages))

            for message in messages:
                # Isolate failures per-message so one bad message
                # can't take down the whole polling loop.
                try:
                    self.process(message)
                except Exception:
                    logger.exception("Unhandled error processing message: %s", message)

    def process(self, message):

        local_pdf = None

        try:
            body = self._parse_body(message)
            cloud_uri = self._extract_cloud_uri(body)

            bucket, key = self.downloader.parse_file_path(cloud_uri)
            local_pdf = self.downloader.download_file(bucket, key)
            collectionName = self._extract_client_name(key)
            logger.info("Downloaded PDF : %s", local_pdf)
            
            docs = process_single_file(self.pipeline, local_pdf)

            for doc in docs :
                if doc is None:
                    raise RuntimeError(f"Parsing pipeline returned no document for {local_pdf}")

                chunks_data = get_chunks_data(doc.full_markdown)
                self._upload_results(bucket, key, doc, chunks_data)

                doesCollectionExists = self.vector_db.ensure_collection_exists(collectionName)
                if doesCollectionExists :
                    logger.info(f"Going to insert into the collection {collectionName}")
                    isDone = self.vector_db.insertVectorsInBatch(doc, chunks_data, collectionName)
                    if isDone:
                        self.poller.acknowledge(message)
                    else :
                        pass
                else :
                    logger.info("Some error has occured in creating the collection")

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Message itself is malformed — retrying won't help.
            # Ack it so it doesn't loop forever, but log it loudly
            # so it can be inspected (ideally routed to a DLQ instead).
            logger.error("Malformed message, acknowledging to drop it: %s", e)
            self.poller.acknowledge(message)

        except FileNotFoundError as e:
            # The file genuinely isn't there — retrying won't fix it either.
            logger.error("Source file not found, acknowledging to drop it: %s", e)
            self.poller.acknowledge(message)

        except PermissionError as e:
            # Access/config issue — this is worth surfacing loudly but
            # NOT acking, since retrying after the permission is fixed
            # should succeed.
            logger.error("Permission denied downloading file, leaving for retry: %s", e)
            raise

        except RuntimeError as e:
            # Transient infra failure (network blip, SDK error, etc.)
            # Don't ack — let it become visible again for retry / DLQ
            # after max receive count.
            logger.error("Transient failure downloading file, leaving for retry: %s", e)
            raise

        finally:
            if local_pdf:
                self._cleanup(local_pdf)

    def _upload_results(self, bucket, key, doc, chunks_data):

        try :
            base_key = key.rsplit(".", 1)[0]

            jsondata = self.downloader.upload_bytes(
                bucket,
                f"{base_key}_chunks.json",
                json.dumps(chunks_data, indent = 2, ensure_ascii = False).encode("utf-8"),
            )

            fullmarkdown = self.downloader.upload_bytes(
                bucket, f"{base_key}.md", doc.full_markdown.encode("utf-8")
            )

            rawmarkdown = self.downloader.upload_bytes(
                bucket, f"{base_key}_raw.md", doc.raw_markdown.encode("utf-8")
            )

            logger.info("Uploaded results for %s to s3://%s/%s*", key, bucket, base_key)
            logger.info(f"jsondata is {jsondata}")
            logger.info(f"fullmarkdown is {fullmarkdown}")
            logger.info(f"rawmarkdown is {rawmarkdown}")
        except Exception as e :
            logger.exception(f"An exception has occured {e}")
            raise e

    @staticmethod
    def _parse_body(message) :
        try:
            return json.loads(message["Body"])
        except KeyError as e:
            raise KeyError(f"Message missing 'Body' key: {message}") from e
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Message body is not valid JSON: {e.msg}", e.doc, e.pos
            ) from e

    @staticmethod
    def _extract_cloud_uri(body) :
        if "s3_path" not in body:
            raise KeyError(f"Body missing 's3_path' key: {body}")
        return body["s3_path"]

    @staticmethod
    def _extract_client_name(key: str) -> str :
        if "/" not in key:
            raise ValueError(f"Key does not contain a client name prefix: {key}")
        return key.split("/", 1)[0]

    def _cleanup(self, local_pdf: Path):
        try:
            local_pdf.unlink(missing_ok=True)
            logger.info("Deleted local temp file: %s", local_pdf)
        except Exception:
            logger.warning("Failed to clean up temp file: %s", local_pdf)