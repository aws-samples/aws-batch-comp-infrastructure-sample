"""AWS service shims for local development and testing."""

from .ddb_shim import (
    DynamoAttr,
    DynamoTable,
    DynamoType,
    LocalConditionalCheckFailed,
    LocalDynamoTable,
)

# Import and re-export classes from s3_shim
from .s3_shim import (
    LocalS3FileSystem,
    S3FileSystem,
    S3FileSystemException,
)

# Import and re-export classes from sqs_shim
from .sqs_shim import (
    LocalSqsQueue,
    QueueMessage,
    SqsQueue,
    SqsQueueException,
)
from .sts_shim import (
    STS,
)
