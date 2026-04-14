# SAT/SMT Competition Infrastructure

Welcome to the 2026 [SAT](https://satcompetition.github.io/) and [SMT](https://smt-comp.github.io/2026/) solver competitions. AWS is happy to again sponsor the parallel and distributed tracks. The competition infrastructure has been rewritten for this year. 

Our primary goal in rewriting this package was to make it easier for you, the solver research community, to prepare your solvers for entry in the competitions. That process is much simpler now; you need to submit only two files: a Dockerfile to build your solver, and a small Python shim to connect your solver inputs and outputs to data structures used by the package.

This package enables you to package, build, and test solvers on a local machine. A single script serves as the entrypoint to preparing and running solvers. The package supports running solvers in parallel or distributed mode. Functionality is included to qualify your solver before submission. 

The competition will take place on exactly the same package. This should minimize incompatibility experienced previously between the mock infrastructure used to prepare solvers and the infrastructure used to run the competition.

The package contains lots of examples, including many solvers from previous competitions. This should be an effective starting point: ideally, you will not have to go deep into the detailed documentation.

We hope you find this package useful. This is not production software, and we expect that issues will surface as we all prepare for the competitions. Reach out to us if you have questions. 

Finally, a reminder that your AWS account is charged for the AWS resources you consume. We intend that this package will help you manage those resources. However, you are responsible for resources consumed by your account, and we strongly suggest manually checking for any remaining resources when your work is complete.

## Documentation Overview

We have organized the documentation around three activies:

1. [Getting Started](/docs/getting-started/README.md). In this step, you will install software dependencies and get your AWS account and permissions set up.
1. [Solver Preparation](/docs/solver-preparation/README.md). You will prepare your solver by packaging it in Docker and providing a shim between the package and your solvers input/output. You will configure a project YAML that provides information about how and where to run your solver. A jobs YAML will be used to organize job submission. Local testing functionality enables you to debug your solver packaging before deploying to AWS. A dedicated section covers the extra requirements for distributed solvers. Finally, a troubleshooting section should help if you experience issues.
1. [Running on AWS](/docs/running-on-AWS/README.md). The final activity will deploy your packaged solver to AWS. You will start tasks that run your solver in Docker containers. You will submit jobs and collect results.

In addition to the activity-based documentation, there is a system, developer, and testing overview in [Architecture](/docs/architecture/README.md).


## Workflow Overview

### Setup

Set up your AWS account and configure your permissions. Install the package dependencies.

Activate the Python virtual environment, set environment variables, and check dependency versions. Note that this adds the repository root directory to $PATH:

```bash
source satcomp-activate.sh    # Prompt changes to (venv-satcomp)
satcomp.py -h                 # View help - works from any directory
```

### Solver Packaging

After sourcing the venv, you can run satcomp.py commands from any directory. We suggest using a directory outside of the package:

AWS setup:
```bash
satcomp.py bootstrap        # AWS setup
```

First time, and after creating your `Dockerfile`, `solver_cmd.py`, and `config.yml`:
```bash
satcomp.py build            # Build Docker images locally
```

Test locally:
```bash
satcomp.py build                              # build Docker images locally
satcomp.py config.yml test-local              # test all solvers in config in local docker containers
satcomp.py config.yml test-local mysolver     # test specific solver in local docker container
satcomp.py test                               # test against submission requirements in local 
```       

### Running on AWS

Push to AWS
```bash
satcomp.py build            # build Docker images locally (if needed)
satcomp.py push             # build Docker images
```

Starting containers, running tests, stopping containers:
```bash
satcomp.py start-instances [n]        # start n instances for each solver (activate compute, can take 15 minutes)
satcomp.py submit                     # Submit the jobs referenced in jobs.yml
satcomp.py terminate-instances        # terminate solvers (when input queues are empty)
satcomp.py collect                    # read solver output from AWS output queues and copy into local results
```

Cleaning up when complete:
```bash
satcomp.py teardown all      # delete AWS resources
```

### Next Step

It's time to [Get Started](/docs/getting-started/README.md)! In this step, you will install software dependencies and get your AWS account and permissions set up.


## Getting Help

If you run into issues not covered by the documentation, contact us:

- SAT Competition: [sat-comp@amazon.com](mailto:sat-comp@amazon.com)
- SMT Competition: [aws-smtcomp-2024@googlegroups.com](mailto:aws-smtcomp-2024@googlegroups.com)

## Submitting Your Solver (Competitors)

Send us a link repository containing your Dockerfile and `solver_cmd.py` files.
We will clone those, along with the solver code (and any other code) that your build downloads.
Note that everything must be built from source to meet both the open-source spirit of the competition and for security reasons.