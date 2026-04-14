# Developer Guide

This guide is for **developers** who want to understand the codebase,
add features, or fix bugs. Solver authors should not have to consult this material.

## Development Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   source satcomp-activate.sh
   ```
3. Run tests:
   ```bash
   pytest
   ```

## Architecture Overview

This project provides infrastructure for running SAT/SMT solvers on AWS. The main
components are:

- **CLI** (`satcomp.py`) - Command-line interface orchestrating all operations
- **CDK Infrastructure** (`cdk_infra/`) - AWS resource definitions
- **Harness** (`scripting/harness/`) - Docker container runtime code
- **Runner** (`scripting/runner/`) - CLI implementation
- **Analysis** (`scripting/analysis/`) - Results analysis

## Guide Contents

1. [Architecture](01-architecture.md) - System components and data flow
2. [Key Abstractions](02-key-abstractions.md) - Important classes and patterns
3. [Testing](03-testing.md) - Test approach and conventions


## Directory Structure

```
satcomp.py                 # Main CLI entrypoint
scripting/
  common/                  # Shared utilities
    resource_namer.py      # AWS resource naming
    solver_env.py          # Container environment variables
    solver_io.py           # Input/output data structures
  harness/                 # Docker container code
    entrypoints/           # Leader/worker scripts
    aws_shim/              # AWS service wrappers
  runner/                  # CLI implementation
    runner_config.py       # Config parsing
    runner_docker.py       # Docker operations
    runner_jobs.py         # Job management
cdk_infra/
  app.py                   # CDK app entrypoint
  solver_constructs/       # CDK stacks
docker/
  satcomp-infrastructure/  # Base Docker image
  example/                 # Example solver
  mallob/                  # Distributed solver example
tests/                     # Pytest test suite
docs/                      # Documentation
```

## Key Conventions

- **Resource names must not contain `--`** - It's the field separator
- **Formulas must be S3 URIs** - Local paths are not supported for submission
- **Docker images target `linux/amd64`** - Required for AWS EC2
- **Solvers implement `solver_cmd.py`** with required interface functions

## Contributing

1. Create a feature branch
2. Make changes
3. Run tests: `pytest`
4. Submit pull request

## Need Help?


- Review existing tests for usage patterns
- Contact maintainers for architecture questions
