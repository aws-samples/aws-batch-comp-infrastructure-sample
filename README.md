# SAT-Comp and SMT-Comp Cloud Track Instructions

This repository will help you get your parallel or distributed solver running efficiently on AWS.  You will build docker containers with your solver and then connect them to the AWS infrastructure.

Last year, we received feedback that it was challenging to debug solvers on AWS.  This year, we provide guidance and scripts to enable debugging your parallel and distributed solvers locally prior to running at larger scale on AWS resources. This will enable you to get solvers running in a stable way before uploading to AWS, which should reduce the overhead of preparing your solver for submission.

We recommend that you work in four steps:

1. Create and configure an AWS Account for the competition
2. Set up AWS infrastructure to run an example distributed solver
3. Create your own solver and run experiments
4. When ready, share the solver repository and Docker image with us

You should begin with the AWS infrastructure steps as described in the [Infrastructure README](infrastructure/README.md). That README will direct you to Docker-related steps and debugging that are covered in [Docker Images for SAT/SMT-Comp](docker/README.md).
