# Local Testing Example

This directory contains example configuration files for using the `test-local` command with custom formula directories and results output.

## Files

- `config-test-local.yml` - Example solver configuration for local testing
- `jobs-test-local.yml` - Example jobs file with custom formula directory settings

## Usage

### Basic Usage (Default Formulas)

Test all solvers using the default `examples/formulas/` directory:

```bash
source satcomp-activate.sh
satcomp.py config.yml build
satcomp.py config.yml test-local
```

### Custom Formula Directory

Use a custom formula directory specified in a jobs file:

```bash
satcomp.py config.yml \
    --jobs-test-local jobs-test-local.yml \
    test-local
```

### Save Results to Directory

Write test results to a directory for CI/CD integration:

```bash
satcomp.py config.yml \
    --results-dir ./test-results \
    test-local
```

### Full Example

Combine custom formulas with results output:

```bash
satcomp.py config.yml \
    --jobs-test-local jobs-test-local.yml \
    --results-dir ./test-results \
    test-local my-solver
```

## Results Output

When `--results-dir` is specified, the following structure is created:

```
test-results/
├── summary.yml           # Overall summary with pass/fail counts
└── my-solver/
    └── cnf_easy_test.cnf/
        ├── solver_out.json   # AWS-compatible solver output
        ├── stdout.log
        └── stderr.log
```

### summary.yml Format

```yaml
timestamp: "2026-03-01T10:30:00+00:00"
formula_dir: /path/to/examples/formulas
expected_file: /path/to/expected.yml
total_passed: 8
total_failed: 2
solvers:
  my-solver:
    passed: 4
    failed: 1
    tests:
      - name: cnf/easy/sat.cnf
        expected: SAT
        actual: SAT
        passed: true
        time_seconds: 0.42
```

## Jobs File Settings

The jobs file supports these test-local specific fields:

```yaml
# Local formula directory (relative to jobs file or absolute)
formula_dir_test_local: my_tests/formulas/

# Optional: Explicit path to expected.yml
expected_file_test_local: my_tests/expected.yml
```

### Resolution Order

**Formula directory:**
1. `formula_dir_test_local` from jobs file
2. Default `examples/formulas/` in project root

**Expected.yml:**
1. `expected_file_test_local` from jobs file
2. `expected.yml` in formula directory (if custom)
3. Default `examples/formulas/expected.yml`
