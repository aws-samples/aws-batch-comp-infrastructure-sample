# Quick Reference and Common Workflows

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

### Start to Finish

```bash
# configure current shell session
source satcomp-activate.sh
# setup AWS infrastructure
./satcomp.py provision
# build solver(s), push to AWS
./satcomp.py build push
# start compute instances, 10 in this case
./satcomp.py start-instances 10
# submit jobs
./satcomp.py submit
# wait for completion, check progress:
./satcomp.py ls sqs    # monitor queue depths
# copy results to local file
./satcomp.py collect 
# terminate (delete) ECS instances
./satcomp.py terminate-instances
# when finished with the competition, delete all AWS resources
./satcomp.py teardown all
```

### Iterating/Debugging Solver Images in AWS

After provisioning:

```bash
# Keep EC2 instances warm while rebuilding
./satcomp.py standby-instances 5

# rinse and repeat as needed
./satcomp.py build push
./satcomp.py start-instances 5
./satcomp.py submit
# wait for completion
./satcomp.py collect 
```

Don't forget to `terminate-instances` when finished debugging,
and `teardown all` when finished with the competition.

### Running Multiple Solvers in Parallel

If you want to test multiple solver configurations at the same time, you simply change the configuration yml files.
In fact, this is how we run the competitions--we use the same setup you do.

You can see a config for multiple SAT parallel solvers in [examples/configs/sat-parallel/config.yml](../../examples/configs/sat-parallel/config.yml).
You might rename this as `sat-parallel-solvers.yml` or something similar.