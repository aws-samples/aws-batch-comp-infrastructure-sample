# Troubleshooting (Solver Authors)

This page covers common issues when packaging and running solvers.

## Docker Build Issues

### Build Fails: Package Not Found

**Symptom:**
```
E: Unable to locate package <package-name>
```

**Solution:**
Add `apt-get update` before installing packages:
```dockerfile
RUN apt-get update && apt-get install -y <package-name>
```

### Build Fails: Permission Denied

**Symptom:**
```
COPY failed: permission denied
```

**Solution:**
Ensure files are owned by `ecs-user`:
```dockerfile
COPY --chown=ecs-user src /solver
```

### Build Fails: satcomp-infrastructure Not Found

**Symptom:**
```
ERROR: failed to solve: satcomp-infrastructure: pull access denied
```

**Solution:**
Build the base image first:
```bash
./satcomp.py build-base
```

### Build Fails: Out of Disk Space

**Symptom:**
```
no space left on device
```

**Solution:**
Clean up Docker resources:
```bash
docker system prune -a
docker volume prune
```

## test-local Issues

### All Tests Fail with Container Error

**Symptom:**
```
Container exited with error code 1
```

**Possible Causes:**
1. Solver binary not found or not executable
2. Missing shared libraries
3. Docker image not built correctly

**Solution:**
First verify the image builds correctly:
```bash
satcomp.py config.yml build
```

Then test manually:
```bash
docker run -it --rm your-solver-image /bin/bash
# Inside container, try running solver directly
```

### test-local Cannot Find expected.yml

**Symptom:**
```
Error: examples/formulas/expected.yml not found
```

**Solution:**
Ensure you're running the command from the repository root directory,
or that your config.yml is in the repository root.

### Wrong Results for Test Formulas

**Symptom:**
Tests fail with unexpected SAT/UNSAT results

**Possible Causes:**
1. `get_solver_result()` not parsing output correctly
2. Solver output format doesn't match expected patterns

**Solution:**
Check what your solver outputs and ensure `get_solver_result()` correctly
parses it. See the section below on "Results Show INDETERMINATE" for details.

## Runtime Issues

### Solver Crashes Immediately

**Possible Causes:**
1. Missing shared libraries
2. Wrong architecture (binary not built for linux/amd64)
3. Missing executable permissions

**Debug Steps:**
```bash
# Run a shell in your container
docker run -it --rm your-image /bin/bash

# Check the binary
file /path/to/solver
ldd /path/to/solver

# Try running manually
/path/to/solver --help
```

### Solver Times Out on Every Job

**Possible Causes:**
1. Timeout too short for problem difficulty
2. Solver not receiving timeout argument
3. Solver ignoring timeout

**Solution:**
Ensure your `get_run_command()` passes the timeout:
```python
def get_run_command(s_input: SolverInput) -> List[str]:
    return [
        "/solver/mysolver",
        str(s_input.formula_file),
        "-t", str(s_input.timeout_seconds)  # Pass timeout
    ]
```

### Results Show INDETERMINATE

**Possible Causes:**
1. `get_solver_result()` not parsing output correctly
2. Solver writing to stderr instead of stdout
3. Output format doesn't match expected patterns

**Solution:**
Check what your solver actually outputs:
```bash
# Run solver and capture output
docker run your-image /solver/mysolver /path/to/test.cnf > output.txt 2>&1
cat output.txt
```

Then update `get_solver_result()` to match the actual output format.

### Memory Errors (OOM Killed)

**Symptom:**
Task stops suddenly, CloudWatch shows "OutOfMemory"

**Solutions:**
1. Choose a larger EC2 instance type in config.yml
2. Reduce memory usage in your solver
3. Increase disk size for swap (temporary workaround)

```yaml
solvers:
  - name: mysolver
    ec2_instance_type: m6i.2xlarge    # More memory
    disk_size: 64                      # Larger disk
```

## AWS Credential Issues

### Unable to Locate Credentials

**Symptom:**
```
botocore.exceptions.NoCredentialsError: Unable to locate credentials
```

**Solution:**
Configure your AWS credentials:
```bash
aws configure
```

Or check that your credentials file exists at `~/.aws/credentials`:
```
[default]
aws_access_key_id=YOUR_KEY
aws_secret_access_key=YOUR_SECRET
region=us-east-1
```

### Access Denied

**Symptom:**
```
An error occurred (AccessDenied) when calling the <Operation> operation
```

**Solution:**
Your AWS account may not have sufficient permissions. If using IAM roles,
ensure your role has the necessary policies. For competition use, root
credentials are acceptable.

## Configuration Issues

### Invalid Project/Solver Name

**Symptom:**
```
Error: project name must not contain '--'
```

**Solution:**
Remove double hyphens from names in config.yml:
```yaml
# Wrong
project: my--project
# Correct
project: my-project
```

### Solver Not Found in Config

**Symptom:**
Commands don't affect your solver

**Solution:**
Check that your solver is correctly listed in config.yml and not commented out.
Verify the `name` field matches what you expect.

## Deployment Issues

### CDK Bootstrap Failed

**Symptom:**
```
Error: This stack uses assets, so the toolkit stack must be deployed
```

**Solution:**
Run bootstrap first:
```bash
./satcomp.py bootstrap
```

### Deploy Takes Too Long

**Note:**
Deployment can take 3-5 minutes per solver. This is normal. If it hangs
indefinitely, check:
1. AWS Console for CloudFormation errors
2. Your internet connection
3. AWS service status

## Getting More Help

If these solutions don't resolve your issue:

1. Check CloudWatch logs for detailed error messages
2. Review the ECS task status in AWS Console
3. Contact the competition organizers:
   - SAT: [sat-comp@amazon.com](mailto:sat-comp@amazon.com)
   - SMT: [aws-smtcomp-2024@googlegroups.com](mailto:aws-smtcomp-2024@googlegroups.com)
