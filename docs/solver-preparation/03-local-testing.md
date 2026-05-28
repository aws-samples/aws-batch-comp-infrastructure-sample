# Local Testing

This page explains how to build and test your solver locally before deploying to AWS.

## Overview

Testing locally helps you:
- Verify your Dockerfile builds correctly
- Ensure your solver runs as expected
- Debug issues without AWS costs
- Iterate quickly during development

## Testing with `test-local`

The `test-local` command provides automated validation of your solver Docker image. It runs your solver against a suite of test formulas and checks that results match expected outcomes.

### Usage

```bash
# Test all solvers defined in config.yml against default suite
satcomp.py config.yml test-local

# Test a specific solver from config.yml
satcomp.py config.yml test-local mysolver

# Supply your own formula directory (specified in jobs.yml)
satcomp.py config.yml --jobs-test-local jobs.yml test-local

# Save results to a directory; you could use this during CI/CD integration
satcomp.py config.yml --results-dir ./test-results test-local

# Combine multiple options
satcomp.py config.yml --jobs-test-local jobs.yml --results-dir ./results test-local mysolver
```

### Prerequisites

Before running `test-local`, you must build your solver image:

```bash
source satcomp-activate.sh
satcomp.py config.yml build   # Build your solver image
```

### Test Categories

The test suite includes formulas in three categories:

| Category | Purpose | Expected Behavior |
|----------|---------|-------------------|
| **easy** | SAT/UNSAT verification | Solver should return correct SAT or UNSAT result |
| **hard** | Timeout handling | Solver should timeout gracefully within time limit |
| **malformed** | Error handling | Solver should handle invalid input without crashing |
| **oom** | Memory limit | Solver is killed when exceeding memory (128MB cap) |

### Test Formula Locations

Test formulas are located in the `examples/formulas/` directory:

- `examples/formulas/cnf/` - DIMACS CNF format (for SAT solvers)
- `examples/formulas/smtlib/` - SMT-LIB format (for SMT solvers)

Expected results are defined in `examples/formulas/expected.yml`.

### Custom Formula Directory

You can use a custom formula directory by specifying it in a jobs.yml file:

```yaml
# jobs.yml
results_dir: results
formulas: []
job_options:
  timeout_secs: 1000
  solver_options: []

# test-local specific settings (ignored when running in AWS)
formula_dir_test_local: my_tests/formulas/
expected_file_test_local: my_tests/expected.yml  # Optional
```

Then run with:
```bash
satcomp.py config.yml --jobs-test-local jobs.yml test-local
```

**Resolution order for formula directory:**
1. `formula_dir_test_local` from jobs file
2. Default `examples/formulas/` in project root

**Resolution order for expected.yml:**
1. `expected_file_test_local` from jobs file (if set)
2. `expected.yml` in custom formula directory (if custom dir set)
3. Default `examples/formulas/expected.yml`

### Results Output

Use `--results-dir` to save results for CI/CD integration:

```bash
satcomp.py config.yml --results-dir ./test-results test-local
```

This creates:
```
test-results/
├── summary.yml               # Overall summary
└── mysolver/
    └── cnf_easy_test.cnf/.   # one directory per query file
        ├── solver_out.json   # solver results in same format that AWS will produce
        ├── stdout.log        # solver stdout
        └── stderr.log        # solver stderr
```

**summary.yml format:**
```yaml
timestamp: "2026-03-01T10:30:00+00:00"
formula_dir: /path/to/examples/formulas
expected_file: /path/to/expected.yml
total_passed: 8
total_failed: 2
solvers:
  mysolver:
    passed: 4
    failed: 1
    tests:
      - name: cnf/easy/sat.cnf
        expected: SAT
        actual: SAT
        passed: true
        time_seconds: 0.42
```

### Understanding Results

The command outputs pass/fail results for each test:

