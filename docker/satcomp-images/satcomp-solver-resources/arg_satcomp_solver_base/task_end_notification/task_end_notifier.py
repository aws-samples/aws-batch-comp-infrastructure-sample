import time
import uuid

import boto3


class TaskEndNotifier:

    def __init__(self, table, notification_expiration_time=5):
        self.table = table
        self.node_expiration_time = notification_expiration_time

    def notify_task_end(self, leader_ip: str):
        current_time = int(time.time())
        notification_id = str(uuid.uuid4())
        self.table.update_item(
            Key={
                'leaderIp': leader_ip
            },
            UpdateExpression="set notificationId = :notificationId, lastModified = :lastModifiedVal",
            ExpressionAttributeValues={
                ":notificationId": notification_id,
                ":lastModifiedVal": current_time
            }
        )

    def check_for_task_end(self, previous_notification_id=None):
        expiration_time = int(time.time() - self.node_expiration_time)

        filter_expression = "#lastModifiedKey > :lastModifiedVal"
        attribute_names = {
            "#lastModifiedKey": "lastModified"
        }
        attribute_values = {
            ":lastModifiedVal": expiration_time
        }
        if previous_notification_id is not None:
            filter_expression += " and not (#notificationId = :notificationId)"
            attribute_values[":notificationId"] = previous_notification_id
            attribute_names["#notificationId"] = "notificationId"

        notifications = self.table.scan(
            Select="ALL_ATTRIBUTES",
            FilterExpression=filter_expression,
            ExpressionAttributeNames=attribute_names,
            ExpressionAttributeValues=attribute_values,
            ConsistentRead=True
        )
        if len(notifications["Items"]) > 0:
            return notifications["Items"][0]["notificationId"]
        return None

    @staticmethod
    def get_task_end_notifier():
        dynamodb_resource = boto3.resource("dynamodb")
        table = dynamodb_resource.Table("TaskEndNotification")
        return TaskEndNotifier(table)
