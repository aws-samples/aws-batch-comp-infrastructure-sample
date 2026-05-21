# Configuration

This page explains how to register your solver in `config.yml`.

## Overview

After preparing your Dockerfile and `solver_cmd.py`, you must add your solver's
information to a satcomp configuration file. 

We recommend putting these files in a directory outside the competition infrastructure. By default the scripting will look for a `config.yml` in the run directory, but you can name it anything.

The directory [examples/configs/](../../examples/configs/) contains examples for several solvers, and should contain good starting points for you.  A fully-documented reference [config-reference.yml](../../examples/configs/config-reference.yml) is also available.

## Basic Configuration

Here's a minimal solver configuration for a SAT solver:

```yaml
project: myproject
profile: default    
region: us-east-1
solver_type: sat

solvers:
  - name: mysolver
    docker_dir: ./docker/
    dockerfile: mysolver/Dockerfile
```

## Required Fields

### Project-Level Fields

| Field | Description |
|-------|-------------|
| `project` | Name for your project. Used to label AWS resources. |
| `profile` | AWS profile from `~/.aws/credentials` (usually `default`). |
| `region` | AWS region (e.g., `us-east-1`). Must stay fixed after `provision`. Changing regions requires `teardown all`, then `bootstrap` and `provision` in the new region. |
| `solver_type` | Either `sat` or `smt`. Determines accepted file extensions. |

### Solver-Level Fields

| Field | Description |
|-------|-------------|
| `name` | Unique name for your solver. Used in AWS resource names. |
| `docker_dir` | Directory containing your Dockerfile (absolute or relative to config.yml). |
| `dockerfile` | Path to Dockerfile, relative to `docker_dir`. |

## Optional Fields

### Solver Options

| Field | Default | Description |
|-------|---------|-------------|
| `author` | (none) | Author/team name. Added to log file names. |
| `is_distributed` | `false` | Set `true` for multi-node distributed solvers. |
| `num_worker_nodes_per_leader` | `0` | Number of worker nodes (distributed only). |
| `ec2_instance_type` | `m6i.xlarge` | EC2 instance type for running your solver. |
| `disk_size` | `32` | Disk size in GB for your container. |

### Global Solver Options

You can set defaults for all solvers using `global_solver_options`:

```yaml
global_solver_options:
  is_distributed: false
  num_worker_nodes_per_leader: 0
  ec2_instance_type: m6i.xlarge
  disk_size: 32

solvers:
  - name: solver1
    # Inherits global_solver_options
    docker_dir: ./docker/
    dockerfile: solver1/Dockerfile

  - name: solver2
    # Override specific options
    docker_dir: ./docker/
    dockerfile: solver2/Dockerfile
    ec2_instance_type: m6i.2xlarge    # Uses larger instance
    disk_size: 64                      # More disk space
```

## EC2 Instance Types

Common instance types for solvers:

| Type | vCPUs | Physical cores |Memory |
|------|-------|--------|-----|
| `m6i.xlarge` | 4 | 2 | 16 GB |
| `m6i.2xlarge` | 8 | 4 | 32 GB |
| `m6i.4xlarge` | 16 | 8 | 64 GB |
| `m6i.16xlarge` | 64 | 32 | 256GB |

See `scripting/common/ec2_instance.py` for the full list of supported types.

Note: Your solver has exclusive access to the instance. Note that each vCPU corresponds to a hardware hyperthread, not a physical core. Solvers are typically cache- and memory-intensive, and our benchmarking shows that assigning one process per physical core (rather than one per vCPU) usually gives better performance.

## Example: Parallel Solver

```yaml
project: satcomp25
profile: default
region: us-east-1
solver_type: sat

solvers:
  - name: cadical
    author: abiere
    docker_dir: ./docker/
    dockerfile: cadical/Dockerfile
    ec2_instance_type: m6i.xlarge
    disk_size: 32
```

## Example: Distributed Solver

```yaml
project: satcomp25
profile: default
region: us-east-1
solver_type: sat

solvers:
  - name: mallob
    author: dschrei
    docker_dir: ./docker/
    dockerfile: mallob/Dockerfile
    is_distributed: true
    num_worker_nodes_per_leader: 7    # 1 leader + 7 workers = 8 total nodes
    ec2_instance_type: m6i.4xlarge
    disk_size: 64
```

## Multiple Configuration Files

You can maintain multiple configuration files for different purposes:

```bash
./satcomp.py parallel_config.yml provision build push
./satcomp.py distributed_config.yml provision build push
```

This is useful for:
- Separating parallel and distributed solvers
- Testing with different EC2 instance types
- Managing multiple teams' solvers if you are a competition organizer

## Naming Rules

- Project and solver names **must not contain `--`** (double hyphen) - we use it as resource name field separator
- Single hyphens are fine (e.g., `my-solver`, `sat-comp-25`)
- The config parser validates this at startup


## Next Steps

After preparing your YAML config file, it's time for [local testing](03-local-testing.md).