```
Running test-local for solver: mysolver
  [PASS] cnf/easy/sat.cnf - SAT (expected: SAT)
  [PASS] cnf/easy/unsat.cnf - UNSAT (expected: UNSAT)
  [PASS] cnf/hard/timeout.cnf - TIMEOUT (expected: TIMEOUT)
  [PASS] cnf/malformed/bad_header.cnf - ERROR (expected: ERROR)

Results: 4 passed, 0 failed
```

### Common Test Failures

| Failure | Likely Cause | Solution |
|---------|--------------|----------|
| SAT formula returns UNSAT | Incorrect solver logic | Fix solver implementation |
| TIMEOUT formula returns SAT/UNSAT | Formula too easy or solver ignores timeout | Use a harder formula or implement timeout |
| ERROR test returns SAT/UNSAT | Solver accepts malformed input | Add input validation |
| All tests timeout | Docker image issue or solver crash | Check logs, verify image builds correctly |

## Building Your Docker Image

### Step 1: Activate the Environment

```bash
source satcomp-activate.sh
```
### Step 2: Build Your Solver Image

```bash
./satcomp.py build
```

This builds Docker images for all solvers in your `config.yml`. To build a specific
solver, ensure only that solver is listed (or comment out others).

### Verifying the Build

Check that your image was created:

```bash
docker images
```

You should see your solver image listed with a tag matching your solver name.

## Testing Your Image Manually

You can run your Docker container directly to test:

```bash
# Run a shell in your container
docker run -it --rm your-solver-image /bin/bash

# Inside the container, test your solver manually
/solver/build-path/my-solver /path/to/test.cnf
```

### Built-in Test Formulas

For convenience, the base image includes small test formulas at `/opt/amazon/test_formulas/`:

```
/opt/amazon/test_formulas/
├── cnf/
│   ├── sat_small_01.cnf      # Small satisfiable CNF
│   ├── unsat_small_01.cnf    # Small unsatisfiable CNF
│   └── malformed_01.cnf      # Malformed CNF for error handling
└── smtlib/
    ├── QF_UF_sat_1.smt2      # QF_UF satisfiable
    ├── QF_UF_unsat_1.smt2    # QF_UF unsatisfiable
    └── smt-sat-easy-*.smt2   # QF_LIA satisfiable formulas
```

Use these to quickly verify your solver works:

```bash
docker run -it --rm your-solver-image /bin/bash

# Test SAT solver
/solver/build/mysolver $TEST_FORMULAS/cnf/sat_small_01.cnf

# Test SMT solver
/solver/build/mysolver $TEST_FORMULAS/smtlib/QF_UF_sat_1.smt2
```

## Common Build Issues

### Issue: Missing Dependencies

**Symptom:** Build fails with "package not found" or similar

**Solution:** Add the missing package to your Dockerfile:
```dockerfile
RUN apt-get update && apt-get install -y <missing-package>
```

### Issue: Permission Denied

**Symptom:** Runtime errors about permissions (e.g., "mkdir: cannot create directory: Permission denied")

**Explanation:** Both `test-local` and AWS run your solver as `ecs-user`, not root.
Any directories or files your solver writes to at runtime must be writable by `ecs-user`.
Even if your Dockerfile uses `USER root` for build steps, the solver process itself
runs as `ecs-user`.

**Solutions:**

Ensure files are owned by `ecs-user`:
```dockerfile
COPY --chown=ecs-user src /solver
```

If your solver creates directories at runtime, pre-create them with correct ownership:
```dockerfile
RUN mkdir /mydir && chown ecs-user:ecs-user /mydir
```

Add executable permissions to your solver binary:
```dockerfile
RUN chmod +x /solver/build/mysolver
```

### Issue: Architecture Mismatch

**Symptom:** Binary won't execute, "cannot execute binary file"

**Solution:** Ensure you're building for `linux/amd64`. The project builds images
for this platform by default.

### Issue: Base Image Not Found

**Symptom:** "FROM satcomp-infrastructure" fails

**Solution:** Build the base image first:
```bash
./satcomp.py build
```

