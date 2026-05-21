# Teardown

You should use `terminate-instances` to delete your solver tasks when you are done running tests.

This page explains how to teardown (delete) the rest of the AWS resources associated with the competition package.

## Why Teardown Matters

Even when no solvers are running, some resources incur ongoing costs:
- **VPC Endpoints:** ~$3/day
- **NAT Gateway:** ~$1/day
- **S3 Storage:** ~$0.023/GB/month

Always tear down resources when you're done to avoid unexpected charges.

## Full Teardown

To tear down all resources created by this project:

```bash
./satcomp.py teardown all
```

This removes:
- All solver ECS clusters, services, and task definitions
- SQS queues
- DynamoDB tables
- VPC, subnets, and endpoints
- S3 bucket (only if empty)
- ECR repository (only if empty)
- CloudWatch log groups
- All associated IAM roles and security groups

**Note:** `teardown all` will fail if S3 bucket or ECR repository contains data.
Empty them first or use the [AWS Console](https://docs.aws.amazon.com/awsconsolehelpdocs/latest/gsg/what-is.html) to force delete.

## Partial Teardown

For more control, you can tear down specific resource groups:

```bash
./satcomp.py teardown help    # Show available options
```

### Destroy Only Solvers

Keep the VPC and shared resources, tear down only solver-specific resources:

```bash
./satcomp.py teardown solvers
```

This is useful if you want to redeploy different solvers without recreating the VPC.

### Destroy VPC

Tear down only the VPC (and its endpoints):

```bash
./satcomp.py teardown vpc
```

**Note:** You must tear down solvers first, as they depend on the VPC.

## Before Destroying

### Stop Running Solvers

Ensure all solvers are stopped:

```bash
./satcomp.py terminate-instances
./satcomp.py ls ecs    # Verify 0 running tasks
```

### Process Remaining Results

Collect any unprocessed results:

```bash
./satcomp.py collect
```

### Download Important Data

Results in S3 are deleted when the bucket deleted. Download anything you need:

```bash
aws s3 sync s3://{bucket}/ ./backup/
```

### Verify Queue Status

Check that queues are empty:

```bash
./satcomp.py ls sqs
```

If needed, purge remaining messages:

```bash
./satcomp.py purge
```

## Verifying Cleanup

After teardown, verify in AWS Console:

1. **CloudFormation:** No stacks with your project name
2. **ECS:** No clusters for your project
3. **EC2:** No running instances (give it a few minutes)
4. **SQS:** No queues for your project

## Handling Destroy Failures

### Destroy Hangs

If teardown hangs, CloudFormation may be stuck:

1. Go to AWS Console > CloudFormation
2. Find the stuck stack
3. Check "Events" tab for the blocking resource
4. Manually delete the blocking resource
5. Retry teardown

### Resources Not Deleted

Some resources may require manual cleanup:

**S3 Bucket Not Empty:**
```bash
aws s3 rm s3://{bucket}/ --recursive
```

**ECR Repository Not Empty:**
```bash
aws ecr delete-repository --repository-name {repo} --force
```

**ENIs Stuck:**
Sometimes network interfaces don't delete automatically. Wait 10-15 minutes,
or manually delete from EC2 Console > Network Interfaces.

### Stack in DELETE_FAILED State

1. Go to CloudFormation > Stack > Delete
2. Select "Delete stack" and choose to retain problematic resources
3. Manually delete retained resources from AWS Console

## Cost Verification

After teardown, verify no costs are accruing:

1. Go to AWS Console > Billing
2. Check "Cost Explorer" for any active resources
3. Set up billing alerts for unexpected charges

## Rebuilding After Teardown

To use the project again after full teardown:

```bash
./satcomp.py bootstrap    # May be needed if you destroyed CDK resources
./satcomp.py provision    # Provision fresh infrastructure
```

## Next Steps

- [Troubleshooting](05-troubleshooting.md) if you encounter issues
- Return to [Running Solvers](02-running-solvers.md) for a new run
