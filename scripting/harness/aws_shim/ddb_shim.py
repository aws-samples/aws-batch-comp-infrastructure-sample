"""Shim for a DynamoDB table."""

import fcntl
import json
import os
import re
from enum import Enum
from typing import Any, Callable, List, Optional, Tuple

import boto3

# Compatibility fix for Python < 3.12
try:
    from itertools import batched
except ImportError:

    def batched(iterable, n):
        """Batch data into tuples of length n. The last batch may be shorter."""
        it = iter(iterable)
        while True:
            batch = list(islice(it, n))
            if not batch:
                break
            yield batch

    from itertools import islice

from common import LoggingManager
from common.solver_env import SolverEnvironment

################################################################################

lm = LoggingManager()
logger = lm.get_logger("Dynamo shim")


class DynamoType(Enum):
    STRING = "S"
    INT = "N"
    FLOAT = "N"
    BYTES = "B"
    BOOL = "BOOL"
    STRING_SET = "SS"
    INT_SET = "NS"
    FLOAT_SET = "NS"
    BINARY_SET = "BS"
    # TODO for completeness, we defime the "SET" types here,
    # but we don't support/implement very many functions for them

    def is_valuelike(self) -> bool:
        return (
            self == DynamoType.STRING
            or self == DynamoType.INT
            or self == DynamoType.FLOAT
            or self == DynamoType.BYTES
            or self == DynamoType.BOOL
        )

    def is_setlike(self) -> bool:
        return (
            self == DynamoType.STRING_SET
            or self == DynamoType.INT_SET
            or self == DynamoType.FLOAT_SET
            or self == DynamoType.BINARY_SET
        )

    def typecheck(self, value) -> None:
        if self == DynamoType.STRING:
            assert isinstance(value, str)
        elif self == DynamoType.INT:
            assert isinstance(value, int)
        elif self == DynamoType.FLOAT:
            assert isinstance(value, int) or isinstance(value, float)
        elif self == DynamoType.BOOL:
            assert isinstance(value, bool)
        elif self.is_setlike():
            assert isinstance(value, list) or isinstance(value, set)

    def from_val(self, x: Any) -> Any:
        if self == DynamoType.STRING:
            return x
        elif self == DynamoType.INT:
            return int(x)
        elif self == DynamoType.FLOAT:
            return float(x)
        elif self == DynamoType.BOOL:
            return x
        else:
            # TODO lists
            return x


