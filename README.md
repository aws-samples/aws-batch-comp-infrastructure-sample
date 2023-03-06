# SAT-Comp and SMT-Comp Cloud Track Instructions

This repository will help you get your parallel or distributed solver running efficiently on AWS.  You will build docker containers with your solver and then connect them to the AWS infrastructure.

We recommend that you work in four steps:

1. Create and configure an AWS Account for the competition.  Please do this right away and send us an email, so we can start the process to give you AWS credits.  You can then continue with step 2 while waiting for us to answer. 
2. Build your solver as a Docker image and run experiments locally.
3. Set up AWS infrastructure and test your solver on the cloud.
4. When ready, share the solver repository and Docker image with us.

We describe step 1 in this document.  Step 2 is described in the [Solver Development README](docker/README-Solver-Development.md), while steps 3 and 4 are described in the [Infrastructure README](infrastructure/README-Infrastructure.md). 


## Creating an AWS Account

First, create a specific AWS account for the competition. If you have not created an AWS account previously, it is straightforward to do, requiring a cell phone number, credit card, and address.  Navigate to [aws.amazon.com](https://aws.amazon.com) and follow the instructions to create an account.

If you have previously created an AWS account, we strongly advise that you create a separate AWS account for managing the SAT/SMT-Comp tool construction and testing. This makes it much easier for us to manage account credits and billing. Once the new account is created, email us the account number at: sat-comp@amazon.com (for SAT-Comp) or aws-smtcomp-2023@googlegroups.com (for SMT-Comp) and we will apply the appropriate credits to your account.

To find your account ID, click on your account name in the top right corner, and then click "My Account". You should see Account ID in the Account Settings

It is important that you tell us your account number immediately after creating the account, so that we can assign you a resource budget for your experiments. We also need to grant you access to the shared problem sets. Once we hear from you, we will email you an acknowledgment when resources have been added to your account.  

## Building Your Solver

Next, it is time to develop your solver!  All of the development and most of the testing can be performed on a local laptop, so it is not necessary to wait for AWS credits to get started.  Please look at the instructions in the [Solver Development README](docker/README-Solver-Development.md) on how to start building and testing your solver.

## Additional Resources: Analysis Problems

The SAT problems for the SAT-Comp 2022 competition are available [here](https://satcompetition.github.io/2022/downloads.html).  The SMT problems for SMT-Comp 2022 competition are available [here](https://smt-comp.github.io/2022/benchmarks.html).

## Additional Resources: Solvers

Here are github repositories for the solvers from the 2022 competitions: 

SAT-Comp Parallel: 
* [ParKissat-RS](https://github.com/mww-aws/ParKissat/tree/RS)
* [ParKissat-PRE](https://github.com/mww-aws/ParKissat/tree/PRE)
* [PaKis22](https://github.com/KTRDeveloper/PaKis22)
* [PaKisMAB22](https://github.com/KTRDeveloper/PaKisMAB22)
* [DPS-Kissat](https://github.com/nabesima/DPS-satcomp2022)
* [NPS-Kissat](https://github.com/nabesima/DPS-satcomp2022/tree/non-det)
* [P-Kissat](https://github.com/vvallade/painless-sat-competition-2022/tree/pkissat)
* [P-MCOMSPS](https://github.com/vvallade/painless-sat-competition-2022)
* [Mallob-ki](https://github.com/domschrei/isc22-mallob/tree/ki)
* [gimsatul](https://github.com/arminbiere/gimsatul)

SAT-Comp Cloud:
* [Paracooba](https://github.com/maximaximal/paracooba-satcomp22)
* [Mallob-kicaliglu](https://github.com/domschrei/isc22-mallob/tree/kicaliglu)

SMT-Comp Parallel:
* [SMTS Cube and Conquer](https://github.com/usi-verification-and-security/aws-smts/tree/parallel-cube-and-conquer-fixed)
* [SMTS Portfolio](https://github.com/usi-verification-and-security/aws-smts/tree/parallel-portfolio)
* [Vampire](https://github.com/vprover/vampire/tree/smtcomp22)

SMT-Comp Cloud:
* [cvc5-cloud](https://github.com/amaleewilson/aws-satcomp-solver-sample/tree/cvc5)
* [SMTS Cube and Conquer](https://github.com/usi-verification-and-security/aws-smts/tree/cloud-cube-and-conquer-fixed)
* [SMTS Portfolio](https://github.com/usi-verification-and-security/aws-smts/tree/cloud-portfolio)
* [Vampire](https://github.com/vprover/vampire/tree/smtcomp22)
