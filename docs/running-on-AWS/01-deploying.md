# Deploying Infrastructure

This page explains how to bootstrap CDK and provision AWS infrastructure to run solvers on the cloud.

## Prerequisites

Before deploying, ensure you have:

1. Installed all software dependencies (see [Software Dependencies](../getting-started/01-software-dependencies.md))
2. Configured AWS credentials (see [AWS Setup](../getting-started/02-aws-setup.md))
3. Registered your solver(s) in `config.yml`

## Bootstrapping CDK (One-Time)

The AWS CDK requires a one-time bootstrap to set up resources for deployment. This
creates an S3 bucket and IAM roles that CDK uses to manage your stacks.

```bash
source satcomp-activate.sh
./satcomp.py bootstrap
```

You only need to bootstrap once per AWS account/region combination. If you change
regions, you'll need to bootstrap again for the new region.

### Using Non-Default Profiles or Regions

If you're using a non-default AWS profile or region, update `config.yml` first:

```yaml
profile: satcomp      # Your AWS profile name
region: us-west-2     # Your desired region
```

Then run bootstrap:
```bash
./satcomp.py bootstrap
```

## Deploying

Once bootstrapped, provision the infrastructure:

```bash
./satcomp.py provision
```

This typically takes 3-5 minutes per solver in your config.yml.

### What Gets Created

The `provision` command creates several AWS resources:

**Shared Resources (one per project):**
- VPC with private subnets and NAT gateway
- VPC endpoints for AWS services (S3, SQS, DynamoDB, ECR)
- S3 bucket for solver results
- ECR repository for Docker images

**Per-Solver Resources:**
- ECS cluster and service
- Auto-scaling group for EC2 instances
- SQS queues (input and output)
- CloudWatch log groups
- DynamoDB tables (for distributed solvers)
- IAM roles and security groups

### Costs While Deployed

The VPC endpoints cost approximately $3/day even when no solvers are running.
Run `./satcomp.py teardown all` when you're done to remove these endpoints.

## Re-Deploying

If you change `config.yml` (e.g., add a solver, change instance types), you must
re-provision:

```bash
./satcomp.py provision
```

### Faster Re-Provision (Solvers Only)

If you've only changed solver configurations (not project settings), you can
provision just the solver stacks:

```bash
./satcomp.py provision solvers
```

This is faster because it skips the VPC and shared resources.

## Verifying Deployment

After deployment, verify resources were created:

```bash
# Check ECS clusters
./satcomp.py ls ecs

# Check SQS queues
./satcomp.py ls sqs
```

You can also verify in the AWS Console:
- CloudFormation: Shows all stacks created
- ECS: Shows clusters (should have 0 running tasks initially)
- SQS: Shows input/output queues for each solver

## Using Multiple Configuration Files

You can maintain separate config files for different sets or solver configurations:

```bash
./satcomp.py parallel.yml provision
./satcomp.py distributed.yml provision
```

Each config file's solvers will be deployed independently.

(TODO: confirm multiple config YAML per project still functions correctly)

## Troubleshooting

### Bootstrap Fails

**Symptom:**
```
Error: This stack uses assets, so the toolkit stack must be deployed
```

**Solution:** Ensure you ran `./satcomp.py bootstrap` first.

### Deploy Fails with Permission Error

**Symptom:**
```
User: arn:aws:iam::... is not authorized to perform: ...
```

**Solution:** You don't have AWS credentials, their not active, or they don't have sufficient permissions. Use root credentials or ensure your IAM role has admin access.

### Deploy Hangs or Times Out

**Cause:**
- CloudFormation stack in inconsistent state

**Solution:**
1. Check CloudFormation in AWS Console for specific errors
2. Try `./satcomp.py teardown all` and re-provision

### Stacks Show UPDATE_ROLLBACK_COMPLETE

**Symptom:** CloudFormation stacks are in a failed state.

**Solution:**
```bash
./satcomp.py teardown all
./satcomp.py provision
```

## Next Steps

After deployment, it's time to [Run your solver](02-running-solvers.md)
