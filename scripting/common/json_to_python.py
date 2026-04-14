"""
Abstract base class for classes that are parsed to/from JSONs.

After implementing parsing `from_dict()` and `to_dict()`,
this class automatically implements ways of converting the object
to a JSON string, or reading/writing the JSON to a file.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Type, TypeVar

from . import pathing

T = TypeVar("T", bound="JsonToPythonObject")


@dataclass
class JsonToPythonObject:
    """
    Abstract base class for classes that are parsed to/from JSON.

    Subclasses must implement these two functions:
    ```
    @classmethod
    def from_dict(cls: Type[T], d: dict) -> T:

    def to_dict(self) -> dict:
    ```
    """

    @classmethod
    def from_dict(cls: Type[T], d: dict) -> T:
        """Parse this object from a provided dictionary."""

    @classmethod
    def from_json(cls: Type[T], j: str) -> T:
        """Parse this object from a provided JSON string."""
        return cls.from_dict(json.loads(j))

    @classmethod
    def from_json_file(cls: Type[T], json_file: Path | str) -> T:
        """Parse this object from a provided JSON file."""
        json_path = pathing.normalize_path(json_file)
        with open(json_path, "r") as f:
            json_dict = json.load(f)
        return cls.from_dict(json_dict)

    def to_dict(self) -> dict:
        """Turn this object into a Python dictionary."""

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def write_to_json_file(self, json_file: Path | str) -> None:
        json_path = pathing.normalize_path(json_file)
        with open(json_path, "w") as f:
            f.write(self.to_json())
            f.write("\n")
