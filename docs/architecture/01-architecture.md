# Architecture

This page provides an overview of the system architecture and data flow.

## System Overview

The SAT/SMT Competition Infrastructure consists of several components that work together
to run solvers on AWS:

```
+------------------+     +------------------+     +------------------+
|   User's Machine |     |       AWS        |     |   Docker Image   |
|                  |     |                  |     |                  |
| satcomp.py CLI   |---->| CDK Stacks       |     | Solver Binary    |
| config.yml       |     | - VPC            |     | solver_cmd.py    |
| jobs.yml         |     | - ECS Clusters   |     | Harness Scripts  |
|                  |     | - SQS Queues     |     |                  |
+------------------+     | - S3 Bucket      |     +------------------+
                         | - DynamoDB       |
                         +------------------+
```

## Why Docker?

We use Docker for several reasons:

1. **Standardization** - Docker ensures consistent builds across different platforms
2. **Isolation** - Containers are isolated from host processes and other solvers
3. **Resource Control** - Easy to configure memory, CPU, and disk limits
4. **AWS Integration** - ECS provides mature container orchestration with logging,
   monitoring, and auto-scaling


## AWS Services Used

| Service | Purpose |
|---------|---------|
| **ECS** | Container orchestration - runs solver Docker containers |
| **EC2** | Compute instances - hosts for ECS tasks |
| **ECR** | Docker image registry - stores solver images |
| **S3** | Object storage - formulas and results |
| **SQS** | Message queues - job distribution and results collection |
| **DynamoDB** | NoSQL database - distributed solver coordination |
| **CloudWatch** | Logging and monitoring |
| **VPC** | Network isolation - private subnets for solvers |

## Data Flow

### Job Submission to Results

```
1. User runs `submit`
   |
   v
2. CLI reads jobs.yml, lists S3 paths
   |
   v
3. Job messages pushed to SQS input queues (one per solver)
   |
   v
4. Solver containers poll input queue
   |
   v
5. Container downloads formula from S3
   |
   v
6. Harness invokes solver via solver_cmd.py
   |
   v
7. Solver runs, outputs to stdout/stderr
   |
   v
8. Harness parses result, uploads logs to S3
   |
   v
9. Result message pushed to SQS output queue
   |
   v
10. User runs `collect` - collects results to local filesystem
```

### Distributed Solver Coordination

For distributed solvers, additional coordination happens via DynamoDB:

```
1. Leader and workers start, register IPs in DynamoDB
   |
   v
2. Leader claims N workers from DynamoDB table
   |
   v
3. Workers wait for commands (SSH daemon running)
   |
   v
4. Leader receives job, creates hostfile with worker IPs
   |
   v
5. Leader invokes solver (typically via MPI)
   |
   v
6. Solver distributes work to workers over SSH/MPI
   |
   v
7. On completion, leader broadcasts cleanup signal via DynamoDB
   |
   v
8. All nodes run cleanup command, return to ready state
```

## Component Details

### CLI (satcomp.py)

The main entrypoint orchestrates all operations:
- Parses config.yml and jobs.yml
- Invokes CDK for infrastructure management
- Manages Docker builds and pushes
- Interacts with AWS services for job management

### CDK Infrastructure (cdk_infra/)

AWS resource definitions using CDK:
- `app.py` - CDK app entrypoint
- `solver_constructs/` - Individual stack definitions
  - VPC stack - Network configuration
  - ECR stack - Container registry
  - S3 stack - Results bucket
  - Solver stack - Per-solver ECS/SQS/DynamoDB resources

### Harness (scripting/harness/)

Code that runs inside Docker containers:
- `entrypoints/` - Main scripts for leader/worker nodes
  - `leader_entrypoint.py` - Job processing loop for leaders
  - `worker_entrypoint.py` - Wait-and-cleanup loop for workers
  - `solver_cmd.py` - User-implemented solver interface
- `aws_shim/` - Wrappers for AWS services (S3, SQS, DynamoDB)

### Runner (scripting/runner/)

CLI implementation library:
- `runner_config.py` - Config file parsing
- `runner_docker.py` - Docker build and push operations
- `runner_jobs.py` - Job submission and result processing

## Resource Naming

All AWS resources follow a consistent naming pattern using `--` as a field separator.
This allows resources to be identified and grouped by project and solver.

See [Resource Naming](02-key-abstractions.md#resource-naming) for the full specification.

## Solver Types

### Parallel (Single-Node)

- `is_distributed: false` in config.yml
- One container per job
- Direct solver invocation via `get_run_command()`

### Distributed (Multi-Node)

- `is_distributed: true` in config.yml
- One leader + N workers per "copy"
- Leader coordinates via DynamoDB
- Workers run SSH daemon, wait for MPI/SSH commands
- Cleanup coordination after each job

## Further Reading

- [Key Abstractions](02-key-abstractions.md) - Important classes and patterns
- [Testing](03-testing.md) - Testing approach and conventions
