# Running Your Solver on AWS

This guide shows you how to provision, build, run, monitor, process, and tear down your packaged solver on AWS.

## Overview

Running your solver on AWS involves:

2. **Provision** - Provision infrastructure (VPC, ECR, ECS clusters, queues)
3. **Build** - Build and push solver Docker images
4. **Run** - Start solvers and submit formula jobs
5. **Monitor** - Track progress and handle failures
6. **Process** - Collect and analyze results
7. **Teardown** - Tear down resources to avoid ongoing costs

## AWS Cost Overview

| Resource | Cost | Notes |
|----------|------|-------|
| VPC Endpoints | ~$3/day | Created by `provision`, persists until `teardown` |
| EC2 Instances | Varies | Only while solvers are running |
| S3 Storage | ~$0.023/GB/month | Results and formulas |
| SQS Queues | Minimal | Per-message costs |

**Important:** Run `teardown all` when not actively using the infrastructure to
avoid VPC endpoint charges.

## Prerequisites


- [ ] Setup software dependences
- [ ] Setup AWS account and credentials
- [ ] Prepare, package, and perform local testing on your solver and configuration

## Guide Contents

1. [Deploying Infrastructure](01-deploying.md) - Deploy and bootstrap
1. [Running the Competition](02-running-competition.md) - Build, start, submit
1. [Processing Results](03-processing-results.md) - Collect and analyze
1. [Teardown](04-teardown.md) - Clean up resources
1. [Troubleshooting](05-troubleshooting.md) - Common issues and solutions

## Quick Reference

```bash
# One-time setup
./satcomp.py bootstrap

# Provision infrastructure (~5 min per solver)
./satcomp.py provision

# Build and push all solver images
./satcomp.py build push

# Start 5 copies of each solver
./satcomp.py start-instances 5

# Submit jobs from jobs.yml
./satcomp.py submit

# Monitor progress
./satcomp.py ls ecs    # monitor instance status
./satcomp.py ls sqs    # monitor queue depths

# collect results
./satcomp.py collect

# Terminate solver instances 
./satcomp.py terminate-instances

# Full teardown
./satcomp.py teardown all
```

## Common Workflows

### Running a Complete Batch

```bash
source satcomp-activate.sh
./satcomp.py provision
./satcomp.py build push
./satcomp.py start-instances 10
./satcomp.py submit
# ... wait for completion ...
./satcomp.py collect terminate-instances
./satcomp.py teardown all
```

### Iterating on Solver Images

```bash
# Keep EC2 instances warm while rebuilding
./satcomp.py standby-instances 5
./satcomp.py build push
./satcomp.py start-instances 5
./satcomp.py submit
./satcomp.py terminate-instances process
# Repeat as needed
```

### Running Multiple Solver Configurations

```bash
./satcomp.py parallel_solvers.yml provision build push
./satcomp.py distributed_solvers.yml provision build push
```

## Need Help?

- SAT Competition: [sat-comp@amazon.com](mailto:sat-comp@amazon.com)
- SMT Competition: [aws-smtcomp-2024@googlegroups.com](mailto:aws-smtcomp-2024@googlegroups.com)
