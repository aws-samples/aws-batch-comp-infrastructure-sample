# Testing

This page documents the testing approach and conventions for the project functionality itself. It does not cover solver testing. 

## Test Setup

Tests use pytest with the Python path configured to include `scripting/`:

```bash
source satcomp-activate.sh
pytest
```

The virtual environment script sets up `PYTHONPATH` automatically.

## Running Tests

### All Tests

```bash
pytest
```

### Specific Test File

```bash
pytest tests/test_resource_namer.py
```

### Tests Matching Pattern

```bash
pytest -k "test_round_trip"
```

### Specific Test Class

```bash
pytest tests/test_prepare_jobs.py::TestS3Source
```

### Verbose Output

```bash
pytest -v
```

## Test Organization

Tests are located in the `tests/` directory:

```
tests/
  test_resource_namer.py    # ResourceNamer unit tests
  test_runner_config.py     # Config parsing tests
  test_prepare_jobs.py      # Job preparation tests
  test_ecs.py               # ECS integration tests
  test_pipeline.py          # End-to-end pipeline tests
  conftest.py               # Shared fixtures
```

## AWS Integration Tests

Some tests require AWS credentials and are marked with `@requires_aws`:

```python
import pytest

@pytest.mark.requires_aws
def test_s3_upload():
    # This test only runs with valid AWS credentials
    pass
```

These tests are automatically skipped when credentials are not available.

### Running Integration Tests

With AWS credentials configured:

```bash
pytest -m "requires_aws"
```

To skip integration tests:

```bash
pytest -m "not requires_aws"
```

## Mocking AWS Services

For unit tests, AWS services are mocked using local implementations:

### S3 Mocking

```python
from harness.aws_shim import S3FileSystem

# The S3FileSystem can operate in local mode
s3 = S3FileSystem(is_aws=False, local_root="/tmp/test_s3")
```

### SQS Mocking

```python
from harness.aws_shim import LocalSqsQueue

# LocalSqsQueue provides in-memory queue for testing
queue = LocalSqsQueue()
queue.send_message("test message")
message = queue.get_message()
```

### DynamoDB Mocking

Tests can use local dictionary-based implementations or moto library:

```python
import moto
import boto3

@moto.mock_dynamodb
def test_dynamo_operations():
    client = boto3.client('dynamodb', region_name='us-east-1')
    # ... test code
```

## Test Fixtures

Common fixtures are defined in `conftest.py`:

```python
import pytest

@pytest.fixture
def sample_config():
    """Returns a minimal ProjectConfig for testing."""
    return ProjectConfig(
        project="testproject",
        profile="default",
        region="us-east-1",
        solver_type="sat",
        solvers=[...]
    )

@pytest.fixture
def temp_dir(tmp_path):
    """Provides a temporary directory for test files."""
    return tmp_path
```

## Writing Tests

### Unit Test Example

```python
def test_resource_namer_solver_stack():
    namer = ResourceNamer(project="myproj", solver="solver1")
    assert namer.solver_stack() == "satcomp--solver--myproj--solver1Stack"

def test_resource_namer_rejects_double_hyphen():
    with pytest.raises(ValueError):
        ResourceNamer(project="my--project", solver="solver1")
```

### Integration Test Example

```python
import pytest

@pytest.mark.requires_aws
def test_s3_upload_download(sample_config, tmp_path):
    s3 = S3FileSystem.from_config(sample_config)

    # Create test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")

    # Upload
    s3.upload_file(test_file, "s3://bucket/test.txt")

    # Download
    downloaded = tmp_path / "downloaded.txt"
    s3.download_file("s3://bucket/test.txt", downloaded)

    assert downloaded.read_text() == "hello world"
```

### Parameterized Tests

```python
import pytest

@pytest.mark.parametrize("result_line,expected", [
    ("s SATISFIABLE", SolverResultCode.SAT),
    ("s UNSATISFIABLE", SolverResultCode.UNSAT),
    ("s UNKNOWN", SolverResultCode.UNKNOWN),
    ("c comment", SolverResultCode.INDETERMINATE),
])
def test_parse_solver_result(result_line, expected):
    # Write result to temp file and parse
    ...
```

## Test Conventions

### Naming

- Test files: `test_<module_name>.py`
- Test functions: `test_<what_is_being_tested>`
- Test classes: `Test<ComponentName>`

### Assertions

Use plain `assert` statements:

```python
def test_something():
    result = function_under_test()
    assert result == expected_value
    assert "key" in result
    assert result.count > 0
```

### Cleanup

Use fixtures or context managers for cleanup:

```python
@pytest.fixture
def temp_config_file(tmp_path):
    config_file = tmp_path / "config.yml"
    config_file.write_text("project: test\n...")
    yield config_file
    # Cleanup happens automatically
```

## Continuous Integration

### Acceptance Test Suite

The project includes an acceptance test suite for validating solver submissions. This runs solvers against generated formulas covering SAT, UNSAT, timeout, OOM, and malformed input scenarios.

```bash
# Run acceptance tests (builds Docker images automatically)
./satcomp.py config.yml --acceptance-test mysolver

# Run local tests (requires pre-built images)
./satcomp.py config.yml --test-local mysolver

# Distributed local tests
./satcomp.py config.yml --test-local mysolver --num-workers 2
```

The acceptance test formulas live in `test_formulas/` at the repository root. This directory should be generated by running `./tools/generate_test_formulas.sh` from the repository root (it creates CNF formulas in `test_formulas/cnf/` and SMT-LIB formulas in `test_formulas/smtlib/`). The `--acceptance-test` command uses these formulas, while `--test-local` uses the formulas in `examples/formulas/`. The Docker image also contains a copy of `examples/formulas/` at `/opt/amazon/test_formulas/` for manual, in-container testing.

### CI Tests

Tests run automatically on pull requests. Ensure all tests pass before merging:

```bash
pytest --tb=short  # Shorter traceback for CI output
```

## Further Reading

- [Architecture](01-architecture.md) - System overview
- [Key Abstractions](02-key-abstractions.md) - Classes used in tests
- [pytest documentation](https://docs.pytest.org/)
