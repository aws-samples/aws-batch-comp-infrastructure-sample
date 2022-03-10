import logging
import time
from enum import Enum

import boto3


class NodeStatus(Enum):
    READY = "READY"
    BUSY = "BUSY"
    FAILED = "FAILED"


class NodeType(Enum):
    WORKER = "WORKER"
    LEADER = "LEADER"


class DynamodbManifest:
    """
    Node manifest for storing IP and status of satcomp nodes based on a DynamoDB Table
    """
    def __init__(self, table, node_expiration_time=120):
        self.table = table
        self.node_expiration_time = node_expiration_time
        self.logger = logging.getLogger(__name__)

    def register_node(self, node_id: str, ip_address: str, status: str, node_type: str):
        """
        Register node with node manifest table
        :param node_id: Unique ID for this node
        :param ip_address: IP address for this node
        :param status: Current status of Node
        :param node_type: Node type, either WORKER or LEADER
        :return:
        """
        current_time = int(time.time())
        self.table.update_item(
            Key={
                'nodeId': node_id
            },
            UpdateExpression="set nodeIp = :ipVal, #stskey = :stsVal, nodeType = :nodeTypeVal,"
                             " lastModified = :lastModifiedVal",
            ExpressionAttributeNames={
                "#stskey": "status"
            },
            ExpressionAttributeValues={
                ":ipVal": ip_address,
                ":stsVal": status,
                ":nodeTypeVal": node_type,
                ":lastModifiedVal": current_time
            }
        )

    def get_all_ready_worker_nodes(self):
        """
        Returns all worker nodes that are currently set to READY status
        :return:
        """
        expiration_time = int(time.time() - self.node_expiration_time)
        nodes = self.table.scan(
            Select="ALL_ATTRIBUTES",
            FilterExpression="#nodeStatusKey = :nodeStatusVal and #nodeTypeKey = :nodeTypeVal and "
                             "#lastModifiedKey > :lastModifiedVal",
            ExpressionAttributeNames={
                "#nodeStatusKey": "status",
                "#nodeTypeKey": "nodeType",
                "#lastModifiedKey": "lastModified"
            },
            ExpressionAttributeValues={
                ":nodeStatusVal": "READY",
                ":nodeTypeVal": "WORKER",
                ":lastModifiedVal": expiration_time
            },
            ConsistentRead=True
        )
        return nodes["Items"]

    @staticmethod
    def get_dynamodb_manifest():
        dynamodb_resource = boto3.resource("dynamodb")
        table = dynamodb_resource.Table("SatCompNodeManifest")
        return DynamodbManifest(table)
