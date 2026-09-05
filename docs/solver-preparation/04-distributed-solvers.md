# Distributed Solvers

This page explains how to configure and run distributed (multi-node) solvers.

## Overview

Distributed solvers run across multiple EC2 instances, with one **leader node** and
multiple **worker nodes**. The leader coordinates work and invokes solvers on workers
via SSH or MPI.

Use distributed mode when your solver can benefit from:
- More total memory than a single instance provides
- Parallel work distribution across machines
- MPI-based communication patterns

## Architecture

```
+---------------+      SSH/MPI      +---------------+
|  Leader Node  | <---------------> |  Worker Node  |
|               |                   |  (1 of N)     |
| - Receives    |                   |               |
|   jobs from   |                   | - SSH daemon  |
|   queue       |                   |   running     |
| - Invokes     |                   | - Waits for   |
|   solver      |                   |   commands    |
| - Coordinates |                   | - Runs solver |
|   workers     |                   |   processes   |
+---------------+                   +---------------+
        |
        v
  DynamoDB Tables
  (coordination)
```

### How It Works

1. When you `start-instances` distributed solvers, AWS creates one leader task and N worker tasks
2. Each task registers its IP address in a DynamoDB table
3. Workers start an SSH daemon and wait for commands
4. The leader claims workers from the DynamoDB table
5. Leader receives a job from the input queue
6. Leader invokes the solver, passing worker IPs via `solver_cmd.py`
7. Your solver uses SSH/MPI to distribute work to workers
8. After completion, the leader broadcasts a cleanup signal
9. All nodes run the cleanup command, then return to ready state

### Heartbeat and Health Monitoring

All nodes send heartbeats to a DynamoDB timestamp table. If a node stops sending
heartbeats, it's considered dead and cleaned up automatically. This handles:
- Worker crashes during solving
- Leader crashes (workers get reassigned)
- Network partitions

## Configuration

Enable distributed mode in your `config.yml`:

```yaml
solvers:
  - name: mysolver
    docker_dir: ./docker/
    dockerfile: mysolver/Dockerfile
    is_distributed: true
    num_worker_nodes_per_leader: 7    # Creates 8 total nodes per "copy"
    ec2_instance_type: m6i.4xlarge
```

**Important:** When you run `start-instances 2` with a distributed solver, you get:
- 2 leader tasks
- 14 worker tasks (7 workers per leader)
- 16 total EC2 instances

## Dockerfile Requirements

Your Dockerfile must work for both leader and worker nodes (they use the same image).
Ensure any software needed on workers is installed.

Since workers communicate via SSH, your solver must be able to:
- Accept a list of worker IP addresses
- Use SSH or MPI to run commands on workers

### Example: MPI Setup

Most distributed SAT solvers use MPI. The base image includes Open MPI. Your
`get_run_command()` might look like:

```python
def get_run_command(s_input: SolverInput) -> List[str]:
    # Create a hostfile with all node IPs
    all_ips = [s_input.node_ip] + s_input.worker_node_ips
    hostfile_path = s_input.run_dir / "hostfile.txt"
    with open(hostfile_path, 'w') as f:
        for ip in all_ips:
            f.write(f'{ip} slots=1\n')

    return [
        "mpirun",
        "--hostfile", str(hostfile_path),
        "--allow-run-as-root",
        "/solver/build/mysolver",
        str(s_input.formula_file)
    ]
```

## Implementing solver_cmd.py

For distributed solvers, you must implement all three functions:

### get_run_command()

Receives `SolverInput` with:
- `node_ip` - This node's IP address
- `worker_node_ips` - List of worker IP addresses
- Other standard fields (formula_file, timeout_seconds, etc.)

Use these IPs to build a hostfile or pass to your solver.

### get_solver_result()

Same as parallel solvers - parse stdout to determine SAT/UNSAT/UNKNOWN.

### get_cleanup_command()

**Required for distributed solvers.** This command runs on ALL nodes after each job.
Use it to:
- Kill any lingering solver processes
- Clean up temporary files
- Reset state for the next job

```python
def get_cleanup_command() -> List[str]:
    return ["pkill", "-f", "mysolver"]
```

The cleanup command has a timeout (default 30 seconds). After cleanup, nodes return
to ready state for the next job. If your solver workers do not cleanup properly, subsequent jobs may be affected. 

## Example: mallob

