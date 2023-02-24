# Configuring AWS Infrastructure for SAT/SMT-Comp

This README describes how to build and configure AWS infrastructure for the SAT and SMT parallel and cloud tracks. If you are only competing in the parallel track, a handful of the steps are unnecessary. We will point out these cloud-only steps as we go.

You will proceed through the following steps.

* [Prerequisites](#prerequisites)
* [Creating an AWS Account](#creating-an-aws-account)
* [Creating Solver Infrastructure](#creating-solver-infrastructure)
* [Preparing Docker Images](#preparing-docker-images)
* [Working with S3](#working-with-s3)
* [Running your Solver](#running-your-solver)

Additional resources are available in a FAQ:

* [FAQ/Troubleshooting](#faq--troubleshooting)

## Prerequisites

To install the infrastructure described in this document, you will need the following tools installed:

- [python3](https://www.python.org/)
- [docker](https://www.docker.com/)
- [awscli](https://aws.amazon.com/cli/)
- [boto3](https://aws.amazon.com/sdk-for-python/)

Basic knowledge of AWS accounts and services is helpful, but we will walk you through all of the necessary steps. 

We recommend that your development environment be hosted on Amazon Linux 2 (AL2) or Ubuntu 20. Other platforms may work, but have not been tested. Note that Mallob will not build cleanly on Mac OS running M1 and M2 processors, even when building within a Docker container, due to missing FPU flags.

## Creating an AWS Account

First, create a specific AWS account for the competition. If you have not created an AWS account previously, it is straightforward to do, requiring a cell phone number, credit card, and address.  Navigate to [aws.amazon.com](https://aws.amazon.com) and follow the instructions to create an account.

If you have previously created an AWS account, we strongly advise that you create a separate AWS account for managing the SAT/SMT-Comp tool construction and testing. This makes it much easier for us to manage account credits and billing. Once the new account is created, email us the account number at: sat-comp-2023@amazon.com (for SAT-Comp) or aws-smtcomp-2023@googlegroups.com (for SMT-Comp) and we will apply the appropriate credits to your account.

To find your account ID, click on your account name in the top right corner, and then click "My Account". You should see Account ID in the Account Settings

It is important that you tell us your account number immediately after creating the account, so that we can assign you a resource budget for your experiments. We also need to grant you access to the shared problem sets. Once we hear from you, we will email you an acknowledgment when resources have been added to your account.

_Note_: If you choose to use an existing AWS account (_not_ recommended), you should create a competition-specific profile, for example `sc-2023`. Instead of using `default` in the `.aws/credentials` file below, you would use `sc-2023` as a profile name.  You would then include `--profile sc-2023` with every AWS command in this README.

### Installing the AWS CLI

In order to work with AWS, you must install the [AWS CLI](https://aws.amazon.com/cli/) for your platform. To get started, follow the directions for your operating system here:
  [https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
If you have previously installed the AWS CLI, you should ensure it is up to date.

### Choose a Region 

AWS has many regions, which enables low-latency access for customers around the world. Each region is independent from all other regions, and in almost all cases, resources created in one region are not shared with other regions. In this document, we will work wtih `us-east-1`, which is the largest AWS region.  This is a good default choice, but you are welcome to use an alternate region. If you do, you should substitute the region that you have chosen whenever we use `us-east-1` as a parameter to commands in this README. If you are on the US West Coast, `us-west-2` is an ideal choice.

### Creating AWS Credentials

You must configure AWS credentials to access the resources in your account. For the purposes of simplifying the competition configurations, you will use a so-called _root level access key_. This is _not_ the best practice for security (which would be to create a separate user in your account) but it will suffice for the competition. If you continue using your AWS account after the competition, we recommend that you follow AWS best practices as described here:
    [https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html#create-iam-users](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html#create-iam-users)

In this section, you will be working with the Identity and Access Management (IAM) console. To create a root level access key go to the [IAM Console](https://console.aws.amazon.com/iamv2/). You can get to the console by clicking previous link or by searching for "IAM" in the search field at the top of the [AWS Console](https://console.aws.amazon.com) as shown [here](readme-images/iam-search.png) and then clicking the resulting link).

On IAM page, click "My Security Credentials" on the right side of the IAM console page as shown [here](readme-images/iam-quicklinks.png). Next, click on "Access keys (access key ID and secret access key)," then "Create New Access Key," and then "Show Access Key."
This will create an Access Key ID and a Secret Access Key. Copy these for use in the next step.

Next, on your local workstation, create a `~/.aws/credentials` file with the following information:

    [default]
    aws_access_key_id=ACCESS_KEY_ID
    aws_secret_access_key=SECRET_ACCESS_KEY
    region=us-east-1

`ACCESS_KEY_ID` and `SECRET_ACCESS_KEY` are the keys that you created in the previous step. 

After installing the AWS CLI and creating credentials, check your configuration by attempting to run an AWS command.  An example command that should work is:
```text
aws sts get-caller-identity
```

If you receive an error message, see the [FAQ/Troubleshooting](#faq--troubleshooting) section at the bottom of this document.

We recommend that when you've completed account set-up, you follow the steps in the FAQ [How Do I Track My Spending?](#how-do-i-track-my-spending) to track your spending. For now, we'll continue with the setup.

## Creating Solver Infrastructure

Next, you will create the AWS infrastructure necessary to build and test solvers. The SAT and SMT competitions both use the following infrastructure elements: 

* Compute resources necessary to host solvers, provided by the [Elastic Compute Cloud](https://aws.amazon.com/ec2/) (EC2) service.
* A registry for solver Docker image files, provided by the [Elastic Container Registry](https://aws.amazon.com/ecr/) (ECR) service.
* A compute environment to support automated launching of containers on compute resources, provided by the [Elastic Container Service](https://aws.amazon.com/ecs/) (ECS) service.  
* A storage location for solver queries that uses the [Simple Storage Service](https://aws.amazon.com/s3/) (S3) service.
* A distributed file system that can be used for communication between leader and worker solvers, using the [Elastic File System](https://aws.amazon.com/efs/) (EFS) service.
* A problem queue that the solver leader uses to extract the next problem to solve, provided by the [Simple Queue Service](https://aws.amazon.com/sqs/) (SQS).

We provide a script to set up all of these resources. You can click the links about for more specifics on each each of the services.  [RBJ: fix next sentence] We also explain how these services interact in more detail in the &quot;Extending the Competition Base Container&quot; section of this document. 

To set up your resouces, simply run the  `create-solver-infrastructure` script that we have provided:
```text
./create-solver-infrastructure --project PROJECT_NAME --solver-type SOLVER_TYPE
```

where:

* `PROJECT_NAME`: is the name of the project [RBJ: as chosen by the user for the life of the competition]. Note that `PROJECT_NAME` must start with a letter and can only contain lowercase letters, numbers, hyphens (-), underscores (_), and forward slashes (/).

* `SOLVER_TYPE`: is either `cloud` or `parallel` depending on which kind of solver you are running. Note that we will run cloud solvers run on multiple 16-core machines (m6i.4xlarge [RBJ: include links?]) with 64GB memory, while parallel solvers run on a single 64-core machine (m6i.16xlarge) with 256GB memory.

The script will take 5-10 minutes. When complete, all of the needed cloud resources should be created.  The script polls until the creation is complete.  

### Switching Between Cloud and Parallel Tracks

Once the infrastructure has been created, if you want to update it to switch between machine configurations for the cloud and parallel tracks, you can run the `update-solver-infrastructure` script: 

```text
./update-solver-infrastructure --project PROJECT_NAME --solver-type SOLVER_TYPE
```

This will change the instance type and memory configurations for the ECS images used. You can switch back and forth as needed.

### Deleting the infrastructure

If something goes wrong and you want to start over, simply run the `delete-solver-infrastructure` script:
```text
./delete-solver-infrastructure --project PROJECT_NAME 
```

This will delete the infrastructure and associated resources.  **Note that this deletion includes any files that have been uploaded to your S3 bucket and also any ECR docker images that you have created.** It will not delete your AWS account or security credentials.

## Preparing Docker Images

### Creating the Base Docker Leader and Worker Images for Solvers

See the [SAT-Comp Docker Images README.md file](../Docker/README.md) in the `docker` directory for instructions on how to build and test Docker images.

### Storing Solver Images in the ECR repository

Amazon stores your solver images in the [Elastic Container Registry (ECR)](https://console.aws.amazon.com/ecr).

The `create-solver-infrastructure` command described earlier creates an ECR repository with the same name as the project (PROJECT_NAME).

This repository will store the images for the leader and worker.  Once you have created and tested a docker image (or images, for the cloud leader and worker) as described in the [SAT-Comp Docker Images README.md file](../Docker/README.md), you can upload them to your AWS account with the `push-ecr` script:

```text
./push-ecr --project PROJECT_NAME [--leader LEADER_IMAGE_TAG] [--worker WORKER_IMAGE_TAG]
```

where:

* `PROJECT_NAME` is the name of the project that you used earlier when creating the account.

* `LEADER\_IMAGE\_TAG` is the tagged name of the leader docker image. [RBJ: fixme -- leader name and tag, tag is no longer "latest". These are names, not tags.]

* `WORKER\_IMAGE\_TAG` is the tagged name of the leader docker image. [RBJ: fixme -- same]

The leader and worker tags are optional; you can upload one or both docker images with this command (though if neither is specified, the script exits with an error).

## Working with S3

Before you can run the solver, you have to add the problems to be solved to an S3 bucket that is accessible by your account. As part of the `create-solver-infrastructure` CloudFormation script, we have created a bucket for you where you can store files: `ACCOUNT\_ID-us-east-1-PROJECT-NAME`, and added a `test.cnf` file to this bucket for testing (if you chose a different region than `us-east-1`, the part `us-east-1` in the bucket name will vary accordingly).  You can start with the `test.cnf` example and skip the rest of this section until you wish to add additional files or buckets for testing your solver.

You can copy files to the bucket with a command similar to this one (when executed from the root directory of this repository, this re-copies the `my-problem.cnf` file to the default bucket):

```text
aws s3 cp my-problem.cnf s3://ACCOUNT_ID-us-east-1-[PROJECT-NAME]
```

When `s3 cp` is compelte, you will see your file(s) in the list of objects in the bucket:

```text
aws s3 ls s3://ACCOUNT_ID-us-east-1-[PROJECT-NAME]
```

More information on creating and managing S3 buckets is found here: [https://aws.amazon.com/s3/](https://aws.amazon.com/s3/). The S3 command line interface is described in more detail here: [https://docs.aws.amazon.com/cli/latest/userguide/cli-services-s3-commands.html](https://docs.aws.amazon.com/cli/latest/userguide/cli-services-s3-commands.html).

## Running Your Solver

After storing docker images: `[PROJECT_NAME]:leader` (and for the cloud solver: `[PROJECT_NAME]:worker`) and placing at least one query file in your S3 bucket, you are ready to run your solver. [RBJ: these names are inconsistent?]

Running the solver consists of three steps:

1. Setup.

    a. Setting capacity for the cluster in [EC2](https://aws.amazon.com/ec2/).

    b. Setting the desired number of workers in [ECS](https://aws.amazon.com/ecs/).
    
2. Run. submitting a solve job to the SQS queue by specifying the S3 location of the problem and the desired number of workers.

3. Cleanup. Setting EC2 [RBJ: and ECS?] capacity for cluster back to zero.

After setup, you can run any number of solve jobs before cleaning up.

Note: It is very important that you [clean up](#cluster-teardown) once you are done. EC2 nodes that remain active continue to be charged against your account.

### Cluster Setup

To set up and tear down the cluster, we have provided a script called `update_instances`.  You provide the number of desired worker nodes as an argument. The script:
 
1. Creates an EC2 fleet large enough to run the experiment (number of workers + a leader node)
2. Creates the correct number of tasks in the ECS service for the leader and workers.

To run the script: 

```text
update_instances --option setup --workers [NUM_WORKERS]
```

where: 

* `NUM_WORKERS` is the number of worker nodes you want to allocate. To avoid  problems with possible resource limits for your AWS account, we recommend that you set `NUM_WORKERS` to `1` when working through this document for the first time. If you are building for the parallel track, set `NUM_WORKERS` to `0`, as all solving will be performed by the leader node.

AWS typically requires 2-5 minutes to allocate nodes and host the ECS cluster. You can monitor the creation process by navigating to the [ECS console](https://us-east-2.console.aws.amazon.com/ecs), and selecting select the SatCompCluster [RBJ: will this name potentially vary?] link.

The next page will show a list of job queues, including:

```text
job-queue-PROJECT_NAME-SolverLeaderService-...
job-queue-PROJECT_NAME-SolverWorkerService-...
```

The service is running and available when the number of running tasks for the leader is `1` and the number of running tasks for the Worker service is `n`, as chosen with `NUM_WORKERS` in the `update_instances` script above.

Note: Your AWS account is charged for the number of EC2 instances that you run, so your bill will rise with the number of workers that you allocate.  

### Job Submission and Execution

Before submitting a job, check that a cluster is set up and running, and the desired problem is available in an accessible S3 bucket.

Solver jobs are submitted by sending SQS messages. We have provided a `send_message` script to do this for you. You provide the S3 location of the file to run and number of desired worker nodes. The script submits an SQS request to the `[ACCOUNT_NUMBER]-[REGION]-SatCompQueue` queue, which the solver leader container is monitoring. 

To run the script: 

```text
send_message --location [S3_LOCATION] --workers [NUM_WORKERS]
```

where: 

* `LOCATION` is the S3 location of the query file. For example, for the bucket we described earlier, the location would be `S3://[ACCOUNT_ID]-us-east-1-satcompbucket/test.cnf`.
* `NUM_WORKERS` is the number of worker nodes to allocate for this problem. Again, we recommend that you start with `NUM_WORKERS` as `1` when beginning. For parallel solvers, you should set `NUM_WORKERS` to `0`.
* `TIMEOUT` is an optional parameter that sets the timeout in seconds for the solver.  Defaults to 60s.
* `NAME` is an optional parameter providing a name for the solver (in case you want to host multiple solvers within one container.  Defaults to the empty string)
* `FORMAT` is an optional parameter providing the problem format.  Defaults to the empty string.
* `ARGS` is an optional parameter allowing one or more arguments to be passed to the solver.  Defaults to the empty list. 

The leader container will pull the message off of the queue, fetch the problem from S3, and begin execution. For more information on the steps performed, see [Extending the Solver Base Container](#understanding-the-solver-architecture-and-extending-the-competition-base-leader-container) below.  

### Monitoring and Logging

The best way to see solver status is by examining the logs. These are available from CloudWatch log groups. There should be logs related to `/ecs/[PROJECT_NAME]-leader` and `/ecs/[PROJECT_NAME]-worker`.  These logs will capture both stdout and stderr from your solver containers.

The ECS console allows you to monitor the logs of all running tasks. You can learn more about the ECS console at: [https://aws.amazon.com/ecs/](https://aws.amazon.com/ecs/).


### Cluster Teardown

After testing, remember to tear down the cluster by running: 

```text
update_instances --option shutdown
```

This will terminate all EC2 instances and reset the number of leaders and workers to zero in the ECS service. 

You should verify that no EC2 instances are running after running the teardown script. Navigate to the [EC2 console](https://console.aws.amazon.com/ec2) and check the `Instances` tab.  There should be no running instances.  Note that it might take a minute or two for the instances to shut down after running the script.

Note: You are responsible for any charges made to your AWS account.  While we have tested the shutdown script and believe it to be robust, you are responsible for monitoring the EC2 cluster to make sure resources have shutdown properly. We have alternate directions to shutdown resources using the console in the Q&A section.


## FAQ / Troubleshooting

#### How Do I Track My Spending?

[AWS CloudFormation](https://aws.amazon.com/cloudformation/) can be used to automate many cloud configuration activities. The file `setup-account.yaml`[setup-account.yaml] in this repository is an optional CloudFormation script that can help you track your spending.  It sets up notification emails to be sent via  email when your account reaches 20%, 40%, 60%, 80%, 90%, 95%, and 100% of the monthly account budget. This will provide a window into the current spend rate for building and testing your solver.

Here is the command to run it:

    aws cloudformation create-stack --stack-name setup-account-stack --template-body file://setup-account.yaml --parameters ParameterKey=emailAddress,ParameterValue=[YOUR_EMAIL_ADDRESS]

_Note_: Be sure to double check the email address is correct! 

After running the aws cloudformation command, you can monitor the installation process by logging into your AWS account and navigating to the [CloudFormation console](https://console.aws.amazon.com/cloudformation).
Make sure you are in the region you chose in your profile (region is selected in the top right corner).
You should see a stack named `setup-account-stack`.

 ![](readme-images/cloudformation.png)
_Figure 1: Cloudformation result_

By clicking on this stack, and choosing `events`, you can see the resources associated with the stack.  After a short time, you should see the `CREATE_SUCCEEDED` event. If not (e.g., the email address was not valid email address syntax), you will see a `CREATE_FAILED` event. In this case, delete the stack and try again. If you have trouble, email us at: [sat-comp-2022@amazon.com](mailto:sat-comp-2022@amazon.com) and we will walk you through the process.

Although it is handy to get emails when certain account budget thresholds have been met, it is both useful and important to check by-the-minute account spending on the console: [https://console.aws.amazon.com/billing/home](https://console.aws.amazon.com/billing/home).

[RBJ: stopped here, except for minor formatting.]


#### Q: I'm only submitting to the parallel track and not the cloud track.  Do I need a worker image?

No. If you are submitting to the parallel track only, you do not need a worker image.  For the parallel track, we will assume that the leader manages all threading and communications within the single (multi-core) compute node.

#### Q: I ran the infrastructure scripts, and they seemed to work, but when I go out to the console, I don't see any of the infrastructure: S3 buckets, ECS Queues, etc. What happened?

The most common mistake people make when starting with AWS is not choosing the correct *region* for executing their jobs.  In the console on the top right there is a selectable region:

<img src="readme-images/regions.png" alt="image of region selector" width="200"/>

The reason that you view has to be the same as the one referenced in your profile created at the beginning of this document (by default, it is us-east-1).  Make sure that the region selected in the top-right of the console page matches the region in your profile. 

#### Q: I created a leader node and submitted a job, but the leader keeps saying it is waiting for worker nodes and not running my solver.  What happened?

There are two likely causes.  First it could be that you submitted an SQS that asked for more workers than you configured when you set up your cluster.  Make sure that the number of worker nodes equals or exceeds the number of worker nodes that were requested in the SQS message.  Second, if you just set up the ECS cluster, then it is likely that either the requested EC2 servers have not yet initialized, or that the ECS cluster has not yet started running on them.  It takes 2-5 minutes for the resources to become available after they are requested.

There is also a less-likely cause, involving capacity limits.  EC2 sets default capacity limits on the number of compute nodes that are available to an account.  If you are running large-scale tests, it may be that you have exceeded the default number of nodes.  To check, navigate to the EC2 console for the account, and click on "Limits" on the left side.  Type "All standard" in the search bar and determine the current limit.  The limit is specified in terms of vCPUs, so each m6i-4xlarge image uses 16 vCPUs, and every m6i-16xlarge uses 64 CPUs.  If you need additional vCPUs, click on the "All Standard" link and request a limit increase.  **N.B.** Running a large cluster can become expensive.  Make sure you limit your large-scale testing to preserve your AWS credits.

#### Q: I'm watching the ECS cluster, but nothing is happening; no nodes are being created.  What happened?

This can happen if you try to start up a cloud solver when the infrastructure is configured for parallel execution or vice versa.  In this case, the machine image where you want to deploy does not match the requirements of the ECS task.  Make sure that if you are running a cloud solver, you have not configured the infrastructure for parallel.  If you are unsure, you can always run `update-solver-infrastructure` with the expected type.  If the infrastructure is already set up for this type, it will be a no-op.


#### Q: Suppose I want to use the console to setup my ECS clusters, or to monitor them.  How do I do that?

__Step 1:__  Update the size of the EC2 cluster using the EC2 console

To control the instances in your cluster, go to the EC2 console and scroll down on the left side of the console and click on the link that says "Auto Scaling Groups".

In the next page, you will see an autoscaling group called something like `job-queue-PROJECT_NAME-EcsInstance`.

1. Select the queue by clicking on it, then click the "Edit" button in the "Group details" section.
1. Set the desired, and maximum task capacity to n (where n includes 1 leader and n-1 workers, so there is a minimum useful size of 2), and click "Update".

__Step 2:__ Update the size of the ECS task pool for the leader and workers

Navigate to the ECS console, then select the SatCompCluster link.

The next page should show a list of job queues, including:

```text
job-queue-PROJECT_NAME-SolverLeaderService-...
job-queue-PROJECT_NAME-SolverworkerService-...
```

Click on the SolverLeaderService job queue and choose "Update".  Set the number of tasks to 1, then choose "Skip to review", then click "Update Service".  You should then navigate back to the SatCompCluster link and click on the SolverWorkerService link.  Choose "Update" and set the number of tasks to n-1, where 'n' is the number of EC2 nodes you created in Setup Step 1.

Please allow 2-3 minutes for the instances to boot up and register with the cluster.  When registered, you should see 1 desired and 1 running task for the leader and n-1 desired tasks for the worker in the SatCompCluster screen.

If you get the following error, it means that your instances have not yet booted up:

```text
An error occurred (InvalidParameterException) when calling the RunTask operation: No Container Instances were found in your cluster.
```

If they fail to boot up after 5 minutes, please verify that both Desired Capacity and Maximum Capacity are set correctly.

You incur costs for the time the machines are running. [RBJ: allocated?]

#### Q: Suppose I want to use the console to tear down my ECS clusters.  How do I do that?

To control the instances in your cluster, go to the EC2 console and scroll down on the left side of the console and click on the link that says "Auto Scaling Groups".
 
In the next page, you will see an autoscaling group called something like job-queue-PROJECT_NAME-EcsInstance.
 
1. Select the queue by clicking on it, then click the "Edit" button in the "Group details" section.
1. Set the desired and maximum task capacity to 0.  This shuts down any EC2 instances.
 

#### Q: Suppose I want to use the console to send SQS messages to start executing jobs. How do I do that?

Submit a job using the [Simple Queue Service (SQS) console](https://console.aws.amazon.com/sqs/).

1. Navigate to the SQS console, and select the queue named `ACCOUNT_NUMBER-REGION-SatCompQueue`.
2. Click the *SendAndReceiveMessages* button
3. Set the message body to something matching the following structure:

```text
{"s3_uri":"s3://[PATH TO CNF PROBLEM]",
 "num_workers": [DESIRED NUMBER OF WORKERS]}
```

For example, for the bucket we described earlier, given a cluster with two nodes (one worker), it would be:

```text
{"s3_uri":"s3://ACCOUNT_ID-us-east-1-satcompbucket/test.cnf",
"num_workers": 1}
```

#### Q: What if I want to create different buckets other than the one provided for storing problems in?

In case you wish to create a different bucket, here is a command to create a bucket named `PROJECT_NAME-satcomp-examples`:

```text
aws s3api create-bucket --bucket PROJECT_NAME-satcomp-examples
```

Notes: 
 
 - This will create the bucket in the AWS region specified in your named profile

- If you chose a different region than `us-east-1`, you might get an `IllegalLocationConstraintException`. To deal with the problem, you have to append the argument `--create-bucket-configuration {"LocationConstraint": "YOUR-REGION-NAME"}` to the command, where `YOUR-REGION-NAME` is replaced with the name of the region you chose.

- S3 buckets are globally unique across all of AWS, which means that the command will fail if someone else is already using the same bucket name.  A simple fix is to add the AWS account number to the bucket name, which will likely yield a unique bucket name.

#### Q: I'd like to know more about how the Elastic Container Registry works.  Can I do the steps to upload files by hand?

Amazon stores your solver images in the [Elastic Container Registry (ECR)](https://console.aws.amazon.com/ecr).

The `create-solver-infrastructure` command described earlier creates two ECR repositories:

```text
PROJECT_NAME-leader
PROJECT_NAME-worker
```

These repositories store the images for the leader and worker.  

Each of these repositories has an associated URI (shown on the console page), which is what we use to push docker images to ECR.
The format for URIs is

```text
[AWS_ACCOUNT_ID].dkr.ecr.[REGION_NAME].amazonaws.com/[REPOSITORY_NAME]
```

You will use these URIs to describe where to store our Docker images in AWS.  

Note: a good way to make sure that you type these URI names correctly is to navigate to the Elastic Container Registry (ECR) console in AWS and copy them from the page (the names are in the URI column).   


To store a Docker image in ECR from your local machine, first you need to login to ECR:

```text
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin [AWS_ACCOUNT_ID].dkr.ecr.us-east-1.amazonaws.com
```

Next, you need to tag the image to match the ECR repository.  For the worker, tag the image as:

```text
docker tag [LOCAL_WORKER_IMAGE_ID] [AWS_ACCOUNT_ID].dkr.ecr.us-east-1.amazonaws.com/[PROJECT\_NAME]-worker
```

where 

* **LOCAL\_WORKER\_IMAGE\_ID** is the local worker image tag (e.g., `my-solver:leader`).  For the sample solver, this image tag is described in the `README.md` instructions.  
* **AWS\_ACCOUNT\_ID** is the account ID where you want to store the image.
* **PROJECT\_NAME** is the name of the project that you chose in the &quot;Creating the AWS Infrastructure&quot; section above.

For the leader, tag the image as:

```text
docker tag [LOCAL_LEADER_IMAGE_ID] [AWS_ACCOUNT_ID].dkr.ecr.us-east-1.amazonaws.com/PROJECT_NAME-leader
```

where 

* **LOCAL\_LEADER\_IMAGE\_ID** is the local image for the leader, and the other parameters are the same as for the worker.

After these steps, you can docker push the images:

```text
docker push [AWS_ACCOUNT_ID].dkr.ecr.us-east-1.amazonaws.com/PROJECT_NAME-leader
docker push [AWS_ACCOUNT_ID].dkr.ecr.us-east-1.amazonaws.com/PROJECT_NAME-worker
```

You should see network progress bars for both images.

More information related to the ECR procedures is described here: [https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-push-ecr-image.html](https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-push-ecr-image.html).

If you have trouble, please email us at: [sat-comp-2023@amazon.com](mailto:sat-comp-2023@amazon.com) and we will walk you through the process.
