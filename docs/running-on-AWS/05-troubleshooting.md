# Troubleshooting (Organizers)

This page covers common issues when running competitions.

## Credential Errors

### Unable to Locate Credentials

**Symptom:**
```
botocore.exceptions.NoCredentialsError: Unable to locate credentials
```

**Solution:**
```bash
aws configure
```

Or verify `~/.aws/credentials` exists and contains valid keys.

### Access Denied

**Symptom:**
```
An error occurred (AccessDenied) when calling the <Operation> operation
```

**Solution:**
Your credentials lack required permissions. For competition use, root credentials
are acceptable. Otherwise, ensure your IAM role has appropriate policies.

## Deployment Issues

### Bootstrap Required

**Symptom:**
```
Error: This stack uses assets, so the toolkit stack must be deployed
```

**Solution:**
```bash
./satcomp.py bootstrap
```

### Deployment Timeout

**Symptom:** `provision` hangs for more than 30 minutes.

**Causes:**
- CloudFormation stack creation stuck
- AWS service issues

**Solution:**
1. Check CloudFormation in AWS Console for specific errors
2. Check [AWS Status](https://status.aws.amazon.com/)
3. If stack is stuck, tear down and re-provision:
   ```bash
   ./satcomp.py teardown all
   ./satcomp.py provision
   ```

### Stack in Failed State

**Symptom:** CloudFormation shows `ROLLBACK_COMPLETE` or `UPDATE_ROLLBACK_COMPLETE`

**Solution:**
```bash
./satcomp.py teardown all
./satcomp.py provision
```

## Instance Launch Issues

### Instances Not Starting

**Symptom:** `ls ecs` shows 0 instances after `start-instances`

**Causes:**
1. Problem in docker container
1. EC2 quota exceeded
1. Instance type unavailable in region
1. Auto-scaling not triggered yet (wait up to 15 minutes)

**Check EC2 Quota:**
Go to AWS Console > Service Quotas > EC2 > Running On-Demand instances

**Change Instance Type:**
Update `ec2_instance_type` in config.yml and redeploy:
```bash
./satcomp.py provision solvers
```

### Tasks Pending Forever

**Symptom:** Tasks stuck in PENDING state in ECS

**Causes:**
1. No EC2 capacity available
2. Task definition incompatible with instances

**Solution:**
1. Check ECS Console for task stopped reason
2. Check Auto Scaling Group activity in EC2 Console
3. Try `standby-instances` to warm up instances first

## Job Submission Issues

### Submit Does Nothing

**Symptom:** `submit` completes but no jobs appear in queue

**Causes:**
1. No matching files in S3 paths
2. Wrong `solver_type` (e.g., `.cnf` files with `solver_type: smt`)
3. S3 path doesn't exist

**Debug:**
```bash
# Check if files exist
aws s3 ls s3://your-bucket/your-path/ --recursive | head
```

### Jobs Not Processing

**Symptom:** Jobs in queue but not being processed

**Causes:**
1. Solvers not running (`ls ecs` shows 0 tasks)
2. Solvers crashed on startup
3. Queue permissions issue

**Debug:**
1. Check `./satcomp.py ls ecs` for running tasks
2. Check CloudWatch logs for solver errors
3. Manually test solver container

## Solver Failures

### All Jobs Return ERROR

**Symptom:** Every job fails with ERROR result

**Likely Causes:**
1. Solver binary not found or not executable
2. `solver_cmd.py` has bugs
3. Base image incompatibility

**Debug:**
1. Check CloudWatch logs for error messages
2. Download S3 logs (stderr.txt) from a failed job
3. Test Docker container locally:
   ```bash
   docker run -it your-image /bin/bash
   /path/to/solver --help
   ```
4. Attach to a running ECS container for interactive debugging:

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

   > **Note:** This requires the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html). ECS Exec is enabled by default on satcomp services.

### High Timeout Rate

**Symptom:** Most jobs timeout

**Causes:**
1. Timeout too short for problem difficulty
2. Solver not respecting timeout
3. Solver stuck (infinite loop, deadlock)

**Solutions:**
1. Increase `timeout_secs` in jobs.yml
2. Verify solver receives timeout argument
3. Check solver with easy problems first

### Memory Errors

**Symptom:** Tasks stop suddenly, "OutOfMemory" in logs

**Solutions:**
1. Use larger EC2 instance:
   ```yaml
   ec2_instance_type: m6i.2xlarge
   ```
2. Increase disk for swap:
   ```yaml
   disk_size: 64
   ```
3. Redeploy after changes:
   ```bash
   ./satcomp.py provision solvers
   ```

## Results Issues

### Process Returns Empty Results

**Symptom:** `collect` completes but results.csv is empty

**Causes:**
1. No messages in output queue
2. Jobs still running
3. Results already processed

**Check:**
```bash
./satcomp.py ls sqs    # Check output queue depth
```

### Missing Results for Some Jobs

**Symptom:** Some jobs don't appear in results

**Causes:**
1. Jobs still in progress
2. Solver crashed before writing result
3. S3 upload failed

**Debug:**
1. Wait for completion (check `ls sqs`)
2. Check CloudWatch logs for crashed tasks
3. Check S3 bucket directly for partial results

## Cleanup Issues

### Destroy Fails

**Symptom:** `teardown all` fails with resource errors

**Common Causes:**

**ENIs Not Deleting:**
Wait 10-15 minutes and retry. Lambda ENIs can take time to clean up.

**S3 Bucket Not Empty:**
```bash
aws s3 rm s3://{bucket}/ --recursive
./satcomp.py teardown all
```

**ECR Not Empty:**
```bash
aws ecr delete-repository --repository-name {repo} --force
./satcomp.py teardown all
```

**Stack Dependencies:**
Destroy in order:
```bash
./satcomp.py teardown solvers
./satcomp.py teardown vpc
```

### Resources Remain After Destroy

**Solution:**
Go to AWS Console and manually delete:
1. CloudFormation > Delete remaining stacks
2. ECS > Delete clusters
3. EC2 > Terminate instances
4. EC2 > Delete Network Interfaces (wait for ENIs to be deletable)

## Getting More Help

If these solutions don't resolve your issue:

1. Collect relevant information:
   - `./satcomp.py ls ecs` output
   - `./satcomp.py ls sqs` output
   - CloudWatch log excerpts
   - CloudFormation event details

2. Contact us at: [solver-competitions@amazon.com](mailto:solver-competitions@amazon.com)
