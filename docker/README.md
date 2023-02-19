# Docker-Based SATComp Example: Mallob

This tutorial covers the process of building your solver and embedding it in docker images. We cover two configurations: parallel (single node, multiple cores) and distributed (multiple nodes, multiple cores per node). Building a distributed solver is a superset of of building a parallel solver; we will note steps that are only required for a distributed solver. 

We use Mallob as the running example for both parallel and distributed solvers. This repository contains a version of Mallob that we have tested with the AWS infrastructure. You will build Mallob later in the tutorial.

This README proceeds in four steps:
- Preparing your system
- Building Base SATcomp docker images
- Building Mallob docker images
- Running Mallob

## Prerequisites

1. Run on Amazon Linux 2 (AL2) or Ubuntu 20. Builds on other platforms may work, but have not been tested.

2. Install Docker.  

We assume some basic familiarity with Docker. If you need more information, there are a number of excellent tutorials, such as [this one](https://docs.docker.com/get-started/).

## Building the SATComp Images

To simplify the solver construction process, we provide base Docker images that manage the infrastructure necessary for solvers and mediate access to AWS resources. We will build three images, a common image, a leader, and a worker. One leader coordinates multiple workers. The Dockerfiles and needed resources are contained in the [satcomp-images](satcomp-images) directory.

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

On repeated image builds, previously-built images with the same name will be left with the name/tag as `<none>/<none>`. All docker dangling images can be deleted with `docker image prune`. A specific image can be deleted by running `docker rmi <IMAGE ID>`. 

Note that you can delete all docker images on your machine by running `docker rmi -f $(docker images -a -q)`. Be careful: only do this after running `docker images` to check that you won't delete images unrelated to the solver competition. 

## Building Mallob Images

*Note*: Although this repository is released under the MIT-0 license, the Dockerfiles use the Mallob project. Mallob licenses include the [LGPL 3.0](https://opensource.org/licenses/lgpl-3.0.html) license.

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

To run parallel Mallob, cd into the `runner` directory. We have created a simple shell script called `run_parallel.sh` to show you how to run the mallob_parallel docker image to create a running container. The script has several variables that you can configure:

- `DOCKER_NETWORK`. Name of the docker bridge network, `mallob-test` for this example.
- `HOST_RUNDIR`. Name of the host directory that will be mounted in the docker run directory. This should be an absolute pathname. Note that this enables you to persist the run directory over multiple docker container sessions. It is also the location where the docker solver will write results. If you use the example from the repo, this should be the absolute pathname to the `experiment` directory.

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

Again, note that this directory is mounted of the host run directory as specified by the script variable `HOST_RUNDIR`. These files will persist on the host.

At this point, you can perform additional experiments or exit the docker shell.

The competition infrastructure starts solver containers and keeps them running for multiple queries. Each query will have a new `input.json` file, and `/container/solver` will be run again.

Your debugging should ensure that you don't leave extra processes running. Check for orphaned jobs with `ps -ax`. In addition, if you create temporary in the container, ensure they are cleaned up.

If your solver doesn't run correctly in the docker container, you can remove the `/container/solver` commands from the `init_mallob.sh` files. Once you are dropped into the docker container's bash shell, you can explore and debug directly, including running `/container/solver /rundir` from the container shell command line.
