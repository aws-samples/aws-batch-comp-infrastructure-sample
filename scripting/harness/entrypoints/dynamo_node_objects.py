import logging
from enum import Enum
from time import sleep, time
from typing import List, Optional, Union
from uuid import UUID, uuid4

from common.misc import get_local_ip_address
from dist_consts import DistributedConsts as DConsts
from harness.aws_shim.ddb_shim import DynamoAttr, DynamoTable, DynamoType

logger = logging.getLogger("DynamoNodeObjects")

################################################################################


class IpItem:
    NODE_ID_KEY = "nodeId"
    IP_ADDR_KEY = "ipAddr"
    IS_LEADER_KEY = "isLeader"
    LED_BY_KEY = "ledBy"

    NODE_ID_ATTR = DynamoAttr(NODE_ID_KEY, DynamoType.STRING, ":n")
    IP_ADDR_ATTR = DynamoAttr(IP_ADDR_KEY, DynamoType.STRING, ":i")
    IS_LEADER_ATTR = DynamoAttr(IS_LEADER_KEY, DynamoType.BOOL, ":l")
    LED_BY_ATTR = DynamoAttr(LED_BY_KEY, DynamoType.STRING, ":b")

    # 0 means "led by nobody" (can't use None)
    UNOWNED_UUID = "0"

    def __init__(
        self,
        uuid: UUID | str | None = None,
        ip_address: str | None = None,
        is_leader: bool | None = None,
        led_by: str | None = None,
    ):
        self.uuid = self.NODE_ID_ATTR.copy()
        self.ip_address = self.IP_ADDR_ATTR.copy()
        self.is_leader = self.IS_LEADER_ATTR.copy()
        self.led_by = self.LED_BY_ATTR.copy()

        # Assign a UUID if one wasn't provided, and convert to string
        if uuid is None:
            uuid = uuid4()

        if isinstance(uuid, UUID):
            uuid = str(uuid)

        if ip_address is None:
            ip_address = get_local_ip_address()

        if is_leader is None:
            is_leader = False

        if led_by is None or led_by == "":
            led_by = uuid if is_leader else self.UNOWNED_UUID

        self.uuid.set(uuid)
        self.ip_address.set(ip_address)
        self.is_leader.set(is_leader)
        self.led_by.set(led_by)

    @staticmethod
    def from_dict(d: dict) -> "IpItem":
        """From Dynamo DB response dictionary. (Not a JSON dictionary.)"""
        node_id = IpItem.NODE_ID_ATTR.copy()
        node_id.from_dict(d)
        i = IpItem(node_id.value)
        i.ip_address.from_dict(d)
        i.is_leader.from_dict(d)
        i.led_by.from_dict(d)
        return i

    def __str__(self) -> str:
        return f"IpItem({self.uuid.value})"

    def __repr__(self) -> str:
        return str(self)

    def write_to(self, table: DynamoTable):
        vals_to_set = [self.ip_address, self.is_leader, self.led_by]
        table.update_item(
            Key=self.uuid,
            UpdateExpression=vals_to_set,
            ExpressionAttributeValues=vals_to_set,
        )

    def read_from(self, table: DynamoTable, raise_not_exists_error: bool = False):
        """
        Tries to update this item's data fields by reading itself from the `table`.

        If this item doesn't exist in the `table`, either an error is raised,
        or nothing happens.
        """
        entry = table.get_item(Key=self.uuid)

        if entry is None:
            if raise_not_exists_error:
                raise ValueError(f"Item {self.uuid.value} does not exist in {table.table_name}")
        else:
            self.ip_address.from_dict(entry)
            self.is_leader.from_dict(entry)
            self.led_by.from_dict(entry)

    @staticmethod
    def scan(table: DynamoTable, is_leader: bool | None = None, led_by: str | None = None) -> List["IpItem"]:
        filter_expr = []
        expr_attrs = []
        IpItem.IS_LEADER_ATTR.add_to_filter_attrs(is_leader, filter_expr, expr_attrs)
        IpItem.LED_BY_ATTR.add_to_filter_attrs(led_by, filter_expr, expr_attrs)

        response = table.scan(
            FilterExpression=filter_expr,
            ExpressionAttributeValues=expr_attrs,
            ConsistentRead=True,
        )

        return [IpItem.from_dict(d) for d in response["Items"]]

    @staticmethod
    def batch_delete_item(table: DynamoTable, items: List[Union["IpItem", DynamoAttr]]) -> None:
        keys = [i.uuid if isinstance(i, IpItem) else i for i in items]
        table.batch_delete_item(keys)

    def get_claimed_workers(self, table: DynamoTable) -> List["IpItem"]:
        """Returns a list of IP items claimed by this node."""
        return IpItem.scan(table, is_leader=False, led_by=self.uuid.value)

    @staticmethod
    def get_unclaimed_workers(table: DynamoTable) -> List["IpItem"]:
        return IpItem.scan(table, is_leader=False, led_by=IpItem.UNOWNED_UUID)

    def claim_workers(
        self,
        table: DynamoTable,
        num_workers: int,
        retry_interval: int | float = DConsts.LEADER_CLAIM_WORKERS_SLEEP_INTERVAL,
        timeout_secs: int = 120,
    ) -> List["IpItem"]:
        """Atomically claims `num_workers` workers in the IP table.

        Returns the list of workers claimed. If unable to claim the requested
        number within timeout_secs, returns however many were claimed so far
        (may be fewer than num_workers). This prevents an infinite hang when
        workers are permanently unavailable (e.g., orphaned claims from a dead
        leader that wasn't properly cleaned up).
        """
        assert num_workers > 0
        import time
        start = time.time()

        ips = []
        num_left_to_claim = num_workers
        while num_left_to_claim > 0:
            # Bail out after timeout_secs to avoid an infinite loop. The loop
            # below hangs forever when get_unclaimed_workers() consistently
            # returns fewer workers than needed — this happens when workers are
            # still "claimed" by a dead leader whose IP entry was deleted before
            # its workers were unclaimed (see clean_up_crashed_nodes). The
            # caller's retry loop in leader_entrypoint.claim_workers() handles
            # the shortfall by re-running cleanup and trying again.
            if time.time() - start > timeout_secs:
                logger.info(
                    f"claim_workers timed out after {timeout_secs}s. "
                    f"Claimed {len(ips)}/{num_workers} workers."
                )
                return ips

            unclaimed = IpItem.get_unclaimed_workers(table)

            # Sleep if there aren't enough workers for us to claim in one go
            if len(unclaimed) < num_left_to_claim:
                logger.info(
                    f"Waiting for workers: {len(unclaimed)} unclaimed, need {num_left_to_claim} more"
                )
                sleep(retry_interval)
                continue

            # Sort by IP address to break symmetry
            unclaimed.sort(key=lambda x: x.ip_address.value)

            # Don't claim too many workers
            unclaimed = unclaimed[:num_left_to_claim]

            led_by_tmp_alias = ":u"
            claimed_up_to = table.transact_items(
                unclaimed,
                key_fn=lambda x: x.uuid,
                ConditionExpression=[
                    # Only claim those workers whose led_by equals...
                    IpItem.LED_BY_ATTR.eq_alias(led_by_tmp_alias),
                ],
                UpdateExpression=IpItem.LED_BY_ATTR,
                ExpressionAttributeValues=[
                    # ... an unowned UUID
                    IpItem.LED_BY_ATTR.typed_alias_val(alias=led_by_tmp_alias, value=IpItem.UNOWNED_UUID),
                    IpItem.LED_BY_ATTR.typed_alias_val(value=self.uuid.value),
                ],
            )

            # For each ip address we claimed, manually and locally update its value
            for i in range(claimed_up_to):
                unclaimed[i].led_by.set(self.uuid.value)
                ips.append(unclaimed[i])

            num_left_to_claim = num_workers - len(ips)
            if num_left_to_claim > 0:
                sleep(0.25)  # Reduce contention for a little bit after claiming some workers

        return ips

    def unclaim_workers(self, table: DynamoTable):
        claimed = self.get_claimed_workers(table)
        if len(claimed) == 0:
            return

        try:
            led_by_tmp_alias = ":u"
            table.transact_items(
                claimed,
                key_fn=lambda x: x.uuid,
                ConditionExpression=[
                    # Only update the `led_by` value for those workers...
                    IpItem.LED_BY_ATTR.eq_alias(led_by_tmp_alias),
                ],
                UpdateExpression=IpItem.LED_BY_ATTR,
                ExpressionAttributeValues=[
                    # ... whose `led_by` equals this node's UUID
                    IpItem.LED_BY_ATTR.typed_alias_val(alias=led_by_tmp_alias, value=self.uuid.value),
                    IpItem.LED_BY_ATTR.typed_alias_val(value=IpItem.UNOWNED_UUID),
                ],
            )
        except Exception:
            # TODO: Presumaby another leader beat us to deleting the same set...
            pass


