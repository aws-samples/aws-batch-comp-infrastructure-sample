"""Centralized constants for the satcomp infrastructure.

This module contains magic numbers, limits, and configuration defaults
that are used across multiple modules. AWS service limits are documented
with links to official documentation where applicable.
"""

# =============================================================================
# SQS Constants
# AWS SQS service limits: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-quotas.html
# =============================================================================

# Maximum time (seconds) that a ReceiveMessage call will wait for messages
# This is an AWS hard limit - cannot exceed 20 seconds
SQS_MAX_WAIT_TIME_SECS = 20

# Maximum number of messages that can be received in a single ReceiveMessage call
# AWS hard limit is 10
SQS_MAX_MESSAGES_PER_CALL = 10

# Maximum number of messages that can be sent in a single SendMessageBatch call
# AWS hard limit is 10
SQS_BATCH_SIZE = 10

# Default visibility timeout (seconds) - how long a message is hidden after being received
SQS_VISIBILITY_TIMEOUT_SECS = 5

# Message retention period (days) - how long messages are kept in the queue
SQS_RETENTION_DAYS = 7


# =============================================================================
# VPC and Network Constants
# =============================================================================

# VPC CIDR block - provides ~65,000 IP addresses
VPC_CIDR = "10.0.0.0/16"

# Subnet CIDR mask - /19 gives ~8,000 IPs per subnet
SUBNET_CIDR_MASK = 19

# Maximum availability zones to use
MAX_AVAILABILITY_ZONES = 3

# Standard SSH port for distributed solver communication
SSH_PORT = 22

# Security group ingress CIDR for internal VPC traffic
VPC_INTERNAL_CIDR = "10.0.0.0/0"

# Port range for security group rules (all TCP ports)
TCP_PORT_RANGE_START = 0
TCP_PORT_RANGE_END = 65535


# =============================================================================
# SSM (Systems Manager) Configuration
# Used for ECS container agent configuration
# =============================================================================

# Maximum concurrent SSM command workers per instance
SSM_COMMAND_WORKERS_LIMIT = 5

# Timeout (milliseconds) for SSM stop commands
SSM_STOP_TIMEOUT_MILLIS = 20000

# Health check intervals (minutes)
SSM_HEALTH_FREQUENCY_MINUTES = 5
SSM_NEGATIVE_HEALTH_FREQUENCY_MINUTES = 30


# =============================================================================
# Formula File Extensions
# =============================================================================

# SAT solver formula extension (DIMACS CNF format)
SAT_FORMULA_EXTENSION = ".cnf"

# SMT solver formula extension (SMT-LIB format)
SMT_FORMULA_EXTENSION = ".smt2"

# Supported compression extensions for formula files
COMPRESSION_EXTENSIONS = (".bz2", ".xz")


# =============================================================================
# Node.js Version Requirements
# Required for AWS CDK
# =============================================================================

NODE_MINIMUM_VERSION = 20
NODE_SUPPORTED_VERSIONS = (20, 22)


# =============================================================================
# Docker Constants
# =============================================================================

# Target platform for Docker builds (AWS ECS uses x86_64)
DOCKER_PLATFORM = "linux/amd64"

# Protocol prefix to strip from ECR endpoints
HTTPS_PREFIX = "https://"


# =============================================================================
# Default Project Values
# =============================================================================

# Default project name used when none specified
DEFAULT_PROJECT_NAME = "satcomp25"

# Default environment tag
DEFAULT_ENVIRONMENT = "production"

# Infrastructure solver name (the base image)
INFRASTRUCTURE_SOLVER_NAME = "satcomp-infrastructure"
