# Running Your Solver on AWS

Now that your solver is [built and passing local tests](/docs/solver-preparation/README.md), you're ready to deploy on AWS. 
This section offers a step-by-step guide to deploying, running, results processing, and resource teardown. 
We also include sections on troubleshooting and a quick reference guide.

1. [Deploying Infrastructure](01-deploying.md) - Deploy and bootstrap
1. [Running Solvers](02-running-solvers.md) - Build, start, submit
1. [Processing Results](03-processing-results.md) - Collect and analyze
1. [Teardown](04-teardown.md) - Clean up resources
1. [Troubleshooting](05-troubleshooting.md) - Common issues and solutions
1. [Quick Reference and Common Workflows](06-reference-and-workflows.md) - Guide to commands and common worklows.

## AWS Costs

| Resource | Cost | Notes |
|----------|------|-------|
| ECS Instances | varies | required to run solvers, mostly costly resource |
| VPC Endpoints | ~$3/day | created by `provision`, persists until `teardown` |
| S3 Storage | ~$0.023/GB/month | stores results and formulas |
| SQS Queues | minimal | per-message costs |

**Important:** Ensure that you terminate ECS instances when not using them.
Costs will acrue regardless of whether or not solvers are actively running.
Run `teardown all` when not actively using the infrastructure to avoid VPC endpoint charges.

## Need Help?

Contact us at: [solver-competitions@amazon.com](mailto:solver-competitions@amazon.com)
