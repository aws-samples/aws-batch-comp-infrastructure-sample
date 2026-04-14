"""Property-based tests for scoped naming convention.

**Validates: Requirements 3.1, 3.2, 4.1, 5.1, 6.1**

Property 2: Scoped names follow the naming convention.
For any valid project name and solver name (neither containing "--"),
and for any resource type in {solver, loggroup, taskdef, container, image},
the generated resource name starts with satcomp--{type}--{project}--{solver}
and splitting on "--" recovers each field.
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

# Resource types that map to solver-scoped naming methods.
resource_type = st.sampled_from(["solver", "loggroup", "taskdef", "container", "image"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_scoped_name(rn: ResourceNamer, res_type: str, solver: str) -> str:
    """Call the appropriate ResourceNamer method for the given resource type."""
    if res_type == "solver":
        return rn.get_solver_stack_name(solver)
    elif res_type == "loggroup":
        return rn.get_log_group_stack_name(solver)
    elif res_type == "taskdef":
        return rn.get_task_def_name(solver, is_leader=True)
    elif res_type == "container":
        return rn.get_container_name(solver)
    elif res_type == "image":
        return rn.get_ecr_image_tag(solver)
    raise ValueError(f"Unknown resource type: {res_type}")


# ---------------------------------------------------------------------------
# Property 2: Scoped names follow the naming convention
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(project=valid_name, solver=valid_name, res_type=resource_type)
def test_scoped_name_starts_with_convention(project, solver, res_type):
    """Generated name starts with satcomp--{type}--{project}--{solver}.

    **Validates: Requirements 3.1, 3.2, 4.1, 5.1, 6.1**
    """
    rn = ResourceNamer(project=project)
    name = _get_scoped_name(rn, res_type, solver)

    expected_prefix = f"satcomp--{res_type}--{project}--{solver}"
    assert name.startswith(expected_prefix), (
        f"Expected name to start with '{expected_prefix}', got '{name}'"
    )


@settings(max_examples=200)
@given(project=valid_name, solver=valid_name, res_type=resource_type)
def test_scoped_name_fields_recoverable(project, solver, res_type):
    """Splitting on '--' recovers prefix, resource type, project, and solver.

    **Validates: Requirements 3.1, 3.2, 4.1, 5.1, 6.1**
    """
    rn = ResourceNamer(project=project)
    name = _get_scoped_name(rn, res_type, solver)

    parts = name.split("--")

    # Must have at least 4 fields: prefix, type, project, solver(+suffix)
    assert len(parts) >= 4, f"Expected >= 4 parts, got {parts}"
    assert parts[0] == "satcomp", f"Expected prefix 'satcomp', got '{parts[0]}'"
    assert parts[1] == res_type, f"Expected type '{res_type}', got '{parts[1]}'"
    assert parts[2] == project.lower(), f"Expected project '{project.lower()}', got '{parts[2]}'"

    # The last part starts with the solver name (may have a suffix like "Stack", "Leader")
    assert parts[3].startswith(solver), (
        f"Expected last part to start with solver '{solver}', got '{parts[3]}'"
    )
