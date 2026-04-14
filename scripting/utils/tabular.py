"""Pretty print tabular data."""

from enum import Enum
from logging import Logger
from typing import List, Tuple

from common import LoggingManager

lm = LoggingManager()
logger = lm.get_logger("Tabular", formatted=False)


class TabularRow(Enum):
    HEADERS = 0
    ROW = 1
    STR = 2  # An explanation string in the middle of the rows


class Tabular:

    DEFAULT_COL_SEP_SPACES = 4
    MAX_COL_LEN = 30

    def __init__(
        self,
        num_columns: int,
        spaces_between_columns: int = DEFAULT_COL_SEP_SPACES,
        max_column_length: int | None = MAX_COL_LEN,
    ):
        """
        Create a new table. Specify the number of columns.

        Setting `max_column_length = None` will let the columns have unlimited length.
        """
        self.num_columns = num_columns
        self.spaces_between_columns = spaces_between_columns
        self.max_allowed_col_len = max_column_length

        self.rows: List[Tuple[TabularRow, str | List[str]]] = []
        self.max_col_lens: List[int] = [0] * self.num_columns
        self.has_added_headers = False

    def __update_max_lens(self, l: List[str]):
        # For each header, update the maximum length of the header
        for i in range(self.num_columns):
            self.max_col_lens[i] = max(self.max_col_lens[i], len(l[i]))
            if self.max_allowed_col_len is not None:
                self.max_col_lens[i] = min(self.max_col_lens[i], self.max_allowed_col_len)

    def add_headers(self, headers: List[str]):
        """
        Sets the headers for the table. Can only be called once per table.

        Invokes `str()` on each list element.
        """
        headers = [str(x) for x in headers]
        if len(headers) != self.num_columns:
            logger.error(
                f"Tabular.add_headers(): the passed list had {len(headers)} headers,"
                f" but {self.num_columns} headers were expected"
            )
            exit(1)

        if self.has_added_headers:
            logger.error("add_headers(): headers were already added.")
            exit(1)

        self.__update_max_lens(headers)
        self.has_added_headers = True
        row = (TabularRow.HEADERS, headers)
        self.rows.append(row)

    def add_row(self, cols: str | List[str], na: str = ""):
        """
        Adds a new row to the table. Missing columns are filled in with `na`.

        If `cols` is a `str`, adds the string as-is.

        If `cols` is a list of strings, this function invokes `str()` on each list element.
        """
        if isinstance(cols, str):
            row = (TabularRow.STR, cols)
            self.rows.append(row)
            return

        if len(cols) > self.num_columns:
            logger.error(
                f"Tabular.add_row(): the passed list had {len(cols)} columns,"
                f" but at most {self.num_columns} columns were expected"
            )

        # Pad missing columns with `na`
        num_missing_cols = max(0, self.num_columns - len(cols))
        cols = [str(x) for x in cols] + ([na] * num_missing_cols)

        self.__update_max_lens(cols)
        row = (TabularRow.ROW, cols)
        self.rows.append(row)

    def get_tablular_string(self) -> str:
        prev_row_type = None
        s = ""

        num_rows = len(self.rows)
        for i in range(num_rows):
            row_type, row = self.rows[i]
            if row_type == TabularRow.HEADERS or row_type == TabularRow.ROW:
                # Add a newline between non-HEADERS/ROW sections
                if (
                    prev_row_type is not None
                    and prev_row_type != TabularRow.HEADERS
                    and prev_row_type != TabularRow.ROW
                ):
                    s += "\n"

                for j in range(self.num_columns):
                    col = row[j]
                    max_col_len = self.max_col_lens[j]
                    desired_len = max_col_len + self.spaces_between_columns

                    # Cut the string off to the maximum allowed length,
                    # then pad spaces to the desired length (if not last column)
                    if j < self.num_columns - 1:
                        s += col[: self.max_allowed_col_len].ljust(desired_len)
                    else:
                        s += col[: self.max_allowed_col_len]
            elif row_type == TabularRow.STR:
                if prev_row_type is not None and prev_row_type != TabularRow.STR:
                    s += "\n"
                s += row
            else:
                logger.error("Unsupported TabularRow type")
                exit(1)

            prev_row_type = row_type

            # Add a new line to the end of the line only this isn't the last row
            if i < num_rows - 1:
                s += "\n"

        return s

    def print(self):
        s = self.get_tablular_string()
        print(s)

    def log(self, l: Logger):
        s = self.get_tablular_string()
        l.info(s)
