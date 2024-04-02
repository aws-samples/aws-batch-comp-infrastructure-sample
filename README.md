# SAT-Comp and SMT-Comp Parallel and Cloud Track Instructions

Welcome to [SAT-comp](https://satcompetition.github.io/2024/) and [SMT-Comp 2024](https://smt-comp.github.io/2024/)!

This repository will help you get your parallel or distributed solver running on AWS. You will first build docker containers with your solver and then connect them to the AWS infrastructure.

We recommend that you work in four steps:

1. Create and configure an AWS Account for the competition (instructions below).  Please do this right away and send us an email, so we can start the process to give you AWS credits.  You can then continue with step 2 while waiting for us to answer. 
2. Build your solver as a Docker image and run experiments locally. See the [Solver Development README](docker/README-Solver-Development.md).
3. Set up AWS infrastructure and test your solver on the cloud. See the [Infrastructure README](infrastructure/README-Infrastructure.md)
4. When ready, share the solver repository and Docker image with us.

## Creating an AWS Account

First, create a specific AWS account for competition use. You can use the same account used in previous years. If you have not created an AWS account previously, it is straightforward to do, requiring a cell phone number, credit card, and address. Make sure to register your account with an institutional email address (and not a private one), otherwise AWS cannot sponsor your account. To create an account, navigate to [aws.amazon.com](https://aws.amazon.com) and follow the instructions.

If you have previously created an AWS account for other purposes, we strongly advise that you create a separate AWS account for managing your SAT/SMTComp tool construction and testing. This makes it much easier for us to manage account credits and billing. Once the new account is created, email us the account number at: sat-comp@amazon.com (for SAT-Comp) or aws-smtcomp-2024@googlegroups.com (for SMT-Comp) and we will apply the appropriate credits to your account.

To find your account ID, click on your account name in the top right corner, and then click "My Account". You should see Account ID in the Account Settings

It is important that you tell us your account number immediately after creating the account, so that we can assign you a resource budget for your experiments. We also need to grant you access to the shared problem sets. Once we hear from you, we will email you an acknowledgment when resources have been added to your account.  

## Building Your Solver

Next, it is time to develop your solver!  All of the development and most of the testing can be performed on a local laptop, so it is not necessary to wait for AWS credits to get started.  Please see the instructions in the [Solver Development README](docker/README-Solver-Development.md) on how to start building and testing your solver.

## For Returning Competitors:
You should find the developer experience similar to 2023. We will note any changes here.

## Additional Resources: Analysis Problems

You can find SAT problems from recent competitions here:
- [2020](https://satcompetition.github.io/2020/downloads.html)
- [2021](https://satcompetition.github.io/2021/downloads.html)
- [2022](https://satcompetition.github.io/2022/downloads.html)
- [2023](https://satcompetition.github.io/2023/downloads.html)
    
You can find SMT problems from recent competitions here:
- [2020](https://smt-comp.github.io/2020/benchmarks.html)
- [2021](https://smt-comp.github.io/2021/benchmarks.html)
- [2022](https://smt-comp.github.io/2022/benchmarks.html)
- [2023](https://smt-comp.github.io/2023/benchmarks.html)


## Additional Resources: Previous Entrants

Here are the github repositories for the 2023 solvers. You may find these useful as you connect your solver to the AWS cloud infrastructure.

SAT-Comp Parallel: 
* [DPS](https://github.com/nabesima/DPS-satcomp2023)
* [Gimsatul](https://github.com/arminbiere/gimsatul/tree/master/aws/sc2023)
* [Mallob-1](https://github.com/domschrei/aws-batch-comp-infrastructure-sample/tree/mallob23-parallel-1)
* [Mallob-2](https://github.com/domschrei/aws-batch-comp-infrastructure-sample/tree/mallob23-parallel-2)
* [Mallob-lin](https://github.com/solimul/mallob-lin)
* [MergeSAT](https://github.com/conp-solutions/mergesat/tree/master/tools/aws_docker)
* [MergeSAT-Pcasso](https://github.com/conp-solutions/mergesat/tree/v4.0-rc4-pcasso)
* [NPS](https://github.com/nabesima/DPS-satcomp2023/tree/non-det)
* [Pahkis23](https://github.com/KTRDeveloper/Pahkis23)
* [PakisInc23](https://github.com/KTRDeveloper/PakisInc23)
* [pDisKS-step (dead link)](https://github.com/sat-team-2023/pKisDS)
* [pKisDS (dead link)](https://github.com/sat-team-2023/pKisDS)
* [PKISSAT-RS-2G](https://github.com/vvallade/painless-sat-competition-2023/tree/main)
* [PKISSAT-RS-STR](https://github.com/vvallade/painless-sat-competition-2023/tree/str)
* [PRS-sc23](https://github.com/shaowei-cai-group/PRS-sc23/tree/PRS-sc23)
* [PRS-nopre-sc23](https://github.com/shaowei-cai-group/PRS-sc23/tree/PRS-nopre-sc23)

SAT-Comp Cloud:
* [Mallob](https://github.com/domschrei/aws-batch-comp-infrastructure-sample/tree/mallob23-cloud)
* [Mallob-lin](https://github.com/solimul/mallob-lin)
* [PRS-distributed-sc23](https://github.com/shaowei-cai-group/PRS-sc23/tree/PRS-distributed-sc23)


SMT-Comp Parallel:
* [Vampire-parallel](https://github.com/vprover/vampire/tree/smtcomp23/dockers)
* [z3-owl](https://github.com/ZJU-Automated-Reasoning-Group/arlib)

SMT-Comp Cloud:
* [cvc5-cloud](https://github.com/amaleewilson/smtcomp23)
* [Vampire-cloud](https://github.com/vprover/vampire/tree/smtcomp23/dockers)


<!---
### 2022

SAT-Comp Parallel: 
* [DPS-Kissat](https://github.com/nabesima/DPS-satcomp2022)
* [gimsatul](https://github.com/arminbiere/gimsatul)
* [Mallob-ki](https://github.com/domschrei/isc22-mallob/tree/ki)
* [NPS-Kissat](https://github.com/nabesima/DPS-satcomp2022/tree/non-det)
* [P-Kissat](https://github.com/vvallade/painless-sat-competition-2022/tree/pkissat)
* [P-MCOMSPS](https://github.com/vvallade/painless-sat-competition-2022)
* [ParKissat-RS](https://github.com/mww-aws/ParKissat/tree/RS)
* [PaKis22](https://github.com/KTRDeveloper/PaKis22)
* [PaKisMAB22](https://github.com/KTRDeveloper/PaKisMAB22)

SAT-Comp Cloud:
* [Mallob-kicaliglu](https://github.com/domschrei/isc22-mallob/tree/kicaliglu)
* [Paracooba](https://github.com/maximaximal/paracooba-satcomp22)

SMT-Comp Parallel:
* [SMTS Cube and Conquer](https://github.com/usi-verification-and-security/aws-smts/tree/parallel-cube-and-conquer-fixed)
* [SMTS Portfolio](https://github.com/usi-verification-and-security/aws-smts/tree/parallel-portfolio)
* [Vampire](https://github.com/vprover/vampire/tree/smtcomp22)

SMT-Comp Cloud:
* [cvc5-cloud](https://github.com/amaleewilson/aws-satcomp-solver-sample/tree/cvc5)
* [SMTS Cube and Conquer](https://github.com/usi-verification-and-security/aws-smts/tree/cloud-cube-and-conquer-fixed)
* [SMTS Portfolio](https://github.com/usi-verification-and-security/aws-smts/tree/cloud-portfolio)
* [Vampire](https://github.com/vprover/vampire/tree/smtcomp22)

-->

## FAQ

#### Q. I already created my AWS account with a non-institutional email address. Can I change the email address tied to my account?

Yes. To change your email address, follow the instructions at https://repost.aws/knowledge-center/change-email-address.