## Testing on AWS (Quick Test)

For a quick AWS test without running a full suite of tests:

1. Deploy infrastructure:
   ```bash
   ./satcomp.py provision
   ```

2. Build and push your image:
   ```bash
   ./satcomp.py build    # use Dockerfile to build docker image
   ./satcomp.py push     # push docker image to AWS
   ```

3. Start a single instance:
   ```bash
   ./satcomp.py start-instances 1
   ```

4. Submit a few test formulas:
   - Add S3 path to a small test set in `jobs.yml`
   - Run `./satcomp.py submit`

5. Check progress:
   ```bash
   ./satcomp.py ls sqs     # Queue depths
   ./satcomp.py ls ecs     # Instance status
   ```

6. Stop and process results:
   ```bash
   ./satcomp.py terminate-instances
   ./satcomp.py collect
   ```

7. Clean up:
   ```bash
   ./satcomp.py teardown all
   ```

## Acceptance Testing

The `--acceptance-test` command runs a built-in acceptance test suite that validates your solver handles all expected scenarios. This is the "admission test" for the competition; we will run the same tests on your solver.

```bash
# Run acceptance tests for a specific solver
./satcomp.py config.yml --acceptance-test mysolver
```

The acceptance suite tests 5 categories using generated formulas:

| Test | Formula | Expected Result |
|------|---------|----------------|
| `sat_small_01` | Small satisfiable CNF | SAT |
| `unsat_small_01` | Small unsatisfiable CNF | UNSAT |
| `timeout_hard_01` | Ramsey formula (hard) | TIMEOUT |
| `oom_large_01` | Large formula | CRASH or INDETERMINATE |
| `malformed_bad_header_01` | Invalid CNF header | CRASH, INDETERMINATE, or UNKNOWN |

All five tests must pass for your solver to be accepted.

## Acceptance Testing on AWS

After passing local acceptance tests, verify your solver works end-to-end on AWS infrastructure. This confirms that the Docker image runs correctly on ECS, communicates with SQS queues, and writes results to S3.

### Step 1: Deploy and start

```bash
./satcomp.py config.yml bootstrap       # One-time account setup
./satcomp.py config.yml provision        # Deploy VPC, ECS, SQS, S3
./satcomp.py config.yml build push       # Build and push Docker image to ECR
./satcomp.py config.yml start-instances 1  # Start one solver instance
```

Wait a few minutes for the EC2 instance to launch and the ECS task to start. Check status with:

```bash
./satcomp.py config.yml ls ecs           # Should show 1 running task
```

### Step 2: Upload test formulas and submit

Upload a known test formula to S3 and create a jobs file:

```bash
# Upload a small SAT formula
aws s3 cp test_formulas/cnf/sat_small_01.cnf \
  s3://<account>-<region>-<project>-solver-results/benchmarks/

# Create a jobs file pointing to it
cat > jobs-aws-test.yml << EOF
results_dir: results
formulas:
  - s3://<account>-<region>-<project>-solver-results/benchmarks/
job_options:
  timeout_secs: 60
  solver_options: []
EOF

# Submit
./satcomp.py config.yml --submit jobs-aws-test.yml
```

### Step 3: Collect and verify results

```bash
# Wait ~60 seconds for the solver to process, then collect
./satcomp.py config.yml --collect jobs-aws-test.yml

# Check the result
cat results/results.txt
```

The output JSON should show `"solving_result": "SAT"` with a non-zero `solver_runtime_millis`.

### Step 4: Clean up

```bash
./satcomp.py config.yml terminate-instances
./satcomp.py config.yml teardown all
```

