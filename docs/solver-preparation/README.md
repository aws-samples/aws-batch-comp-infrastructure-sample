# Solver Preparation and Packaging

This guide is for **solver authors** who want to package,
test, and submit their solvers for the SAT or SMT competitions.

## Quick Start

Get your solver running on AWS:

1. **Prepare your Dockerfile** - Package your solver in a Docker container
2. **Implement solver_cmd.py** - Tell the harness how to invoke your solver
3. **Register your solver in config.yml** - Add your solver configuration
4. **Test locally** - Build and verify your Docker image
5. **Deploy, run, and analyze** - Push to AWS and run test jobs

## Prerequisites

To begin, read and follow the [Getting Started](/docs/getting-started/README.md) guide.

## Guide Contents

1. [Packaging Your Solver](01-packaging-solver.md) - Dockerfile and solver_cmd.py preparation
2. [Configuration](02-configuration.md) - Setting up config.yml for your solver
3. [Local Testing](03-local-testing.md) - Building and testing locally before AWS deployment
4. [Distributed Solvers](04-distributed-solvers.md) - Multi-node solver setup with leader/worker pattern
5. [Troubleshooting](05-troubleshooting.md) - Common issues and solutions

## Example Solvers

The repository includes lots of examples that you can use as templates: Dockerfiles and `solver_cmd.py` shims for multiple solvers, and YAML configuration and jobs files pointing to the solver-specific files.


- `/docker/example/` - Basic example Dockerfile
- `/docker/mallob/` - Complete distributed solver example (mallob)

## What You Can and Cannot Modify

**You should only modify:**
- Your solver's `Dockerfile` and `solver_cmd.py`
- `config.yml` — solver definitions for your solver entries
- `jobs.yml` — job submission configuration

**Do not modify anything else**, including:
- `satcomp.py` — the main CLI entrypoint
- `satcomp-activate.sh` — environment activation script
- `scripting/` — all harness, runner, and testing code
- `cdk_infra/` — AWS CDK infrastructure
- `docker/satcomp-infrastructure/` — the base satcomp Docker image
- `requirements.txt` — Python dependencies
- `examples/formulas/` — test formula files

Modifying infrastructure or harness files will cause your submission to be rejected.

## Submission Checklist

Before submitting your solver for competition:

- [ ] Dockerfile builds successfully
- [ ] `solver_cmd.py` implements `get_run_command()` and `get_solver_result()`
- [ ] Solver builds from source (not copied binaries)
- [ ] Local Docker tests pass
- [ ] `test-local` validation passes (see [Local Testing](03-local-testing.md))
- [ ] Solver respects timeout limits
- [ ] For distributed solvers: `get_cleanup_command()` implemented

## Next Step

[Learn](/docs/using-AWS/README.md) how to deploy, run, analyze, and teardown your solver on AWS.

## Need Help?

- SAT Competition: [sat-comp@amazon.com](mailto:sat-comp@amazon.com)
- SMT Competition: [aws-smtcomp-2024@googlegroups.com](mailto:aws-smtcomp-2024@googlegroups.com)
