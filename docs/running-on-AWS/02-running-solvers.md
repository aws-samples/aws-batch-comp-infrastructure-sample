# Running Solvers on AWS

This page covers pushing solver images to AWS, starting instances, and submitting jobs.

## Building and Pushing Images

After provisioning infrastructure, build and push Docker images for all solvers in your config:

```bash
./satcomp.py build push
```

As before, `build` builds the base `satcomp-infrastructure` image and each solver's Docker image. The `push` command copies all solver images to ECR.

### Rebuilding After Changes

If you modify a solver's Dockerfile or `solver_cmd.py`, rebuild and push:

```bash
./satcomp.py build push
```

Docker caches build steps, so subsequent builds are faster.

If your Dockerfile fetches from external sources (e.g., `git clone`, `apt-get install`)
and the upstream content has changed but the Dockerfile hasn't, use `--no-cache` to
force a full rebuild:

```bash
./satcomp.py build --no-cache push
```

### Verifying Images

Check that images were pushed:

```bash
docker images    # list local images
aws ecr describe-images --repository-name ${project}-${region}-ecr    # list ECR images
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
1. Uses auto-scaling to create EC2 instances as needed
1. ECS deploys solver containers to the EC2 instances

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

### Using `standby-instances` for faster iteration

If you're iterating on solver builds, use `standby-instances` to keep EC2 instances ready. `standby-instances` creates EC2 instances but doesn't run solver containers, so you can
swap in new images without waiting for instance launch.

```bash
./satcomp.py standby-instances 5    # Warm up 5 instances per solver
# ... make local changes, rebuild, test ...
./satcomp.py build push
./satcomp.py start-instances 5      # Starts new solver images quickly on warm instances
```

**Note:** Running `standby-instances` after `start-instances` will stop running tasks, but keep the compute instances alive (and keeps charging your account for the underlying instances)

### Refreshing running tasks with new images

If you've already started instances and push new images, use `refresh-instances`
to cycle tasks without losing your warm EC2 instances:

```bash
./satcomp.py build push
./satcomp.py refresh-instances    # Standby, wait for drain, then restart
```

This reads the current desired count from ECS, puts solvers in standby, waits for
all running tasks to fully drain, then restarts with the same count using fresh images.

**Note:** If you run `start-instances` when tasks are already running with outdated images, it will detect the mismatch and offer to refresh for you. You can use `refresh-instances` directly if you already know your images have changed, or simply use `start-instances` and let it prompt you.

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
- `sat`: `.cnf` files (including compressed: `.cnf.gz`, `.cnf.bz2`, `.cnf.xz`)
- `smt`: `.smt2` files (including compressed: `.smt2.gz`, `.smt2.bz2`, `.smt2.xz`)

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

## Terminate solver instances

Terminate (delete) all solver instances:

```bash
./satcomp.py terminate-instances
```

This:
1. Sets ECS service desired count to 0
2. Stops all running tasks
3. Terminates EC2 instances

**Note:** `terminate-instances` terminates ALL solvers in your configuration yml file.
To terminate only specific solvers, comment out others in config.yml first.

### Verify zero running Tasks

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

# 8. When complete (input queue empty), collect results and terminate instances
./satcomp.py collect
./satcomp.py terminate-instances

# 9. Clean up
./satcomp.py teardown all
```

## Running Multiple Batches

To run different formula sets or configurations:

```bash
# Batch 1: Easy formulas
# Edit jobs.yml with easy formulas
./satcomp.py submit
# Wait for completion, then collect results
./satcomp.py collect

# Batch 2: Hard formulas
# Edit jobs.yml or use a different jobs.yml with hard formulas
./satcomp.py submit
# Wait for completion, collect results, then terminate the containers
./satcomp.py collect terminate-instances
```

Results accumulate in `<results_dir>/results.txt` specified in jobs.yml.

## Next Steps

- [Process and analyze results](03-processing-results.md)
- [Troubleshooting](05-troubleshooting.md) for common issues
