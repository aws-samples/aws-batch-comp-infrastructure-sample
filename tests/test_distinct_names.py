"""Property-based tests for distinct inputs producing distinct resource names.

**Validates: Requirements 3.1, 4.1, 5.1, 6.1**

Property 4: Distinct inputs produce distinct resource names.
For any two distinct (project, solver) pairs where neither contains "--",
all corresponding resource names from one pair differ from those of the other pair.
"""

from hypothesis import given, assume, settings
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
# Helpers
# ---------------------------------------------------------------------------

def _all_solver_scoped_names(rn: ResourceNamer, solver: str) -> list[str]:
    """Return all solver-scoped resource names for a given (project, solver)."""
    return [
        rn.get_solver_stack_name(solver),
        rn.get_log_group_stack_name(solver),
        rn.get_task_def_name(solver, is_leader=True),
        rn.get_container_name(solver),
        rn.get_ecr_image_tag(solver),
    ]


# ---------------------------------------------------------------------------
# Property 4: Distinct inputs produce distinct resource names
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    project1=valid_name,
    solver1=valid_name,
    project2=valid_name,
    solver2=valid_name,
)
def test_distinct_pairs_produce_distinct_names(project1, solver1, project2, solver2):
    """Two distinct (project, solver) pairs must produce entirely distinct resource names.

    **Validates: Requirements 3.1, 4.1, 5.1, 6.1**
    """
    assume((project1, solver1) != (project2, solver2))

    rn1 = ResourceNamer(project=project1)
    rn2 = ResourceNamer(project=project2)

    names1 = _all_solver_scoped_names(rn1, solver1)
    names2 = _all_solver_scoped_names(rn2, solver2)

    for n1, n2 in zip(names1, names2):
        assert n1 != n2, (
            f"Collision detected: ({project1!r}, {solver1!r}) and "
            f"({project2!r}, {solver2!r}) both produced {n1!r}"
        )
