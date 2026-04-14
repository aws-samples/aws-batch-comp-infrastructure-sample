"""Property-based tests for double-hyphen validation.

**Validates: Requirements 1.1, 1.2, 2.1, 2.2**

Property 1: Double-hyphen validation rejects iff separator is present.
For any string s, check_no_double_hyphen rejects s iff "--" is in s.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from runner.runner_config import check_no_double_hyphen, FIELD_SEPARATOR


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

# Strings that never contain "--": lowercase ascii with optional single hyphens.
# We filter out any accidental "--" occurrences.
valid_name = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-"),
    min_size=1,
    max_size=60,
).filter(lambda s: FIELD_SEPARATOR not in s)

# Strings that always contain at least one "--" substring.
invalid_name = st.builds(
    lambda prefix, suffix: prefix + FIELD_SEPARATOR + suffix,
    prefix=st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-"),
        min_size=0,
        max_size=30,
    ),
    suffix=st.text(
        alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-"),
        min_size=0,
        max_size=30,
    ),
)


# ---------------------------------------------------------------------------
# Property 1: Double-hyphen validation rejects iff separator is present
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(name=valid_name)
def test_accepts_names_without_double_hyphen(name):
    """Names without '--' must be accepted (no SystemExit).

    **Validates: Requirements 1.2, 2.2**
    """
    # Should return normally — no exception
    check_no_double_hyphen(name, "Test label")


@settings(max_examples=200)
@given(name=invalid_name)
def test_rejects_names_with_double_hyphen(name):
    """Names containing '--' must be rejected via SystemExit.

    **Validates: Requirements 1.1, 2.1**
    """
    with pytest.raises(SystemExit):
        check_no_double_hyphen(name, "Test label")
