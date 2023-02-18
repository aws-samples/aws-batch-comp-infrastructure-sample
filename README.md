# SAT-Comp and SMT-Comp Cloud Track Instructions

The goal of this repository is to help you get your solver running efficiently on AWS, either as a parallel solver or a distributed solver.  Getting your solver ready requires two stages: preparing docker containers with your solver and connecting to AWS infrastructure.

Last year, we received some feedback about how it was challenging to debug solvers on AWS.  This year we provide some guidance and scripts to allow you to debug your parallel and distributed solvers locally using some Docker tricks prior to running at larger scale on AWS resources.  This should allow teams to get solvers running in a stable way prior to upload, and we think this will reduce frustration when developing solvers.

We recommend that you work in four steps:
    1. Creating and configuring a test AWS Account 
    2. Setting up infrastructure to run an example distributed solver.
    3. Creating your own solver and running experiments.
    4. Once ready, sharing the solver repository and Docker image with us for the competition.

For step #3, we provide some guidance on running solvers locally within Docker.  This allows you to perform your initial debugging locally prior to uploading to the cloud.

The AWS-infrastructure steps are described in the [Infrastructure README](infrastructure/README.md), and the docker-related steps and debugging are covered in [SAT-Comp Docker Images](docker/README.md).


This tutorial walks through setting up AWS infrastructure, installing the solver containers, and submitting queries.