class NodeStatus(Enum):
    READY = 0
    CLEANING = 1

    def __str__(self) -> str:
        return self.name

    def __int__(self) -> int:
        return self.value

    @staticmethod
    def from_val(value: str | int | None) -> Optional["NodeStatus"]:
        if value is None:
            return None
        elif isinstance(value, str):
            value = value.upper()
            for status in NodeStatus:
                if status.name == value:
                    return status
            raise ValueError(f"Invalid NodeStatus value: {value}")
        elif isinstance(value, int):
            for status in NodeStatus:
                if status.value == value:
                    return status
            raise ValueError(f"Invalid NodeStatus value: {value}")
        else:
            raise ValueError(f"Invalid NodeStatus value: {value}")


class TimestampItem:
    NODE_ID_KEY = "nodeId"
    STATUS_KEY = "st"  # Can't use 'status' because it's a DynamoDB reserved keyword
    TIMESTAMP_KEY = "tstamp"

    NODE_ID_ATTR = DynamoAttr(NODE_ID_KEY, DynamoType.STRING, ":n")
    STATUS_ATTR = DynamoAttr(STATUS_KEY, DynamoType.INT, ":s")
    TIMESTAMP_ATTR = DynamoAttr(TIMESTAMP_KEY, DynamoType.INT, ":t")

    UNOWNED_UUID = IpItem.UNOWNED_UUID

    SECS_TO_LIVE = 10

    def __init__(
        self,
        uuid: UUID | str,
        status: NodeStatus = NodeStatus.READY,
        timestamp: int | None = None,
    ):
        self.uuid = self.NODE_ID_ATTR.copy()
        self.status = self.STATUS_ATTR.copy()
        self.timestamp = self.TIMESTAMP_ATTR.copy()

        self.uuid.set(str(uuid))
        self.set_status(status)
        self.set_time(timestamp)

    def set_status(self, status: NodeStatus):
        self.status.set(int(status))

    @staticmethod
    def get_curr_time() -> int:
        return int(time())

    def set_time(self, timestamp: int | None = None):
        timestamp = self.get_curr_time() if timestamp is None else timestamp
        self.timestamp.set(timestamp)

    def is_alive(self, time: int | float | None = None, error_secs: int | float = DConsts.HEARTBEAT_ERROR_SECS) -> bool:
        time = self.get_curr_time() if time is None else time
        return time - self.timestamp.value <= error_secs

    def check_is_alive(self, error_secs: int | float = DConsts.HEARTBEAT_ERROR_SECS):
        """
        Checks if the `TimestampItem` is alive, according to `get_curr_time()`.

        If the timestamp is "dead," then an `Exception` is raised.
        Otherwise, this is a no-op, and `self` is unchanged.
        """
        curr_time = self.get_curr_time()
        if curr_time - self.timestamp.value > error_secs:
            raise Exception(f"Timestamp node with id {self.uuid.value} is not alive")

    @staticmethod
    def from_dict(d: dict) -> "TimestampItem":
        """From Dynamo DB response dictionary. (Not a JSON dictionary.)"""
        uuid = TimestampItem.NODE_ID_ATTR.copy()
        status = TimestampItem.STATUS_ATTR.copy()
        timestamp = TimestampItem.TIMESTAMP_ATTR.copy()

        uuid.from_dict(d)
        status.from_dict(d)
        timestamp.from_dict(d)

        return TimestampItem(
            uuid=uuid.value,
            status=status.value,
            timestamp=timestamp.value,
        )

    def read_from(self, table: DynamoTable, raise_not_exists_error: bool = False):
        """
        Tries to update this item's data fields by reading itself from the `table`.

        If this item doesn't exist in the `table`, either an error is raised,
        or nothing happens.
        """
        entry = table.get_item(Key=self.uuid)

        if entry is None:
            if raise_not_exists_error:
                raise ValueError(f"Item {self.uuid.value} does not exist in {table.table_name}")
        else:
            self.status.from_dict(entry)
            self.timestamp.from_dict(entry)

    def write_to(self, table: DynamoTable):
        vals_to_set = [self.status, self.timestamp]
        table.update_item(
            Key=self.uuid,
            UpdateExpression=vals_to_set,
            ExpressionAttributeValues=vals_to_set,
        )

    def write_new_time_to(self, table: DynamoTable):
        self.set_time()
        table.update_item(
            Key=self.uuid,
            UpdateExpression=self.timestamp,
            ExpressionAttributeValues=self.timestamp,
        )

    @staticmethod
    def scan(table: DynamoTable, status: NodeStatus | None = None) -> List["TimestampItem"]:
        filter_expr = []
        expr_attrs = []
        TimestampItem.STATUS_ATTR.add_to_filter_attrs(status, filter_expr, expr_attrs)

        response = table.scan(
            FilterExpression=filter_expr,
            ExpressionAttributeValues=expr_attrs,
        )

        return [TimestampItem.from_dict(d) for d in response["Items"]]

    @staticmethod
    def batch_get(table: DynamoTable, keys: List[DynamoAttr]) -> List["TimestampItem"]:
        response = table.batch_get_item(keys)
        return [TimestampItem.from_dict(d) for d in response]

    @staticmethod
    def delete_expired_items(
        table: DynamoTable, allowed_error_secs: int = DConsts.HEARTBEAT_ERROR_SECS
    ) -> List["TimestampItem"]:
        """Deletes and returns any `TimestampItem`s whose heartbeat has stopped."""
        # TODO: use `transact_write_items()` here instead, rather than `scan()` and `delete()`
        cutoff_time = TimestampItem.get_curr_time() - allowed_error_secs
        response = table.scan(
            FilterExpression=TimestampItem.TIMESTAMP_ATTR.lt_alias(),
            ExpressionAttributeValues=TimestampItem.TIMESTAMP_ATTR.typed_alias_val(value=cutoff_time),
        )

        expired_ts = [TimestampItem.from_dict(d) for d in response["Items"]]
        expired_ts_uuids = [t.uuid for t in expired_ts]
        table.batch_delete_item(expired_ts_uuids)
        return expired_ts
