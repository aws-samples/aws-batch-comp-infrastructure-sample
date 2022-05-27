"""Implementation of classes for interacting with SQS"""
import logging

from botocore.exceptions import ClientError


class SqsQueueException(Exception):
    """Exception for SqsQueue errors"""


class QueueMessage:
    """Class to represent an SQS message"""

    def __init__(self, msg, queue_resource):
        self.logger = logging.getLogger("QueueMessage")
        self.logger.setLevel(logging.DEBUG)
        self.queue_resource = queue_resource
        self.msg = msg

    def read(self):
        return self.msg.body

    def delete(self):
        
        self.logger.info("Deleting message with receipt handle: %s", self.msg.receipt_handle)
        msg_txt = self.msg.body
        try:
            self.queue_resource.delete_messages(Entries=[
                {
                    'Id': "test",
                    'ReceiptHandle': self.msg.receipt_handle
                },
            ])
        except ClientError as ex:
            self.logger.error("Failed to delete message from SQS queue")
            self.logger.exception(ex)
            raise ex
        else:
            return msg_txt


class SqsQueue:
    """Class to represent an SQS queue"""
    def __init__(self, queue_resource, queue_name):
        self.queue_resource = queue_resource
        self.queue_name = queue_name
        self.logger = logging.getLogger("SqsQueue")

    def get_message(self):
        """Get a single message off the queue if it exists"""
        try:
            self.logger.info("Trying to get message from queue %s", self.queue_name)
            messages = self.queue_resource.receive_messages(
                AttributeNames=['All'],
                MessageAttributeNames=['All'],
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
            )
        except ClientError as e:
            self.logger.error("Failed to get message from SQS queue")
            self.logger.exception(e)
            raise SqsQueueException(f"Failed to get message from SQS queue {self.queue_name}")
        if messages is None or len(messages) == 0:
            return None
        return QueueMessage(messages[0], self.queue_resource)

    def put_message(self, msg):
        """Put a single message on the queue"""
        try:
            self.logger.info("Trying to put message onto queue %s", self.queue_name)
            messages = self.queue_resource.send_message(
                MessageBody=msg
            )
        except ClientError as e:
            self.logger.error("Failed to put message on SQS queue")
            self.logger.exception(e)
            raise SqsQueueException(f"Failed to put message on SQS queue {self.queue_name}")

    def purge(self): 
        try:
            self.logger.info(f"Trying to purge queue {self.queue_name}")
            self.queue_resource.purge()
        except ClientError as e:
            self.logger.error(f"Failed to purge queue {self.queue_name}")
            self.logger.exception(e)
            raise SqsQueueException(f"Failed to purge queue {self.queue_name}")

    @staticmethod
    def get_sqs_queue(queue_name: str):
        import boto3
        sqs = boto3.resource('sqs')
        queue = sqs.get_queue_by_name(QueueName=queue_name)
        return SqsQueue(queue, queue_name)

    @staticmethod
    def get_sqs_queue_from_session(session, queue_name: str):
        import boto3
        sqs = session.resource('sqs')
        queue = sqs.get_queue_by_name(QueueName=queue_name)
        return SqsQueue(queue, queue_name)