# SAT-Comp and SMT-Comp Cloud Track Instructions

This repository will help you get your parallel or distributed solver running efficiently on AWS.  You will build docker containers with your solver and then connect them to the AWS infrastructure.

Last year, we received feedback that it was challenging to debug solvers on AWS.  This year, we provide guidance and scripts to enable debugging your parallel and distributed solvers locally prior to running at larger scale on AWS resources. This will enable you to get solvers running in a stable way before uploading to AWS, which should reduce the overhead of preparing your solver for submission.

We recommend that you work in four steps:

1. Create and configure an AWS Account for the competition
2. Create your own solver and run experiments
3. Set up AWS infrastructure to run on the cloud
4. When ready, share the solver repository and Docker image with us

We describe step 1 in this document.  Step 2 is described in the [Solver Development README](docker/README-Solver-Development.md), while steps 3 and 4 are described in the [Infrastructure README](infrastructure/README-Infrastructure.md). 


## Prerequisites

To build and run solvers, you will need the following tools installed:

- [python3](https://www.python.org/).  To install the latest version for your platform, go to the [downloads](https://www.python.org/downloads/) page.
- [docker](https://www.docker.com/).  There is a button to download Docker Desktop on the main page.
- [boto3](https://aws.amazon.com/sdk-for-python/).  Once you have python3 installed (above), you can install this with `pip3 install boto3`. 

Basic knowledge of AWS accounts and services is helpful, but we will walk you through all of the necessary steps. 

We recommend that your development environment be hosted on Amazon Linux 2 (AL2) or Ubuntu 20. Other platforms may work, but have not been tested. Note that Mallob (our example solver) will not build cleanly on Mac OS running M1 and M2 processors, even when building within a Docker container, due to missing FPU flags.

## Creating an AWS Account

First, create a specific AWS account for the competition. If you have not created an AWS account previously, it is straightforward to do, requiring a cell phone number, credit card, and address.  Navigate to [aws.amazon.com](https://aws.amazon.com) and follow the instructions to create an account.

If you have previously created an AWS account, we strongly advise that you create a separate AWS account for managing the SAT/SMT-Comp tool construction and testing. This makes it much easier for us to manage account credits and billing. Once the new account is created, email us the account number at: sat-comp-2023@amazon.com (for SAT-Comp) or aws-smtcomp-2023@googlegroups.com (for SMT-Comp) and we will apply the appropriate credits to your account.

To find your account ID, click on your account name in the top right corner, and then click "My Account". You should see Account ID in the Account Settings

It is important that you tell us your account number immediately after creating the account, so that we can assign you a resource budget for your experiments. We also need to grant you access to the shared problem sets. Once we hear from you, we will email you an acknowledgment when resources have been added to your account.  

_Note_: If you choose to use an existing AWS account (_not_ recommended), you should create a competition-specific profile, for example `sc-2023`. Instead of using `default` in the `.aws/credentials` file below, you would use `sc-2023` as a profile name.  You would then include `--profile sc-2023` with every AWS command in this README.

Next, it is time to develop your solver!  Please look at the instructions in the [Solver Development README](docker/README-Solver-Development.md) on how to start building and testing your solver.