> **Tip:** You can also attach to the running container to debug interactively — see [Attach to a Running Container](#attach-to-a-running-container-in-aws) below.

### Running Acceptance Tests on AWS

Once your infrastructure is deployed and instances are running, you can run the acceptance test suite directly against AWS:

```bash
./satcomp.py config.yml --acceptance-test --acceptance-test-aws
```

This uploads each test formula to S3, submits jobs via SQS, and validates the results. Tests run in two phases:
1. **Safe tests** (SAT, UNSAT, timeout) — run first to verify basic correctness
2. **Destructive tests** (OOM, malformed) — run second, as they may crash the solver container

Expected results on AWS:

| Test | Expected | Notes |
|------|----------|-------|
| `sat_small_01` | SAT | Should match local result |
| `unsat_small_01` | UNSAT | Should match local result |
| `timeout_hard_01` | TIMEOUT | Solver times out at configured limit |
| `oom_large_01` | INDETERMINATE or CRASH | 200M variable formula exhausts container memory |
| `malformed_bad_header_01` | INDETERMINATE or CRASH | Solver rejects invalid input |

> **Note:** The output queue is automatically purged before each test batch. Ensure your solver instances are running before starting (`ls ecs` should show running tasks).

## Distributed Local Testing

For distributed (multi-node) solvers, use `--test-local` with `--num-workers`:

```bash
# Build images first
./satcomp.py $SATCOMP_ROOT examples/configs/sat-distributed-mallob/config.yml --build

# Test with 2 workers
./satcomp.py $SATCOMP_ROOT examples/configs/sat-distributed-mallob/config.yml --test-local mallob --num-workers 2
```

This starts multiple Docker containers on a bridge network that communicate via MPI/SSH, mimicking the ECS distributed setup. See [Distributed Solvers](04-distributed-solvers.md) for details.

## Debugging Tips

### View Build Output

The `build` command shows Docker's build output. Look for errors in red text.

### Attach to a Running Container in AWS

You can connect to a running ECS task container to debug your solver interactively.

#### Option 1: AWS CLI

```bash
# Find your running task
aws ecs list-tasks --cluster <cluster-name> --region <region>

# Start an interactive shell
aws ecs execute-command \
  --cluster <cluster-name> \
  --task <task-id> \
  --container <container-name> \
  --interactive \
  --command "/bin/bash"
```

> **Note:** ECS Exec must be enabled on the service. The satcomp infrastructure enables this by default.

#### Option 2: VS Code Remote Attach

You can attach VS Code directly to a running ECS container for a full IDE debugging experience:

1. Install the [AWS Toolkit](https://marketplace.visualstudio.com/items?itemName=AmazonWebServices.aws-toolkit-vscode) and [Remote - Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extensions
2. Open the AWS Toolkit sidebar and navigate to **ECS** > your cluster > your running task
3. Right-click the container and select **Attach to Container**
4. VS Code opens a new window connected to the container — you get a terminal, file browser, and can set breakpoints in your solver code

This is especially useful for stepping through `solver_cmd.py` logic or inspecting the container filesystem while a solve is in progress.

### Check Container Logs

If your solver fails on AWS, check CloudWatch logs:
1. Go to AWS Console > CloudWatch > Log groups
2. Find `/ecs/{project}-{region}-{solver}`
3. Review recent log streams

### Test solver_cmd.py Logic

You can test your `get_run_command()` and `get_solver_result()` functions in Python:

```python
from pathlib import Path
from common.solver_io import SolverInput, SolverResultCode

# Test get_run_command
from solver_cmd import get_run_command
s_input = SolverInput(
    formula_file=Path("/tmp/test.cnf"),
    run_dir=Path("/tmp/run"),
    timeout_seconds=60,
    solver_options=[],
    node_ip="127.0.0.1",
    worker_node_ips=[]
)
print(get_run_command(s_input))

# Test get_solver_result
from solver_cmd import get_solver_result
result = get_solver_result(Path("/tmp/test_output.txt"))
print(result)
```

## Troubleshooting

See [Troubleshooting](05-troubleshooting.md) for common issues and solutions.

## Next Steps

After testing locally:

1. [Deploy to AWS](../running-on-AWS/01-deploying.md)
2. For distributed solvers, first see [Distributed Solvers](04-distributed-solvers.md)