class DynamoAttr:
    def __init__(self, key: str, entry_type: DynamoType, alias: str | None = None, value=None):
        """
        Create a "column" in a Dynamo entry, i.e., an attribute.

        When supplying a `key` or an `alias`, make sure to avoid any reserved words in DynamoDB. See:
        https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ReservedWords.html

        By convention, most aliases start with a colon, such as `:x`.
        Avoid starting them with a pound (`'#'`), since that is used to
        escape a reserved word.
        """
        self.key = key
        self.alias = f":{key}" if alias is None else alias
        self.entry_type = entry_type
        self.value = value
        self.typecheck()

    def typecheck(self) -> None:
        if self.value is not None:
            self.entry_type.typecheck(self.value)

    def set(self, value):
        self.value = value
        self.typecheck()

    def copy(self) -> "DynamoAttr":
        """Shallow copy the attributes and value."""
        return DynamoAttr(self.key, self.entry_type, self.alias, self.value)

    def _get_value(self, value: Any | None = None) -> Any:
        if value is None:
            assert self.value is not None
        return value if value is not None else self.value

    def _cmp_str(self, lhs: str, op: str, rhs: str) -> str:
        return f"{lhs} {op} {rhs}"

    def key_cmp_alias(self, op: str, alias: str | None = None) -> str:
        alias = alias if alias is not None else self.alias
        alias = str(alias)
        return self._cmp_str(self.key, op, alias)

    def eq_alias(self, alias: str | None = None) -> str:
        return self.key_cmp_alias("=", alias)

    def lt_alias(self, alias: str | None = None) -> str:
        return self.key_cmp_alias("<", alias)

    def le_alias(self, alias: str | None = None) -> str:
        return self.key_cmp_alias("<=", alias)

    def gt_alias(self, alias: str | None = None) -> str:
        return self.key_cmp_alias(">", alias)

    def ge_alias(self, alias: str | None = None) -> str:
        return self.key_cmp_alias(">=", alias)

    def key_cmp_value(self, op: str, value: Any | None = None) -> str:
        value = str(self._get_value(value))
        return self._cmp_str(self.key, op, value)

    def eq(self, value: Any | None = None) -> str:
        return self.key_cmp_value("=", value)

    def lt(self, value: Any | None = None) -> str:
        return self.key_cmp_value("<", value)

    def le(self, value: Any | None = None) -> str:
        return self.key_cmp_value("<=", value)

    def gt(self, value: Any | None = None) -> str:
        return self.key_cmp_value(">", value)

    def ge(self, value: Any | None = None) -> str:
        return self.key_cmp_value(">=", value)

    def key_val(self, value: Any | None = None) -> dict:
        return {self.key: self._get_value(value)}

    def alias_val(self, alias: str | None = None, value: Any | None = None) -> dict:
        alias = alias if alias is not None else self.alias
        return {alias: self._get_value(value)}

    def _typed_val(self, value: Any | None = None) -> dict:
        value = self._get_value(value)
        if self.entry_type == DynamoType.BOOL:
            return {self.entry_type.value: value}
        else:
            # TODO: Implement for lists
            return {self.entry_type.value: str(value)}

    def typed_key_val(self, value: Any | None = None) -> dict:
        """Returns a typed dict for 'key' with the actual value `value`."""
        return {self.key: self._typed_val(value)}

    def typed_alias_val(self, alias: str | None = None, value: Any | None = None) -> dict:
        """Returns a typed dict for the actual value `value` under `alias`."""
        alias = alias if alias is not None else self.alias
        return {alias: self._typed_val(value)}

    def from_dict(self, d: dict) -> None:
        """Extract a value from a dict."""
        if d.get(self.key) is not None and d[self.key].get(self.entry_type.value) is not None:
            self.value = self.entry_type.from_val(d[self.key][self.entry_type.value])

    def add_to_filter_attrs(self, value: Any | None, filter_expr: List["DynamoAttr"], expr_attrs: List[dict]):
        if value is not None:
            filter_expr.append(self)
            expr_attrs.append(self.typed_alias_val(value=value))


