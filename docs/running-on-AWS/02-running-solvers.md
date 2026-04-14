# Running the Competition

This page covers building solver images, starting instances, and submitting jobs.

## Building and Pushing Images

After provisioning infrastructure, build Docker images for all solvers in your config:

```bash
./satcomp.py build push
```

`build` builds the base `satcomp-infrastructure` image and each solver's Docker image. `push` pushes all solver images to ECR.

### Rebuilding After Changes

If you modify a solver's Dockerfile or `solver_cmd.py`, rebuild and push:

```bash
./satcomp.py build push
```

Docker caches build steps, so subsequent builds are faster.

### Verifying Images

Check that images were pushed:

```bash
docker images    # Local images
aws ecr describe-images --repository-name ${project}-${region}-ecr    # ECR images
```

## Start Solvers Instances

Start solver containers with the `start-instances` command:

```bash
./satcomp.py start-instances [n]
```

Where `n` is the number of copies per solver (default: 1).

### How `start-instances` Works

The command:
1. Adjusts ECS service desired count to `n`
2. Auto-scaling creates EC2 instances as needed
3. ECS deploys solver containers to the EC2 instances

**Important:** `n` applies to each solver in your config. If you have 3 solvers
and run `start 5`, you'll start 15 instances total (5 per solver).

### Startup Time

It can take **up to 15 minutes** for solvers to become available. This is due to:
- EC2 instance launch time (3-5 minutes)
- ECS auto-scaling poll interval (up to 10 minutes)
- Docker image download

Use `ls ecs` to monitor progress:
```bash
./satcomp.py ls ecs
```

You can also look at ECS updates in the AWS console.

### Using `standby-instances` for Faster Iteration

If you're iterating on solver builds, use `standby-instances` to keep EC2 instances ready:

```bash
./satcomp.py standby-instances 5    # Warm up 5 instances per solver
# ... make changes, rebuild ...
./satcomp.py build push
./satcomp.py start-instances 5      # Starts quickly on warm instances
```

`standby-instances` creates EC2 instances but doesn't run solver containers, so you can
swap in new images without waiting for instance launch.

**Note:** Running `standby-instances` after `start-instances` will stop running tasks, but keep instances alive (and charging your account for the underlying instances)

## Submitting Jobs

### Preparing jobs.yml

Configure jobs in `jobs.yml`:

```yaml
results_dir: results

formulas:
  - s3://your-bucket/benchmarks/easy
  - s3://your-bucket/benchmarks/medium

job_options:
  timeout_secs: 1000
  solver_options: []
```

**Important:** Formula paths must be S3 URIs. Upload local files to S3 first:
```bash
aws s3 sync ./local_benchmarks s3://your-bucket/benchmarks
```

### Submitting

```bash
./satcomp.py submit
```

This submits jobs to queus for **all solvers** in your config. If you have 100 formulas
and 5 solvers, 500 total jobs are submitted (100 per solver).

### Filtering by File Extension

The `solver_type` in config.yml determines which files are submitted:
- `sat`: Only `.cnf` files
- `smt`: Only `.smt2` files

### Limiting Job Count

To submit only a subset of formulas, use the `limit` field:

```yaml
limit: 10    # Submit at most 10 jobs per solver
```

## Monitoring Progress

### Queue Status

```bash
./satcomp.py ls sqs
```

Shows:
- Messages in input queues (pending jobs)
- Messages in output queues (completed results)
- Messages in flight (currently processing)

When input queue reaches 0, all jobs have been read.

### Instance Status

```bash
./satcomp.py ls ecs
```

Shows:
- Running tasks per solver
- Pending tasks
- Container instance count

### CloudWatch Logs

View detailed logs in AWS Console:
1. Go to CloudWatch > Log groups
2. Find `/ecs/{project}-{region}-{solver}`
3. Select recent log streams

## Stopping Solvers

Terminate all running solvers:

```bash
./satcomp.py terminate-instances
```

This:
1. Sets ECS service desired count to 0
2. Stops all running tasks
3. Terminates EC2 instances

**Note:** `terminate-instances` terminates ALL solvers in your config. To terminate only specific solvers,
comment out others in config.yml first.

### Verify Stopped

```bash
./satcomp.py ls ecs    # Should show 0 running tasks
```

## Purging Queues

If you need to cancel pending jobs, empty input queues with:

```bash
./satcomp.py purge
```

This removes all messages from input queues. Already-running jobs will complete,
and results in output queues are preserved.

**Note:** Purging can take up to 60 seconds. You can't purge twice within a minute.

## Batch Workflow Example

A typical competition run:

```bash
# 1. Activate environment
source satcomp-activate.sh

# 2. Provision infrastructure (if not already)
./satcomp.py provision

# 3. Build and push solver images
./satcomp.py build push

# 4. Start solver instances
./satcomp.py start-instances 10    # 10 copies per solver

# 5. Wait for instances to be ready (~15 min)
./satcomp.py ls ecs

# 6. Submit jobs
./satcomp.py submit

# 7. Monitor progress
./satcomp.py ls sqs

# 8. When complete (input queue empty), terminate and collect
./satcomp.py terminate-instances process

# 9. Clean up
./satcomp.py teardown all
```

## Running Multiple Batches

To run different formula sets or configurations:

```bash
# Batch 1: Easy formulas
# Edit jobs.yml with easy formulas
./satcomp.py submit
# Wait for completion
./satcomp.py collect

# Batch 2: Hard formulas
# Edit jobs.yml or use a different jobs.yml with hard formulas
./satcomp.py submit
# Wait for completion, then terminate the containers
./satcomp.py terminate-instances process
```

Results accumulate in `<results_dir>/results.txt` specified in jobs.yml.

## Next Steps

- [Process and analyze results](04-processing-results.md)
- [Troubleshooting](06-troubleshooting.md) for common issues