The Mallob distributed solver in `examples/configs/sat-distributed` is a complete example that invokes the 2024 Mallob parallel solver in distributed mode:

**Configuration:**
```yaml
solvers:
  - name: mallob
    docker_dir: $SATCOMP_ROOT/examples/solvers/sat/distributed/mallob
    dockerfile: Dockerfile
    is_distributed: true
    num_worker_nodes_per_leader: 7
    ec2_instance_type: m6i.4xlarge
```

**solver_cmd.py:**
```python
def get_run_command(s_input: SolverInput) -> List[str]:
    # Create hostfile
    all_ips = [s_input.node_ip] + s_input.worker_node_ips
    hostfile_path = s_input.run_dir / "combined_hostfile.txt"
    with open(hostfile_path, 'w+') as f:
        for ip in all_ips:
            f.write(f'{ip} slots=1\n')

    return ["/run_solver.sh", str(hostfile_path), str(s_input.formula_file)]
```

Note that this example copies `run_solver.sh` from the local directory. With the 2026 infrastructure, this shoul be part of the repository. `run_solver.sh` is a shell script that:
1. Reads the hostfile
2. Configures MPI options
3. Runs `mpirun` with appropriate settings

## Troubleshooting Distributed Solvers

### Local Distributed Testing

You can test distributed solvers locally using Docker containers connected via a bridge network. This avoids AWS costs and enables fast iteration.

```bash
# Test with 2 worker containers + 1 leader
./satcomp.py examples/configs/sat-distributed-mallob/config.yml --test-local mallob --num-workers 2
```

This creates:
- A Docker bridge network for container communication
- 2 worker containers that register in a shared DynamoDB shim (file-based)
- 1 leader container that claims workers, downloads formulas, and runs the solver
- MPI/SSH communication between containers using shared SSH keys from the base image

**Prerequisites:**
- Build images first: `./satcomp.py <config.yml> --build`
- Docker must be running

**How it works:**
1. A shared temp directory is mounted at `/shared` in all containers, providing file-based DynamoDB coordination
2. Workers register their IPs, leader claims them and builds a hostfile
3. Leader runs `get_run_command()` which invokes `mpirun` with the hostfile
4. MPI connects to workers via SSH (keys are shared across all containers from the same image)
5. Results are collected from leader container logs

**Expected behavior for mallob:**
- SAT/UNSAT formulas: should return correct results
- Timeout formulas: mallob with multiple MPI processes may solve these faster than expected, returning INDETERMINATE instead of TIMEOUT. This happens because mallob exits with a non-standard exit code when it doesn't find a solution in time, which the harness interprets as INDETERMINATE rather than TIMEOUT.
- Malformed formulas: mallob is lenient with some malformed input and may return SAT or UNSAT instead of erroring, since it silently ignores certain formatting issues.

### Workers Not Connecting

**Symptom:** Leader can't reach workers, SSH failures

**Check:**
- Workers are registered in DynamoDB (check tables in AWS Console)
- Security groups allow traffic on port 22 (SSH)
- All nodes are in the same VPC subnet

### Cleanup Not Working

**Symptom:** Processes persist between jobs, causing failures

**Solution:**
- Ensure `get_cleanup_command()` actually kills your processes
- Test the command manually in a container
- Add more aggressive cleanup (pkill, killall)

### Workers Die During Solving

**Symptom:** Solver fails mid-run, workers marked dead

**Check:**
- Memory usage - workers might be OOM-killed
- Disk usage - workers might fill up temp space
- Network - MPI communication issues

### Leader Never Finds Workers

**Symptom:** Leader waits indefinitely for workers

**Check:**
- `num_worker_nodes_per_leader` matches your `start-instances` count expectations
- DynamoDB tables are created (check CDK deployment)
- Workers are starting (check ECS task status)

## Best Practices

1. **Test with small worker counts first** - Start with 1-2 workers before scaling up

2. **Implement robust cleanup** - Your cleanup command should work even if the solver
   crashed unexpectedly

3. **Use MPI's built-in fault tolerance** if available - Some MPI implementations can
   handle worker failures gracefully

4. **Monitor memory carefully** - Distributed solvers often use significant memory for
   clause sharing; size instances appropriately

5. **Log verbosely during development** - Add logging to understand coordination issues

## Next Steps

- See [Troubleshooting](05-troubleshooting.md) for solutions to common issues.
- Then move to the next section: [Running on AWS](../running-on-AWS/README.md).
