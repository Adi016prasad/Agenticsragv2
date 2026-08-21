from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List
import os
from dotenv import load_dotenv

load_dotenv()

import logging
import boto3
# from kafka import KafkaConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

maxMessages = int(os.getenv("MAXMESSAGES"))
waittimeseconds = int(os.getenv("WAITTIMESECONDS"))
visibilityTimeout = int(os.getenv("VISIBILITY_TIMEOUT"))

# ============================================================
# ABSTRACT CLASS
# ============================================================

class PollingEvent(ABC):

    @abstractmethod
    def poll_messages(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def acknowledge(self, message: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def close(self):
        pass


# ============================================================
# AWS SQS CONFIG
# ============================================================

@dataclass
class AwsSqsConfig:

    queue_url: str
    region_name: str

    max_messages: int = maxMessages
    wait_time_seconds: int = waittimeseconds
    visibility_timeout: int = visibilityTimeout


# ============================================================
# KAFKA CONFIG
# ============================================================

@dataclass
class KafkaConfig:

    bootstrap_servers: str
    topic: str
    group_id: str

    auto_offset_reset: str = "earliest"

    enable_auto_commit: bool = False


# ============================================================
# AWS SQS IMPLEMENTATION
# ============================================================

class PollingAwsSqs(PollingEvent):

    def __init__(self, config: AwsSqsConfig):

        self.config = config

        self.client = boto3.client(
            "sqs",
            region_name = config.region_name,
        )

        logger.info("AWS SQS Client Initialized")

    def poll_messages(self) -> List[Dict[str, Any]]:

        response = self.client.receive_message(

            QueueUrl=self.config.queue_url,

            MaxNumberOfMessages=self.config.max_messages,

            WaitTimeSeconds=self.config.wait_time_seconds,

            VisibilityTimeout=self.config.visibility_timeout,

            AttributeNames=["All"],

            MessageAttributeNames=["All"],

        )

        return response.get("Messages", [])

    def acknowledge(self, message: Dict[str, Any]):

        logger.info("Deleting the event from the SQS now only")
        
        self.client.delete_message(

            QueueUrl=self.config.queue_url,

            ReceiptHandle=message["ReceiptHandle"]

        )

    def close(self):

        logger.info("Closing AWS SQS Client")

        self.client.close()


# ============================================================
# KAFKA IMPLEMENTATION
# ============================================================

class PollingKafka(PollingEvent):

    def __init__(self, config: KafkaConfig):

        self.config = config

        self.consumer = KafkaConsumer(

            config.topic,

            bootstrap_servers=config.bootstrap_servers,

            group_id=config.group_id,

            auto_offset_reset=config.auto_offset_reset,

            enable_auto_commit=config.enable_auto_commit,

            value_deserializer=lambda x: x.decode("utf-8")

        )

        logger.info("Kafka Consumer Initialized")

    def poll_messages(self) -> List[Dict[str, Any]]:

        records = self.consumer.poll(

            timeout_ms=5000,

            max_records=10

        )

        messages = []

        for _, kafka_messages in records.items():

            for message in kafka_messages:

                messages.append({

                    "topic": message.topic,

                    "partition": message.partition,

                    "offset": message.offset,

                    "key": message.key,

                    "body": message.value,

                    "_kafka_message": message

                })

        return messages

    def acknowledge(self, message: Dict[str, Any]):

        self.consumer.commit()

    def close(self):

        logger.info("Closing Kafka Consumer")

        self.consumer.close()