class DynamoTable:

    def __init__(self, ddb_client, table_name: str):
        self.ddb_client = ddb_client
        self.table_name = table_name

    # Python/boto3 interprets an unset `kwargs` arg different from one set to `None`,
    # i.e., there's different behavior when `kwargs.get(k) is None` versus `kwargs[k] is None`.
    # boto3 prefers the args to be unset; Thus, we only store values that are set into `kwargs`

    def _format_key(self, Key: DynamoAttr | dict) -> dict:
        if isinstance(Key, DynamoAttr):
            Key = Key.typed_key_val()
        elif not isinstance(Key, dict):
            raise ValueError(f"Expected DynamoAttr or dict, got {Key}")
        return Key

    def _connect_exprs(
        self,
        exprs: List[DynamoAttr | str] | DynamoAttr | str,
        connector: str,
        fn: Callable[[DynamoAttr], str],
    ) -> str:
        exprs = [exprs] if isinstance(exprs, DynamoAttr) or isinstance(exprs, str) else exprs
        return connector.join(map(lambda x: fn(x) if isinstance(x, DynamoAttr) else x, exprs))

    def _store_logic_expr(
        self,
        xs: List[DynamoAttr | str] | DynamoAttr | str | None,
        connector: str,
        store_in: dict,
        key: str,
    ):
        if xs is not None:
            expr = self._connect_exprs(xs, connector, lambda x: x.eq_alias())
            if expr != "":
                store_in[key] = expr

    def _store_cond_expr(
        self,
        ConditionExpression: List[DynamoAttr | str] | DynamoAttr | str | None,
        ConditionConnector: str,
        store_in: dict,
    ):
        self._store_logic_expr(ConditionExpression, ConditionConnector, store_in, "ConditionExpression")

    def _store_filter_expr(
        self,
        FilterExpression: List[DynamoAttr | str] | DynamoAttr | str | None,
        FilterConnector: str,
        store_in: dict,
    ):
        self._store_logic_expr(FilterExpression, FilterConnector, store_in, "FilterExpression")

    def make_update_expr(self, xs: List[DynamoAttr | str] | DynamoAttr | str) -> str:
        expr = self._connect_exprs(xs, ", ", lambda x: x.eq_alias())
        return "SET " + expr

    def _store_update_expr(self, UpdateExpression: List[DynamoAttr | str] | DynamoAttr | str | None, store_in: dict):
        if UpdateExpression is not None:
            UpdateExpression = self.make_update_expr(UpdateExpression)
            if UpdateExpression != "":
                store_in["UpdateExpression"] = UpdateExpression

    def _store_expr_attr_vals(
        self,
        ExpressionAttributeValues: List[DynamoAttr | dict] | DynamoAttr | dict | None,
        store_in: dict,
    ):
        if ExpressionAttributeValues is not None:
            xs = ExpressionAttributeValues  # alias to shorter variable name
            xs = [xs] if isinstance(xs, DynamoAttr) or isinstance(xs, dict) else xs

            d = {}
            for x in xs:
                d |= x.typed_alias_val() if isinstance(x, DynamoAttr) else x

            if len(d) > 0:
                store_in["ExpressionAttributeValues"] = d

    def _store_update_item_dict(
        self, ConditionExpression, ConditionConnector, UpdateExpression, ExpressionAttributeValues, store_in: dict
    ) -> None:
        self._store_cond_expr(ConditionExpression, ConditionConnector, store_in)
        self._store_update_expr(UpdateExpression, store_in)
        self._store_expr_attr_vals(ExpressionAttributeValues, store_in)

    def update_item(
        self,
        Key: DynamoAttr | dict,
        UpdateExpression: List[DynamoAttr | str] | DynamoAttr | str,
        *,
        ConditionExpression: List[DynamoAttr | str] | DynamoAttr | str | None = None,
        ConditionConnector: str = " AND ",
        ExpressionAttributeValues: List[DynamoAttr | dict] | DynamoAttr | dict | None = None,
        **kwargs,
    ) -> None:
        """
        Use the `update_item()` DDB API, and use `DynamoAttr` methods.

        When `UpdateExpression` is a list of `DynamoAttr`s, the update query
        sets each `dattr.key = dattr.alias`. If an alias is used, then the
        alias's value needs to be set in `ExpressionAttributeValues`.
        Otherwise, a hard-coded string could be used in place of a `DynamoAttr`.

        The same thing applies for `UpdateExpression` as well. Note that the
        default aliases are used, so if the same alias appears in both the
        update and condition expression, they will clash in
        `ExpressionAttributeValues`. Use `.eq_alias()` etc. to manually
        construct those alias strings, and use the manual aliases
        in `ExprAttrVs`.

        When `ExpressionAttributeValues` is a list of `DynamoAttr`s,
        the query sets each `dattr.alias := dattr.value`.
        """

        self._store_update_item_dict(
            ConditionExpression, ConditionConnector, UpdateExpression, ExpressionAttributeValues, kwargs
        )
        self.ddb_client.update_item(
            TableName=self.table_name,  # Required argument means it can't appear in kwargs
            Key=self._format_key(Key),  # Also required
            **kwargs,
        )

    def get_item(
        self,
        Key: DynamoAttr | dict,
        *,
        ConsistentRead: bool = False,
    ) -> Optional[dict]:
        try:
            response = self.ddb_client.get_item(
                TableName=self.table_name,
                Key=self._format_key(Key),
                ConsistentRead=ConsistentRead,
            )
            return response.get("Item")
        except Exception as e:
            logger.error("Error: `get_item()` failed for some reason.")
            logger.error(e)
            return None

    def delete_item(
        self,
        Key: DynamoAttr | dict,
        *,
        ConditionExpression: List[DynamoAttr | str] | DynamoAttr | str | None = None,
        ConditionConnector: str = " AND ",
        ExpressionAttributeValues: List[DynamoAttr | dict] | DynamoAttr | dict | None = None,
        **kwargs,
    ):
        self._store_expr_attr_vals(ExpressionAttributeValues, kwargs)
        self._store_cond_expr(ConditionExpression, ConditionConnector, kwargs)
        self.ddb_client.delete_item(
            TableName=self.table_name,
            Key=self._format_key(Key),
            **kwargs,
        )

    class ScanSelect(Enum):
        ALL = "ALL_ATTRIBUTES"
        PROJ = "ALL_PROJECTED_ATTRIBUTES"
        SPEC = "SPECIFIC_ATTRIBUTES"
        COUNT = "COUNT"

        def __str__(self) -> str:
            return self.value

    def scan(
        self,
        Select: ScanSelect = ScanSelect.ALL,
        *,
        FilterExpression: List[DynamoAttr | str] | DynamoAttr | str | None = None,
        FilterConnector: str = " AND ",
        ExpressionAttributeValues: List[DynamoAttr | Tuple[DynamoAttr, Any]] | dict | None = None,
        ConsistentRead: bool = False,
        **kwargs,
    ) -> dict:
        """
        Returns raw `scan()` result. Index by `['Items']` for the items.

        Set `ConsistentRead` to `True` if the database should commit all writes
        before starting a read. However, setting to `True` reduces throughput.
        """

        # TODO: Develop alternative ways of using FilterExpressions that automatically
        #       add to ExpressionAttributeValues. It seems like you can't have filter
        #       expressions with explicit values, you have to use aliases.
        #       So we should make the API automatically manage aliases for the caller.

        # TODO: Apply the above feature generally to the API we've implemented here.

        # TODO: Scan through multiple segments if the response is too large (> 4 MB)
        #       But for our purposes, with O(100) solvers, we'll be fine.

        self._store_expr_attr_vals(ExpressionAttributeValues, kwargs)
        self._store_filter_expr(FilterExpression, FilterConnector, kwargs)
        return self.ddb_client.scan(
            TableName=self.table_name,
            Select=str(Select),
            ConsistentRead=ConsistentRead,
            **kwargs,
        )

    class TransactOp(Enum):
        CONDITION_CHECK = "ConditionCheck"
        DELETE = "Delete"
        PUT = "Put"
        UPDATE = "Update"

        def __str__(self) -> str:
            return self.value

    def transact_items(
        self,
        items: List[Any],
        key_fn: Callable[[Any], DynamoAttr | dict],
        operation: TransactOp = TransactOp.UPDATE,
        *,
        ConditionExpression: List[DynamoAttr | str] | DynamoAttr | str | None = None,
        ConditionConnector: str = " AND ",
        UpdateExpression: List[DynamoAttr | str] | DynamoAttr | str | None = None,
        ExpressionAttributeValues: List[DynamoAttr | Tuple[DynamoAttr, Any]] | dict | None = None,
        **kwargs,
    ) -> int:
        """
        Batches a single type of operation on a collection of items. Returns the items the operation failed on.

        This function is a wrapper for `transact_write_items()`.

        If `operation == UPDATE`, then `items` is interpreted as the list of items
        to update according to their key values. Arguments in `kwargs` are interpreted
        as if you called `update_item()`. Omit any unnecessary `kwargs` parameters,
        rather than setting them to `None`. For example, if the `ConditionExpression`
        should not be included, do not set it to `None`, just omit it.

        The `transact_write_items()` API has a limit of 100 items. Thus, this function
        tries every batch of 100 items in `items` until either an operation fails,
        or all operations succeed. This function returns the index into `items`
        where the operations failed. Anything before the index succeeded,
        everything after failed. A full success means that the index matches
        the length of `items`.
        """

        if len(items) == 0:
            return 0

        if operation == DynamoTable.TransactOp.UPDATE:
            self._store_update_item_dict(
                ConditionExpression=ConditionExpression,
                ConditionConnector=ConditionConnector,
                UpdateExpression=UpdateExpression,
                ExpressionAttributeValues=ExpressionAttributeValues,
                store_in=kwargs,
            )

            transact_items = [
                {
                    "Update": {
                        "TableName": self.table_name,
                        "Key": self._format_key(key_fn(i)),
                    }
                    | kwargs
                }
                for i in items
            ]
        elif operation == DynamoTable.TransactOp.DELETE:
            assert UpdateExpression is None
            self._store_update_item_dict(
                ConditionExpression=ConditionExpression,
                ConditionConnector=ConditionConnector,
                ExpressionAttributeValues=ExpressionAttributeValues,
                store_in=kwargs,
            )

            transact_items = [
                {
                    "Delete": {
                        "TableName": self.table_name,
                        "Key": self._format_key(key_fn(i)),
                    }
                    | kwargs
                }
                for i in items
            ]
        else:
            raise ValueError(f"Unsupported transact_items() operation: {operation}")

        num_items = len(transact_items)
        s = 0
        e = min(100, num_items)
        while s < num_items:
            try:
                transact_slice = transact_items[s:e]
                self.ddb_client.transact_write_items(TransactItems=transact_slice)

                s = e
                e = s + min(100, num_items - s)
            except self.ddb_client.exceptions.TransactionCanceledException as e:
                return s

        return num_items

    def batch_get_item(
        self,
        items: List[DynamoAttr | dict],
        *,
        ConsistentRead: bool = False,
    ) -> List[dict]:
        if len(items) == 0:
            return []

        # The `batch_get_item()` API can only process 100 items at a time
        res = []
        for batch in batched(items, 100):
            RequestItems = {
                self.table_name: {
                    "Keys": [self._format_key(i) for i in batch],
                    "ConsistentRead": ConsistentRead,
                }
            }

            response = self.ddb_client.batch_get_item(RequestItems=RequestItems)

            # There should be only one key/table with items in the dictionary
            table_name = next(iter(response["Responses"]))
            res.extend(response["Responses"][table_name])
        return res

    def batch_delete_item(
        self,
        items: List[DynamoAttr | dict],
    ) -> None:
        if len(items) == 0:
            return

        # The `batch_write_item()` API can only process 25 items at a time
        # Plus, good news: Double-deletions won't throw an exception, see:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb/client/batch_write_item.html
        # In other words, if two separate processes/machines delete the same item,
        # the batch-deletion succeeds, and Dyanmo ignores the double-deletion.
        for batch in batched(items, 25):
            RequestItems = {self.table_name: [{"DeleteRequest": {"Key": self._format_key(i)}} for i in batch]}

            self.ddb_client.batch_write_item(RequestItems=RequestItems)

    @staticmethod
    def get_table_from_name(table_name: str) -> "DynamoTable":
        ddb_client = boto3.client("dynamodb")
        return DynamoTable(ddb_client, table_name)

    @staticmethod
    def get_table_from_session(session: boto3.Session, table_name: str) -> "DynamoTable":
        ddb_client = session.client("dynamodb")
        return DynamoTable(ddb_client, table_name)

    @staticmethod
    def get_tables_from_env(senv: SolverEnvironment) -> Tuple["DynamoTable", "DynamoTable"]:
        if senv.is_local:
            if senv.is_distributed:
                shared_dir = os.environ.get("SHARED_STATE_DIR", "/shared")
                ip_table = LocalDynamoTable(
                    os.path.join(shared_dir, "ip_table.json"),
                    "local-ip-table",
                )
                timestamp_table = LocalDynamoTable(
                    os.path.join(shared_dir, "timestamp_table.json"),
                    "local-timestamp-table",
                )
                return ip_table, timestamp_table
            return None, None
        else:
            rn = senv.to_resource_namer()
            ip_table = DynamoTable.get_table_from_name(rn.get_ip_table_name())
            timestamp_table = DynamoTable.get_table_from_name(rn.get_timestamp_table_name())
            return ip_table, timestamp_table


