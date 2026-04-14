"""Solver acceptance testing framework."""

from .result_validator import (
    ResultValidator,
)
from .test_models import (
    TestCaseDefinition,
    TestCaseResult,
    TestReport,
)
from .test_registry import (
    TestCaseRegistry,
)

__all__ = [
    "TestCaseDefinition",
    "TestCaseResult",
    "TestReport",
    "TestCaseRegistry",
    "ResultValidator",
]
