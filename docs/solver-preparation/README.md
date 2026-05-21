# Solver Preparation and Packaging

This guide is for **solver authors** who want to package,
test, and submit their solvers for the SAT or SMT competitions.

You should have already completed the steps in the [Getting Started](/docs/getting-started/README.md) guide.

## Guide Contents

1. [Packaging Your Solver](01-packaging-solver.md) - Fetch and build your solver in a Docker container
1. [Configuration](02-configuration.md) - Tell the harness how to invoke your solver and set up a configuration file
1. [Local Testing](03-local-testing.md) - Build and verify locally before AWS deployment
1. [Distributed Solvers](04-distributed-solvers.md) - (Distributed solvers only) multi-node solver setup with a leader/worker pattern
1. [Troubleshooting](05-troubleshooting.md) - Common issues and solutions

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

## Next Step

[Learn](/docs/running-on-AWS/README.md) how to deploy, run, analyze, and teardown your solver on AWS.

## Need Help?

Contact us at: [solver-competitions@amazon.com](mailto:solver-competitions@amazon.com)