################################################################################
# Local DynamoDB shim for multi-container local testing
################################################################################


class LocalConditionalCheckFailed(Exception):
    """Raised when a conditional expression check fails on a LocalDynamoTable."""

    pass


class LocalDynamoTable:
    """File-backed local DynamoDB table for multi-container local testing.

    Stores items in DynamoDB wire format so DynamoAttr.from_dict() works unchanged.
    Uses fcntl.flock(LOCK_EX) for cross-container file-level locking.
    """

    def __init__(self, file_path: str, table_name: str):
        self.file_path = file_path
        self.table_name = table_name
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Create the JSON file with {} if it doesn't exist."""
        dir_path = os.path.dirname(self.file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w") as f:
                json.dump({}, f)

    def _read_data(self, f) -> dict:
        """Read JSON data from an already-locked file handle."""
        f.seek(0)
        content = f.read()
        if not content:
            return {}
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"Corrupt JSON in {self.file_path}, re-initializing")
            return {}

    def _write_data(self, f, data: dict):
        """Write JSON data to an already-locked file handle."""
        f.seek(0)
        f.truncate()
        json.dump(data, f)
        f.flush()

    def _extract_partition_key(self, Key) -> str:
        """Extract the partition key string value from a Key argument."""
        if isinstance(Key, DynamoAttr):
            return str(Key.value)
        elif isinstance(Key, dict):
            # Key is in typed format: { 'keyName': { 'S': 'value' } }
            for k, v in Key.items():
                if isinstance(v, dict):
                    for type_code, val in v.items():
                        return str(val)
                return str(v)
        raise ValueError(f"Cannot extract partition key from {Key}")

    def _format_key(self, Key) -> dict:
        """Format a Key into DynamoDB wire format dict."""
        if isinstance(Key, DynamoAttr):
            return Key.typed_key_val()
        elif isinstance(Key, dict):
            return Key
        raise ValueError(f"Expected DynamoAttr or dict, got {Key}")

    def _build_expr_attr_vals(self, ExpressionAttributeValues) -> dict:
        """Build a flat alias->typed_value dict from ExpressionAttributeValues."""
        if ExpressionAttributeValues is None:
            return {}
        xs = ExpressionAttributeValues
        if isinstance(xs, DynamoAttr) or isinstance(xs, dict):
            xs = [xs]
        d = {}
        for x in xs:
            if isinstance(x, DynamoAttr):
                d.update(x.typed_alias_val())
            elif isinstance(x, dict):
                d.update(x)
        return d

    def _build_update_expr_string(self, UpdateExpression) -> str:
        """Build a SET update expression string."""
        if UpdateExpression is None:
            return ""
        if isinstance(UpdateExpression, str):
            return UpdateExpression
        if isinstance(UpdateExpression, DynamoAttr):
            UpdateExpression = [UpdateExpression]
        parts = []
        for x in UpdateExpression:
            if isinstance(x, DynamoAttr):
                parts.append(x.eq_alias())
            else:
                parts.append(str(x))
        return "SET " + ", ".join(parts)

    def _build_condition_expr_string(self, ConditionExpression, ConditionConnector=" AND ") -> str:
        """Build a condition expression string."""
        if ConditionExpression is None:
            return ""
        if isinstance(ConditionExpression, str):
            return ConditionExpression
        if isinstance(ConditionExpression, DynamoAttr):
            ConditionExpression = [ConditionExpression]
        parts = []
        for x in ConditionExpression:
            if isinstance(x, DynamoAttr):
                parts.append(x.eq_alias())
            else:
                parts.append(str(x))
        return ConditionConnector.join(parts)

    def _resolve_typed_value(self, typed_val: dict):
        """Extract the raw value from a DynamoDB typed value dict like {'S': 'foo'}."""
        for type_code, val in typed_val.items():
            if type_code == "BOOL":
                return val
            elif type_code == "N":
                # Keep as string for comparison, convert to numeric when needed
                return val
            else:
                return val
        return None

    def _compare_values(self, left, right, op: str) -> bool:
        """Compare two values with the given operator. Handles numeric strings."""
        # Try numeric comparison
        try:
            left_num = float(left) if not isinstance(left, bool) else left
            right_num = float(right) if not isinstance(right, bool) else right
            if op == "=":
                return left_num == right_num
            elif op == "<":
                return left_num < right_num
            elif op == "<=":
                return left_num <= right_num
            elif op == ">":
                return left_num > right_num
            elif op == ">=":
                return left_num >= right_num
        except (ValueError, TypeError):
            pass
        # Fall back to string/direct comparison
        if op == "=":
            return left == right
        elif op == "<":
            return str(left) < str(right)
        elif op == "<=":
            return str(left) <= str(right)
        elif op == ">":
            return str(left) > str(right)
        elif op == ">=":
            return str(left) >= str(right)
        return False

    def _evaluate_condition(self, expr_str: str, item: dict, attr_vals: dict) -> bool:
        """Evaluate a condition/filter expression against an item.

        Supports expressions like 'key = :alias' and 'key < :alias' connected by AND.
        """
        if not expr_str:
            return True

        # Split by AND
        clauses = [c.strip() for c in expr_str.split(" AND ")]
        for clause in clauses:
            # Parse 'key op :alias' pattern
            match = re.match(r"(\w+)\s*(=|<|<=|>|>=)\s*(:\w+)", clause)
            if not match:
                continue
            attr_name, op, alias = match.groups()

            # Get the expected value from attr_vals
            if alias not in attr_vals:
                continue
            expected_typed = attr_vals[alias]
            expected_val = self._resolve_typed_value(expected_typed)

            # Get the actual value from the item
            if attr_name not in item:
                # Attribute doesn't exist in item — condition fails for = checks
                if op == "=":
                    return False
                continue
            actual_typed = item[attr_name]
            actual_val = self._resolve_typed_value(actual_typed)

            if not self._compare_values(actual_val, expected_val, op):
                return False

        return True

    def _apply_update(self, item: dict, update_str: str, attr_vals: dict, key_dict: dict) -> dict:
        """Apply a SET update expression to an item. Returns the updated item."""
        # Ensure the key attributes are in the item
        item.update(key_dict)

        # Parse 'SET attr1 = :alias1, attr2 = :alias2'
        set_body = update_str
        if set_body.upper().startswith("SET "):
            set_body = set_body[4:]

        assignments = [a.strip() for a in set_body.split(",")]
        for assignment in assignments:
            match = re.match(r"(\w+)\s*=\s*(:\w+)", assignment.strip())
            if not match:
                continue
            attr_name, alias = match.groups()
            if alias in attr_vals:
                item[attr_name] = attr_vals[alias]

        return item

    # ---- Public interface (matches DynamoTable) ----

    def update_item(
        self,
        Key,
        UpdateExpression,
        *,
        ConditionExpression=None,
        ConditionConnector: str = " AND ",
        ExpressionAttributeValues=None,
        **kwargs,
    ) -> None:
        attr_vals = self._build_expr_attr_vals(ExpressionAttributeValues)
        update_str = self._build_update_expr_string(UpdateExpression)
        cond_str = self._build_condition_expr_string(ConditionExpression, ConditionConnector)
        pk = self._extract_partition_key(Key)
        key_dict = self._format_key(Key)

        with open(self.file_path, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                data = self._read_data(f)
                item = data.get(pk, {})

                # Evaluate condition
                if cond_str and not self._evaluate_condition(cond_str, item, attr_vals):
                    raise LocalConditionalCheckFailed(f"Condition check failed for key {pk}")

                # Apply update
                item = self._apply_update(item, update_str, attr_vals, key_dict)
                data[pk] = item
                self._write_data(f, data)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def get_item(
        self,
        Key,
        *,
        ConsistentRead: bool = False,
    ) -> Optional[dict]:
        pk = self._extract_partition_key(Key)

        with open(self.file_path, "r") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                data = self._read_data(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        return data.get(pk)

    def delete_item(
        self,
        Key,
        *,
        ConditionExpression=None,
        ConditionConnector: str = " AND ",
        ExpressionAttributeValues=None,
        **kwargs,
    ):
        attr_vals = self._build_expr_attr_vals(ExpressionAttributeValues)
        cond_str = self._build_condition_expr_string(ConditionExpression, ConditionConnector)
        pk = self._extract_partition_key(Key)

        with open(self.file_path, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                data = self._read_data(f)
                item = data.get(pk, {})

                if cond_str and not self._evaluate_condition(cond_str, item, attr_vals):
                    raise LocalConditionalCheckFailed(f"Condition check failed for key {pk}")

                data.pop(pk, None)
                self._write_data(f, data)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def scan(
        self,
        Select=None,
        *,
        FilterExpression=None,
        FilterConnector: str = " AND ",
        ExpressionAttributeValues=None,
        ConsistentRead: bool = False,
        **kwargs,
    ) -> dict:
        attr_vals = self._build_expr_attr_vals(ExpressionAttributeValues)
        filter_str = self._build_condition_expr_string(FilterExpression, FilterConnector)

        with open(self.file_path, "r") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                data = self._read_data(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        items = []
        for pk, item in data.items():
            if self._evaluate_condition(filter_str, item, attr_vals):
                items.append(item)

        return {"Items": items}

    def transact_items(
        self,
        items,
        key_fn,
        operation=None,
        *,
        ConditionExpression=None,
        ConditionConnector: str = " AND ",
        UpdateExpression=None,
        ExpressionAttributeValues=None,
        **kwargs,
    ) -> int:
        if len(items) == 0:
            return 0

        attr_vals = self._build_expr_attr_vals(ExpressionAttributeValues)
        update_str = self._build_update_expr_string(UpdateExpression)
        cond_str = self._build_condition_expr_string(ConditionExpression, ConditionConnector)

        with open(self.file_path, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                data = self._read_data(f)
                count = 0

                for item_obj in items:
                    key = key_fn(item_obj)
                    pk = self._extract_partition_key(key)
                    key_dict = self._format_key(key)
                    current = data.get(pk, {})

                    try:
                        if cond_str and not self._evaluate_condition(cond_str, current, attr_vals):
                            raise LocalConditionalCheckFailed(f"Condition check failed for key {pk}")

                        if update_str:
                            current = self._apply_update(current, update_str, attr_vals, key_dict)
                            data[pk] = current
                        else:
                            # Delete operation
                            data.pop(pk, None)

                        count += 1
                    except LocalConditionalCheckFailed:
                        self._write_data(f, data)
                        return count

                self._write_data(f, data)
                return count
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def batch_get_item(
        self,
        items,
        *,
        ConsistentRead: bool = False,
    ) -> List[dict]:
        if len(items) == 0:
            return []

        with open(self.file_path, "r") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                data = self._read_data(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        results = []
        for key in items:
            pk = self._extract_partition_key(key)
            if pk in data:
                results.append(data[pk])
        return results

    def batch_delete_item(
        self,
        items,
    ) -> None:
        if len(items) == 0:
            return

        with open(self.file_path, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                data = self._read_data(f)
                for key in items:
                    pk = self._extract_partition_key(key)
                    data.pop(pk, None)
                self._write_data(f, data)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
