import logging
import os
from new.main import build_pipeline
from dotenv import load_dotenv
from quadrantIngestion.vector import VectorDatabase, QudrantVectorDatabase
from qdrant_client import QdrantClient, models
import time

from pollingtheevent import (
    AwsSqsConfig,
    KafkaConfig,
    PollingAwsSqs,
    PollingKafka,
    PollingEvent,
)

from textExtraction import (
    DownloadFileFromCloud,
    S3Downloader,
    GCSDownloader,
    AzureBlobDownloader,
)

from pdfWorker import PdfWorker

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

def create_poller() -> PollingEvent:

    provider = os.getenv("EVENT_PROVIDER", "SQS").upper()

    if provider == "SQS":

        return PollingAwsSqs(

            AwsSqsConfig(
                queue_url=os.getenv("QUEUE_URL"),
                region_name=os.getenv("AWSREGION"),
            )

        )

    elif provider == "KAFKA":

        return PollingKafka(

            KafkaConfig(

                bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS"),

                topic=os.getenv("KAFKA_TOPIC"),

                group_id=os.getenv("KAFKA_GROUP_ID"),

            )

        )

    raise ValueError(f"Unsupported EVENT_PROVIDER: {provider}")

def create_downloader() -> DownloadFileFromCloud:

    provider = os.getenv("CLOUD_PROVIDER", "AWS").upper()

    if provider == "AWS":
        return S3Downloader()

    elif provider == "GCP":
        return GCSDownloader()

    elif provider == "AZURE":

        return AzureBlobDownloader(

            connection_string=os.getenv("AZURE_STORAGE_CONNECTION_STRING")

        )

    raise ValueError(f"Unsupported CLOUD_PROVIDER: {provider}")

def create_vectorDatabase() -> VectorDatabase :

    vector = os.getenv("vectorname", "qudrant").lower()

    if vector == "qudrant":
        client = QdrantClient(
            url = os.getenv("QUADRANT_CLUSTERENDPOINT"),
            api_key = os.getenv("QUADRANTAPIKEY"),
            cloud_inference = True
        )

        vectordatabase = QudrantVectorDatabase(
            client = client,
            batch_size = int(os.getenv("BATCHSIZE"))
        )

        logger.info("Buffering")
        time.sleep(10)
        logger.info("Buffering is over")

        return vectordatabase

def main():

    try :
        logger.info("Starting PDF Worker")

        poller = create_poller()

        downloader = create_downloader()

        pipeline = build_pipeline()

        vectorDatabase = create_vectorDatabase()

        worker = PdfWorker(

            poller = poller,

            downloader = downloader,

            pipeline = pipeline,

            vectordb = vectorDatabase

        )

        worker.start()
    except Exception as e :
        logger.info(f"Here is the exceptions which occured {e}")
        raise e


if __name__ == "__main__":
    main()