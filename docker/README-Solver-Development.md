# Solver Development for SAT/SMT-Comp

This README covers the process of building your solver and embedding it in docker images.  We first show the steps to build and run an example solver, Mallob, then describe how to build your own solver within Docker and test it on your local machine.

## Prerequisites

Platforms Amazon Linux 2 (AL2), Ubuntu 20, and Mac OS Monterey (v12.6) have been tested successfully. Builds on other platforms may work, but have not been tested.

To build and run solvers, you will need the following tools installed:

- [python3](https://www.python.org/).  To install the latest version for your platform, go to the [downloads](https://www.python.org/downloads/) page.
- [docker](https://www.docker.com/).  There is a button to download Docker Desktop on the main page.

Basic familiarity with Docker will be helpful, but we will walk you through step-by-step. If you need more information, there are a number of excellent tutorials, such as [this](https://docs.docker.com/get-started/).


# Example: Mallob

This example covers two configurations: parallel (single node, multiple cores) and distributed (multiple nodes, multiple cores per node). Because building a distributed solver is a superset of of building a parallel solver; we will note steps that are only required for a distributed solver. 

We use [Mallob](https://github.com/domschrei/mallob) as the running example for both parallel and distributed solvers. This example pulls a version of Mallob that we have tested with the AWS infrastructure. Note that although this repository is released under the MIT-0 license, the Dockerfiles use the Mallob project.  Mallob and the solvers it uses have other licenses, including the [LGPL 3.0](https://opensource.org/license/lgpl-3-0/) license.

This section proceeds in three steps:
- Building base SATcomp Docker images
- Building Mallob Docker images
- Running Mallob in Docker

## Building the SATComp Base Images

To simplify the solver construction process, we provide base Docker images that manage the infrastructure necessary for solvers as well as access to AWS resources. We will build three images, a common image, a leader, and a worker. One leader coordinates multiple workers. The Dockerfiles and needed resources are contained in the [satcomp-images](satcomp-images) directory.

To begin, navigate to the `satcomp-images` directory and execute the `build_satcomp_images.sh` script.  This script will build three images: `satcomp-infrastructure:common`, `satcomp-infrastructure:leader`, and `satcomp-infrastructure:worker` that correspond to the common, leader, and worker images.

### Checking Docker Build Results

After buliding the docker images, check to make sure the images have built successfully:

1. Run `docker image ls` or `docker images`
2. Make sure that you see `satcomp-infrastructure:common`, `satcomp-infrastructure:leader`, and `satcomp-infrastructure:worker` in the list of images.

You should get a response similar to

    % docker image ls
    REPOSITORY               TAG       IMAGE ID       CREATED         SIZE
    satcomp-infrastructure   worker    83e1a25f57a9   5 minutes ago   819MB
    satcomp-infrastructure   leader    766b446bd057   5 minutes ago   817MB
    satcomp-infrastructure   common    51da12f359f8   6 minutes ago   725MB
    ubuntu                   20.04     e40cf56b4be3   7 days ago      72.8MB
    % 

## Building Mallob Images

To build the mallob distributed solver images, we will use the satcomp infrastructure worker and leader images built previously. To begin, cd into the `mallob-images` directory, which contains the needed Dockerfiles and other infrastructure. 

To build all three docker images in one step, execute the `build_mallob_images.sh` script. You will want to create a similar script for your solver.  More information on the script and how to build each docker image individually is available in the Q&A section of the document.

After building the mallob images, run `docker image ls` and make sure you see both `satcomp-mallob:leader` and `satcomp-mallob:worker` in the list of images.

This is what `docker image ls` shows for the tutorial to this point:

    % docker image ls
    REPOSITORY               TAG       IMAGE ID       CREATED          SIZE
    satcomp-mallob           worker    f3a2276355eb   2 minutes ago    916MB
    satcomp-mallob           leader    c3045f85f3bc   2 minutes ago    914MB
    satcomp-mallob           common    4bcf7c5a156e   2 minutes ago    1.58GB
    satcomp-infrastructure   worker    dad677687909   11 minutes ago   819MB
    satcomp-infrastructure   leader    c439dfb34537   12 minutes ago   817MB
    satcomp-infrastructure   common    3b2935f84a7c   12 minutes ago   725MB
    ubuntu                   20.04     e40cf56b4be3   2 weeks ago      72.8MB 
    
## Running Mallob

We will use `docker run` to create docker _containers_ (processes) as instances of the docker _images_ we created in the previous section. 

To find out which docker containers are running, use the command `docker ps`. The command `docker ps -a` will include containers that have already exited. To remove a container, run `docker rm <CONTAINER_ID>`. To remove all containers, run `docker rm $(docker ps -aq)`.

### Creating a Docker Network

Before running mallob we need to create a docker bridge network that our containers can attach to. This is necessary for both parallel and distributed mallob. Create a network named `mallob-test` by running the command `docker network create mallob-test`.

### Running Parallel Mallob

To run parallel Mallob, navigate to the `runner` directory. We have created a simple shell script called `run_parallel.sh`, which you will use to run the mallob_parallel docker image, starting a container and running a SAT/SMT problem in the container. The script has two variables that can be configured if you wish (described in Q&A) but are set to sensible defaults.  

 **N.B.:** Because the docker image runs as a different user and group than the local host, you need to set the directory permissions so that Docker image can read and write to the directory.  Please run: `sudo chgrp -R 1000 . && chmod 775 .` from the `docker/runner` directory so that the container can access this portion of the filesystem..
 
The `run_parallel.sh` script requires two command-line arguments.
- <docker_image_name>, which is `satcomp-mallob` for this example. 
- <query_file>, which is the name of the test file for the solver.  If you use the defaults, you should put SAT/SMT files in the docker/runner/experiment subdirectory, and if you run the script from the `runner` directory, then you can use standard shell completion for paths.

To run the script with the `test.cnf` file we provided, call `run_parallel.sh satcomp-mallob experiment/test.cnf` from within the `runner` directory. After creating a container, the script will drop you into a bash shell for this container.

The script will create an `input.json` file in the host run directory. This file will be copied to the docker run directory `/rundir`, where it will be read by the solver script.

The script comments explain the various arguments to the `docker run` command. The `docker run` invocation uses bash as the docker entrypoint and passes `init_solver.sh` as a command to bash. The initialization script starts sshd and then runs `/competition/solver /rundir`, which will execute the solver on the query in `<query_file>`. At this point, you should see mallob STDOUT and STDERR on the terminal as mallob runs the solver query. 

### Running Distributed Mallob

Running distributed mallob requires two docker invocations running in two different terminal windows: one to start a leader container and one to start a worker container. 

To run distributed Mallob, again cd into the `runner` directory. You will use two shell scripts, `run_dist_worker.sh` and `run_dist_leader.sh`. 

- Step 1. Invoke `run_dist_worker.sh`, which requires a single command-line argument <docker_image_name>, which is `satcomp-mallob` for this example. Notice that the script will launch a `satcomp-mallob:worker` container. You will be dropped into a bash shell for the worker container. No further commands are needed.
- Step 2. From a different terminal on the host machine (in the same `runner` directory), invoke `run_dist_leader.sh` This script requires the same two command-line arguments as `run_parallel.sh` in the previous section. For example, you can call `run_dist_leader.sh satcomp-mallob experiment/test.cnf`

The `run_dist_leader` script will again create an `input.json` file, with more fields than used for parallel mallob. Again, you should see mallob output on the terminal.

### Debugging

After the solver query runs, you will be left in a bash shell prompt that is executing in the docker leader container. At that point, you can explore. You will see the `/competition` directory with the solver scripts. You will also see the `/rundir` directory that includes your test file, the solver input file `input.json`, and three output files:

If mallob ran successfully, you will find three new files in `/rundir`:

- `solver_out.json`
- `stdout.log`
- `stderr.log`

Again, note that the container directory `/rundir` is the mount point for the  host run directory as specified by the script variable `HOST_RUNDIR`. The files in `/rundir` will persist on the host filesystem, even after the docker container is stopped or removed.

At this point, you can perform additional experiments or exit the docker shell.

The competition infrastructure starts solver containers and keeps them running for multiple queries. Each query will have a new `input.json` file, and `/container/solver` will be run again.

**N.B.:** When debugging your own solver, the key step (other than making sure your solver ran correctly) is to ensure that you clean up resources between runs of the solver.  You should ensure that no solver processes are running and any temporary files are removed between executions.  During the competition, the docker images will be left running throughout and each SAT/SMT problem will be injected into the running container.  You are responsible for cleaning up files and processes created by your solver.   In the case of Mallob, it performs the cleanup of temporary files for the leader when the solver starts (rather than when it finishes), so that you can inspect them after the solver completes execution.  

To check for orphaned jobs, use the `ps -ax` in both the leader and worker containers.  This should show you all running processes. Make sure there aren't any stray processes that continue execution.   In addition, check all the locations in the container where your solver places temporary files in order to make sure that they are removed after the run.

If your solver doesn't run correctly in the docker container, you can remove the `/container/solver` commands from the `init_solver.sh` files. Once you are dropped into the docker container's bash shell, you can explore and debug directly, including running `/container/solver /rundir` from the container shell command line.

We have now run, debugged, and inspected a sample solver.  It is a good idea to try out multiple files, inspect the results, and try running in both cloud and parallel configurations.  Once you are comfortable with these interactions, it is time to start working on your own solver.

# Preparing Your Own Solver Images

In the previous section, we walked through building and running a sample solver in both cloud and parallel configurations.  We assume at this point that you know how to build with Docker and how to run it locally using the scripts that we have provided.  We recommend that you run through the Mallob example before you start building your own images, but of course you can start here and then follow the same steps as described in "Running Mallob" using your own images.

In this section, we'll talk about how to build your own solvers into Docker containers that are derived from the base containers that we provide.  All of the interaction with AWS services for deployment on the cloud is managed by the Docker base images.  We provide two base images: one for leader nodes and one for worker nodes (N.B.: workers are only required for the cloud track).  The Leader Node is responsible for collecting IP addresses of available worker nodes before starting the solving process, pulling work from an SQS queue, downloading problem instances from S3, and sharing and coordinating with Worker Nodes. The Worker Node base container is responsible for reporting its status and IP address to the Leader Node.  As these base images manage the interaction with AWS, you can build and test your solvers locally, and they should work the same way when deployed on the cloud.

## Building from Competition Base Containers

Your solver must be buildable from source code using a standard process. We use Docker to create a build process that can easily be standardized. Docker removes many of the platform-specific problems with building under one operating system and running in another.

You will provide a GitHub repo with a Dockerfile in the top directory that we will use to build your solver. This first section of this README constructed just such a solver.  In this guide, we start by building and running the solver locally, then once it is working properly, we will use the [Infrastructure README](../infrastructure/README-Infrastructure.md) to test it using AWS resources.  We will use the same process to host your solver during the competition.

For the cloud track, you will need to supply two Dockerfiles for your solver, one that acts as a Leader Node and one that acts as a Worker Node. In the case of a parallel solver, you only need to provide a single image, which we will also call a Leader Node for convenience.

The Docker base images are contained in the `satcomp-images` directory. As you follow this example, you should also consult the `mallob-images` directory to see how we based the Mallob examples on the images in `satcomp-images`.

You should begin your Dockerfiles with:

```text
    FROM satcomp-infrastructure:leader
```
or

```text
    FROM satcomp-infrastructure:worker
```

The base images (which are based on ubuntu:20.04) have predefined entrypoints that will start when the container is invoked. These entrypoints handle all interaction with the competition infrastructure. As a result, you are only responsible for invoking your solver; we expect that you will not have to write code for most of the interactions with AWS resources.

### Leader Base Container

The Leader Base Container sets up the SAT/SMT problem for the solver.  It loads the SAT/SMT problem, then attempts to run an executable file in the docker image in the `/competition/solver` directory.  It provides a single argument to this file, which is a directory path containing a file called `input.json`.  

Here is an example of the `input.json` file for cloud mallob:

```text
{
  "formula_file": "/mount/efs/problem.cnf",
  "formula_language": "DIMACS", 
  "solver_argument_list": ["-p", "another_arg"],
  "timeout_seconds": 10,
  "worker_node_ips": ["192.158.1.38", "192.158.2.39", ...]
}
```

where: 
* `formula_file` is the path to the SAT/SMT problem to be solved.
* `formula_language` is the encoding of the problem (currently we use DIMACS for SAT-Comp and SMTLIB2 for SMT-Comp).  This field is optional and can be ignored by the solver.
* `solver_argument_list` allows passthrough of arguments to the solver.  This allows you to try different strategies without rebuilding your docker container by varying the arguments.
* `timeout_seconds` is the timeout for the solver.  It will be enforced by the infrastructure; a solver that doesn't complete within the timeout will be terminated.
* `worker_node_ips` is unchanged; for cloud solvers, it is the list of worker nodes.  For parallel solvers this field will always be the empty list.

For the interactive example in the first section, this file is generated by the [`run_parallel.sh`](runner/run_parallel.sh) script. 

The solver is then expected to run and generate a file called `solver_out.json`.  
Here is an example of `solver_out.json` from distributed mallob:

```text
{
  "return_code": int,      // The return code for the solver.
  "artifacts": {
    "stdout_path": String, // Where to find the stdout of the solve run
    "stderr_path": String  // Where to find the stderr of the solve run
  }
}
```

where:
* `return_code` is the return code for the solver.  **N.B.**: The return_code in `solver_out.json` will determine the satisfiability of the problem for the solver: A return code of 10 indicates SAT, 20 indicates UNSAT, 0 indicates UNKNOWN, and all other return codes indicate an error.
* `stdout_path` is the path to the stdout log.
* `stderr_path` is the path to the stderr log.

You will adapt the Mallob `solver` script to invoke your solver and coordinate with Worker nodes. You should extend the competition base image by copying your `solver` script to a new container that is based on the Competition Base Container.

For example:

```text
FROM satcomp-base:leader

# Do all steps necessary to build your solver
RUN apt-get install my-amazing-solver

# Add your solver script
COPY solver /competition/solver
RUN chmod +x /competition/solver
```

Consult the Mallob [leader Dockerfile](mallob-images/leader/Dockerfile) for a more complete example. Note that you should not provide a docker entrypoint or a CMD because the entrypoint is specified by the base container.

### Worker Base Container

Workers are expected to be controllable by the leader node using `ssh`.  For workers, competitors have three responsibilities: 
1. To report their status to the AWS infrastructure once per second, to determine whether work can be allocated to them.
2. To clean up when the leader completes a problem (or terminates with an error).
3. To assist with the solving process using ssh.

#### Reporting Status 

To accomplish the first task, the infrastructure assumes that there is an executable at the location `/competition/worker` that will report status once per second.  Status reporting is done by updating a file at location `/competition/worker_node_status.json`.  The file contains a current status (one of {READY, BUSY, ERROR}), and a timestamp. The timestamp is the unix epoch time as returned by the linux time() function.  If the worker fails to update this status file for more than 5 seconds, the worker node will be considered failed and the infrastructure will reset the node. Repeated failures of worker nodes (likely to be a maximum of three) will cause the system to score the problem as an 'error'.

Here is an example of the format for `worker_node_status.json`:

```text
{
    "status": "READY",  // one of {"READY", "BUSY", "ERROR"}
    "timestamp": "1644545117" // linux epoch time as returned by the C time() function
}
```

The Mallob worker script is a 'bare-bones' example of status reporting that simply checks the status of the worker process and sshd. See the [worker](mallob-images/worker/worker) for details.

#### Cleaning up

You are also responsible for writing a worker `cleanup` script that is executed when a solving task is complete.  The infrastructure will ensure that this file is called after the leader completes on a SAT/SMT problem, or after the leader fails in some way.  We add this capability to make it straightforward to kill solver nodes that are still working on subproblems when the leader node completes.  Given that the leader can also communicate with the worker using SSH, this file is not strictly necessary depending on how the system is architected (i.e., if the leader can gracefully and quickly terminate all workers at the end of solving, and the leader itself does not fail).  

In normal operation, this script is executed by the infrastructure when the leader process completes. It will also be executed when a failure occurs. The script must reset the worker state (the node will remain) so that it is ready to solve the next problem.

For example:

```text
FROM satcomp-base:worker

# Do all steps necessary to build your solver
RUN apt-get install my-amazing-solver

# Add your solver script
COPY worker /competition/worker
RUN chmod +x /competition/worker

COPY cleanup /competition/cleanup
RUN chmod +x /competition/cleanup
```

See the Mallob worker [Dockerfile](satcomp-images/satcomp-worker/Dockerfile) for more details.

#### Assisting with the Solving Process

There are many ways to accomplish this goal, and to some degree this is the critical part of building a distributed solver.  In past years, many competitors have used [MPI](https://en.wikipedia.org/wiki/Message_Passing_Interface) to structure the communications between the leader and worker nodes (Mallob is one example that uses MPI), but competitors have the freedom to structure communication in whatever way makes the most sense for their solver.  Worker nodes are not passed a representation of the SAT/SMT problem by the infrastructure: instead the leader must communicate the problem (or a portion of it) to the worker.

## Next step: Building / Running on AWS Infrastructure
After building your solvers, please test them using Docker, as we did with Mallob in this README.  Once you have built your solver and you are confident that it works properly using Docker, then you are ready to try it out at larger scale on AWS infrastructure.  Next, please navigate to [Infrastructure Readme](../infrastructure/README-Infrastructure.md), where the process of uploading, running, and debugging your docker images on AWS is described.  


## FAQ / Troubleshooting

### Q: What is the build_mallob_images.sh script doing?  What do the flags for docker build mean?

The script looks like this: 

    # /bin/sh
    cd common
    docker build -t satcomp-mallob:common .
    cd ..

    cd leader
    docker build -t satcomp-mallob:leader .
    cd ..

    cd worker
    docker build -t satcomp-mallob:worker .
    cd ..

First we factor out the common parts of the leader and worker into a common image.  This Dockerfile builds the Mallob solver and its components that will be used by both the leader and the worker image.  Then we use this common image to build the leader and worker images.  

Docker has two characteristics for build that are important for this script.  The `-t satcomp-mallob:common` argument tells Docker to give the newly constructed image a _tag_ that provides a name for the docker image.   The second thing is that all file paths in Docker are local to the directory where the `docker build` command occurs.  This is why we need to navigate to the directory containing the Dockerfile prior to running the build.

Note that there is also a `nocache_build_mallob_images.sh` script.  Although Docker does a pretty good job of dependency tracking, certain changes are invisible to it.  For example, Docker can determine whether there has been an update to the Mallob repository, but if Mallob calls out to another repository, then Docker will not detect it, and you might get a stale build.  To guard against this, there is a `--no-cache` flag that will do a full rebuild.  If your solver has similar indirect dependencies, you might need to use the `--no-cache` flag.

#### To build the Mallob leader image:

1. Navigate to the `leader` subdirectory.
2. Run `docker build -t satcomp-mallob:leader .` The resulting image will be named `satcomp-mallob:leader`.  This Dockerfile adds scripts necessary to use Mallob as the leader node in a distributed solver to the generated image.

#### To build the Mallob worker image:

1. Navigate to the `worker` subdirectory.
2. Run `docker build -t satcomp-mallob:worker .`  This Dockerfile adds scripts necessary to use Mallob as the worker node in a distributed solver to the generated image.


### Q: Suppose I want to change the directory or network name for the run_parallel and run_cloud scripts.  How do I do this?

A: The two variables to change are: 
- `DOCKER_NETWORK`. Name of the docker bridge network. The default is  `mallob-test`, which will work with the `network create` command in the previous section.  
- `HOST_RUNDIR`. Name of the host directory that will be mounted in the docker run directory. _Note: This should be an absolute pathname and it must be updated for your filesystem._ This directory will be mounted in the docker container and enables you to persist information over multiple docker container sessions. We have placed an `experiment` directory inside `runner` that you can use to begin.  

These are both documented in the script files.


### Q: After a while, I have lots of old versions of Docker images that are taking up disk space that I no longer need.  How do I get rid of them?

A: On repeated image builds, previously-built images with the same name will be left with the name/tag as `<none>/<none>`. Docker dangling images can be deleted with `docker image prune`. A specific image can be deleted by running `docker rmi <IMAGE ID>`. 

Note that you can delete all docker images on your machine by running `docker rmi -f $(docker images -a -q)`. Be careful: only do this after running `docker images` to check that you won't delete images unrelated to the solver competition. 

### Q: I'm only submitting to the parallel track and not the cloud track. Do I need a worker image?

A: No. If you are submitting to the parallel track only, you do not need a worker image. For the parallel track, we will assume that the leader manages all threading and communications within the single (multi-core) compute node.
