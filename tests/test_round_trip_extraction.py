"""Property-based tests for round-trip solver extraction from resource names.

**Validates: Requirements 6.2, 7.2, 7.3**

Property 3: Round-trip solver extraction from resource names.
For any valid solver name (not containing "--"), generating an ECR image tag
with get_ecr_image_tag(solver) and then extracting the solver with
get_solver_from_ecr_image_tag(tag) returns the original solver name.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from common.resource_namer import ResourceNamer


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

# Valid name: lowercase ASCII + digits + optional single hyphens, no "--",
# must not start or end with a hyphen (mirrors Docker naming constraints).
valid_name = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-"),
    min_size=1,
    max_size=60,
).filter(lambda s: "--" not in s and not s.startswith("-") and not s.endswith("-"))


# ---------------------------------------------------------------------------
# Property 3: Round-trip solver extraction from resource names
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(project=valid_name, solver=valid_name)
def test_round_trip_ecr_image_tag(project, solver):
    """get_solver_from_ecr_image_tag(get_ecr_image_tag(solver)) == solver.

    **Validates: Requirements 6.2, 7.2, 7.3**
    """
    rn = ResourceNamer(project=project)
    tag = rn.get_ecr_image_tag(solver)
    extracted = rn.get_solver_from_ecr_image_tag(tag)
    assert extracted == solver, (
        f"Round-trip failed: solver={solver!r}, tag={tag!r}, extracted={extracted!r}"
    )
