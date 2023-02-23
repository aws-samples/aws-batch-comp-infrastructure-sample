# Docker Images for SAT/SMT-Comp

This README covers the process of building your solver and embedding it in docker images. We suggest that you proceed in two stages: build the Mallob example and test it with the infrastructure [you have just created](../infrastructure/README.md). Once you have the Mallob example working, return to this README and follow the instructions in the [second section](#preparing-your-own-solver-images).

# Example: Mallob

This example covers two configurations: parallel (single node, multiple cores) and distributed (multiple nodes, multiple cores per node). Because building a distributed solver is a superset of of building a parallel solver; we will note steps that are only required for a distributed solver. 

We use Mallob as the running example for both parallel and distributed solvers. This example pulls a version of Mallob that we have tested with the AWS infrastructure. 

This section proceeds in four steps:
- Preparing your system
- Building base SATcomp Docker images
- Building Mallob Docker images
- Running Mallob in Docker

## Prerequisites

1. Amazon Linux 2 (AL2) or Ubuntu 20. Builds on other platforms may work, but have not been tested.

2. Install Docker.  

Basic familiarity with Docker will be helpful, but we will walk you through step-by-step. If you need more information, there are a number of excellent tutorials, such as [this](https://docs.docker.com/get-started/).

## Building the SATComp Base Images

To simplify the solver construction process, we provide base Docker images that manage the infrastructure necessary for solvers and menage access to AWS resources. We will build three images, a common image, a leader, and a worker. One leader coordinates multiple workers. The Dockerfiles and needed resources are contained in the [satcomp-images](satcomp-images) directory.

To begin, cd into the `satcomp-images` directory. To build all three docker images in one step, execute the `build_docker_base_images.sh` script. To build the images individually, follow the next three steps.

#### 1. Build `satcomp-infrastructure:common` image:

From the `satcomp-images` directory, run `docker build -f satcomp-common/Dockerfile -t satcomp-base:common .`

The common image will take several minutes to build. The next two images are derived from the common image and will build faster.

#### 2. Build `satcomp-infrastructure:leader` image

Run `docker build -f satcomp-leader/Dockerfile -t satcomp-base:leader .`

#### 3. Build `satcomp-infrastructure:worker` image

Run `docker build -f satcomp-worker-image/Dockerfile -t satcomp-base:worker .`

### Checking Docker Build Results

After buliding the docker images, check to make sure the images have built successfully:

1. Run `docker image ls` or `docker images`
2. Make sure that you see `satcomp-infrastructure:common`, `satcomp-infrastructure:leader`, and `satcomp-infrastructure:worker` in the list of images.

Your should get a response similar to

    % docker image ls
    REPOSITORY               TAG       IMAGE ID       CREATED         SIZE
    satcomp-infrastructure   worker    83e1a25f57a9   5 minutes ago   819MB
    satcomp-infrastructure   leader    766b446bd057   5 minutes ago   817MB
    satcomp-infrastructure   common    51da12f359f8   6 minutes ago   725MB
    ubuntu                   20.04     e40cf56b4be3   7 days ago      72.8MB
    % 

### Managing Docker Images

On repeated image builds, previously-built images with the same name will be left with the name/tag as `<none>/<none>`. Docker dangling images can be deleted with `docker image prune`. A specific image can be deleted by running `docker rmi <IMAGE ID>`. 

Note that you can delete all docker images on your machine by running `docker rmi -f $(docker images -a -q)`. Be careful: only do this after running `docker images` to check that you won't delete images unrelated to the solver competition. 

## Building Mallob Images

Note: Although this repository is released under the MIT-0 license, the Dockerfiles use the Mallob project. Mallob licenses include the [LGPL 3.0](https://opensource.org/licenses/lgpl-3.0.html) license.

To build the mallob distributed solver images, we will use the satcomp infrastructure worker and leader images built previously. To begin, cd into the `mallob-images` directory, which contains the needed Dockerfiles and other infrastructure. 

To build all three docker images in one step, execute the `build_mallob_images.sh` script. To build the images individually, follow the next three steps.

#### To build the Mallob common image:

1. Navigate to the `common` subdirectory.
2. Run `docker build -t satcomp-mallob:common .` This will read the Dockerfile in the mallob-common directory and build an image called `satcomp-mallob:common`. This will take several minutes as all of mallob and the solvers used by mallob will be fetched and built from source.

#### To build the Mallob leader image:

1. Navigate to the `leader` subdirectory.
2. Run `docker build -t scatcomp-mallob:leader .` The resulting image will be named `mallob`, with an image tag `leader`.

#### To build the Mallob worker image:

1. Navigate to the `worker` subdirectory.
2. Run `docker build -t satcomp-mallob:worker .`

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

In the this section, we will use `docker run` to create docker _containers_ (processes) as instances of the docker _images_ we created in the previous section. 

To find out which docker containers are running, use the command `docker ps`. The command `docker ps -a` will include containers that have already exited. To remove a container, run `docker rm <CONTAINER_ID>`. To remove all containers, run `docker rm $(docker ps -aq)`.

### Creating a Docker Network

Before running mallob we need to create a docker bridge network that our containers can attach to. This is necessary for both parallel and distributed mallob. Create a network named `mallob-test` by running the command `docker network create mallob-test`.

### Running Parallel Mallob

To run parallel Mallob, cd into the `runner` directory. We have created a simple shell script called `run_parallel.sh` to show you how to run the mallob_parallel docker image to create a running container. The script has several variables that you need to configure.

- `DOCKER_NETWORK`. Name of the docker bridge network. The default is  `mallob-test`, which will work with the `network create` command in the previous section.  
- `HOST_RUNDIR`. Name of the host directory that will be mounted in the docker run directory. _Note: This should be an absolute pathname and it must be updated for your filesystem._ This directory will be mounted in the docker container and enables you persist information over multiple docker container sessions. We have placed an `experiment` directory inside `runner` that you can use to begin.

[MWW: we need to add instructions chmod 777 this directory so that is world-writeable/executable so Docker can use it.]

[MWW: if you make the 'rundir' the base dir where the script runs, then you can use path completion to describe the relative path to the query file.  However, the way the files are placed, you also have to make the directory containg the script is chmod 777. ]

The script requires two command-line arguments.
- <docker_image_name>, which is `satcomp-mallob` for this example. 
- <query_file>, which is the name of the test file for the solver, `test.cnf` in the repository. Note that this file must appear in the host run directory `HOST_RUNDIR`.

The script will create an `input.json` file in the host run directory. This file will be copied to the docker run directory `/rundir`, where it will be read by the solver script.

The script comments explain the various arguments to the `docker run` command. The `docker run` invocation uses bash as the docker entrypoint and passes `init_mallob.sh` as a command to bash. The initialization script starts sshd and then runs `/competition/solver /rundir`, which will execute the solver on the query in `<query_file>`. At this point, you should see mallob STDOUT and STDERR on the terminal as mallob runs the solver query. 

### Running Distributed Mallob

Running distributed mallob requires two docker invocations: one to start a leader container and one to start a worker container. 

To run distributed Mallob, again cd into the `runner` directory. You will use two shell scripts, `run_dist_leader` and `run_dist_worker.sh`. 

- Step 1. Invoke `run_dist_worker.sh`, which requires a single command-line argument <docker_image_name>, which is `satcomp-mallob` for this example. Notice that the script will launch a `satcomp-mallob:worker` container. You will be dropped into a bash shell for the worker container. No further commands are needed.
- Step 2. From a different shell prompt on the host machine in the same `runner` directory, invoke `run_dist_leader.sh` This script requires the same two command-line arguments as `run_parallel.sh` in the previous section.

The `run_dist_leader` script will again create an `input.json` file, with more fields than used for parallel mallob. Again, you should see mallob output on the terminal.

### Debugging

After the solver query runs, you will be left in a bash shell that is executing in the docker container. At that point, you can explore. You will see the `/competition` directory with the solver scripts. You will also see the `/rundir` directory that includes your test file, the solver input file `input.json`, and three output files:

If mallob ran successfully, you will find three new files in `/rundir`:

- `solver_out.json`
- `stdout.log`
- `stderr.log`

Again, note that the container directory `/rundir` is the mount point for the  host run directory as specified by the script variable `HOST_RUNDIR`. The files in `/rundir` will persist on the host filesystem, even after the docker container is stopped or removed.

At this point, you can perform additional experiments or exit the docker shell.

The competition infrastructure starts solver containers and keeps them running for multiple queries. Each query will have a new `input.json` file, and `/container/solver` will be run again.

Your debugging should ensure that you don't leave extra processes running. Check for orphaned jobs with `ps -ax`. In addition, if you create temporary in the container, ensure they are cleaned up.

If your solver doesn't run correctly in the docker container, you can remove the `/container/solver` commands from the `init_mallob.sh` files. Once you are dropped into the docker container's bash shell, you can explore and debug directly, including running `/container/solver /rundir` from the container shell command line.

# Preparing Your Own Solver Images

Before proceeding through this section, you should work through the [infrastructure README](../infrastructure/README.md) up to Section [RBJ:fixme](../infrastructure/README.md#fixme).

In previous years, we asked participants to provide a Dockerfile which would build a container that would handle coordination between nodes and all interactions with AWS infrastructure. This meant that the Dockerfiles and images were quite complicated and included items common to all solvers running on the AWS infrastructure, e.g., retrieving problems from S3, setting up openssh-server.  This required complex, duplicate effort from every team. It also made managing the competition difficult, because we frequently found bugs that were not related to the solvers themselves, but rather to their interfaces with AWS.

This year, we have modified the architecture to make it easier for you, the competitors. Most of the interaction with AWS services is now managed by Docker base images. We provide two base images: one for leader nodes and one for worker nodes. The Leader Node is responsible for collecting IP addresses of available worker nodes before starting the solving process, pulling work from an SQS queue, downloading problem instances from S3, and sharing and coordinating with Worker Nodes. The Worker Node base container is responsible for reporting its status and IP address to the Leader Node.

## Building from Competition Base Containers

Your solver must be buildable from source code using a standard process. We use Docker to create a build process that can easily be standardized. Docker removes many of the platform-specific problems with building under one operating system and running in another.

You will provide a GitHub repo with a Dockerfile in the top directory that we will use to build your solver. This first section of this README constructed just such a solver. Instead of running and interacting with the Docker containers on a local machine, you simply provide them to ECR as exmplained in the [infrastructure overview](../infrastructure/README.md#fixme).

This year, you will need to supply two Dockerfiles for your solver, one that acts as a Leader Node and one that acts as a Worker Node. In the case of a parallel solver, you only need to provide a single image, which we will also call a Leader Node for convenience.

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

The Leader Base Container performs the following steps: 

1. Pull and parse a message from the `[ACCOUNT_NUMBER]-[REGION]-SatCompQueue` SQS queue with the format described in the infrastructure README [Job Submission and Execution section](../infrastructure/README.md#fixme).  
1. Pull the appropriate solver problem from S3 from the location provided in the SQS message.
1. Save the solver problem on a shared EFS drive so that it can also be accessed by the worker nodes.
1. Wait until the requested number of workers have reported their status as READY along with their IP addresses.
1. Create a working directory for this problem.
1. Create and write an `input.json` with the IP addresses of the worker nodes as well as the location of the problem to the working directory
1. Invoke the executable script located at path `/competition/solver` with a single parameter: the path to the working directory. The solver script will look for the `input.json` file in the working directory. It is also the location where solver output and error logs will be written.  
1. The return code for `/competition/solver` will determine the expected result for the solver: A return code of 10 indicates SAT, 20 indicates UNSAT, 0 indicates UNKNOWN, and all other return codes indicate an error.
1. Upon task completion, notify all workers that the task has ended.

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

For the interactive example in the first section, this file is generated by the `run_parallel.sh`[runner/run_parallel.sh] script. Here is an example of `solver_out.json` for distributed mallob:

```text
{
  "artifacts": {
    "stdout_path": String, // Where to find the stdout of the solve run
    "stderr_path": String  // Where to find the stderr of the solve run
  }
}
```

**N.B.**: The return code for `/competition/solver` will determine the satisfiability of the problem for the solver: A return code of 10 indicates SAT, 20 indicates UNSAT, 0 indicates UNKNOWN, and all other return codes indicate an error.

You will adapt the Mallob `solver` script to invoke your solver and coordinates with Worker nodes. You should extend the competition base image by copying your `solver` script to a new container that is based on the Competition Base Container.

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

The Worker Base Container does the following:

1. Reports its IP address to a global Node Manifest and reports its status as READY, BUSY, or ERROR
2. Monitors the Task Notifier for a notification that a solving task has ended
3. Provides cleanup functionality to be executed on the worker node when a solving task has ended.

Although the base container handles all interaction with the Node Manifest and the Task Notifier, individual solvers are responsible for defining what it means to be "READY". When the container comes up, it immediately runs the executable script at `/competition/worker` in a separate process. You should adapt the Mallob [`worker`](Mallob-images/worker/worker) script for your solver.

Workers must update the `worker_node_status.json` file on the file system once per second with a heartbeat, the current status (READY, BUSY, ERROR), and a timestamp. The timestamp is the unix epoch time as returned by the linux time() function.

If the worker fails to update this status file for more than 5 seconds, the worker node will be considered failed and the infrastructure will reset the node. Repeated failures of worker nodes (likely to be a maximum of three) will cause the system to score the problem as an 'error'.

Here is an example of the format for `worker_node_status.json`:

```text
{
    "status": "READY",  // one of {"READY", "BUSY", "ERROR"}
    "timestamp": "1644545117" // linux epoch time as returned by the C time() function
}
```

The Mallob worker script is a 'bare-bones' example of status reporting that simply checks the status of the worker process and sshd. See the [worker](Mallob-images/worker/worker) for details.

You are also responsible for writing a separate worker `cleanup` script that is executed when a task is complete. Note that the leader script will perform leader node cleanup as part of the leader `solver` script. Workers are handled differently. Because one worker could (and will) finish before another, the infrastructure needs to be able to remotely kill workers when the leader registers a solution or fails. This is accomplished with a `cleanup` script that can be invoked in each worker node. This script will perform any cleanup tasks and ensure the node is ready for more work. 

Just as the base Docker image, your Dockerfile should place this script at `/competition/cleanup`. Note that the default `cleanup` script](satcomp-images/satcomp-worker/resources/cleanup) provided as part of the base worker image only kills MPI processes. 

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

See the Mallob worker Dockerfile[docker/worker/Dockerfile] for more details.