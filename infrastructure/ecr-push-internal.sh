#!/bin/bash

print_args() {
    echo "usage: ecr-push-internal.sh -p PROFILE -j PROJECT -a ACCOUNT -r REGION -l LEADER [-h] [-w WORKER]"
    echo " "
    echo "required arguments:"
    echo "  -j, --project PROJECT    Name of the project"
    echo "  -a. --account ACCOUNT    Account number"
    echo "  -r, --region REGION      Region"
    echo "optional arguments:"
    echo "  -p, --profile PROFILE    AWS profile"
    echo "  -h, --help               show this message and exit"
    echo "  -l, --leader LEADER      Name of the leader local docker image"
    echo "  -w, --worker WORKER      Name of the worker local docker image"
}

failure() {
  echo "Failure: $2"
  exit $1
}

POSITIONAL_ARGS=()

if [ $# -lt 4 ]; 
then
    echo "args: $*"
    echo "arg count: $#"
    print_args
    exit -1;
fi

while [[ $# -gt 0 ]]; do
  case $1 in
    -l|--leader)
      LEADER="$2"
      shift # past argument
      shift # past value
      ;;
    -w|--worker)
      WORKER="$2"
      shift # past argument
      shift # past value
      ;;
    -p|--profile)
      PROFILE="$2"
      shift # past argument
      shift # past value
      ;;
    -j|--project)
      PROJECT="$2"
      shift
      shift
      ;;
    -a|--account)
      ACCOUNT="$2"
      shift
      shift
      ;;
    -r|--region)
      REGION="$2"
      shift
      shift
      ;;
    -h|--help)
      echo "ABOUT TO RUN HELP"
      print_args
      shift # past argument
      ;;
    -*|--*)
      echo "Unknown option $1"
      exit 1
      ;;
    *)
      echo "Unknown positional argument $1"
      exit 1
      ;;
  esac
done

# echo "Leader is: " $LEADER
# echo "Worker is: " $WORKER
# echo "Project is: " $PROJECT
# echo "Profile is: " $PROFILE

if [ -z ${PROJECT+x} ] || [ -z ${ACCOUNT+x} ] || [ -z ${REGION+x} ] ;
then 
    echo "account, region, project and profile are all required arguments"
    exit 1; 
fi

if [ -z ${PROFILE+x} ] ;
then
    echo "Profile not set.";
else
    PROFILE_ARG="--profile ${PROFILE}"
    echo "Profile arg is: $PROFILE_ARG";
fi

aws $PROFILE_ARG --region $REGION ecr get-login-password  | docker login --username AWS --password-stdin "$ACCOUNT".dkr.ecr."$REGION".amazonaws.com || failure 1 "Line ${LINENO}"

if [ -z ${LEADER+x} ];
then 
    echo "No leader set";
else
    docker tag "$LEADER" "$ACCOUNT".dkr.ecr."$REGION".amazonaws.com/"$PROJECT":leader || failure 2 "Line ${LINENO}"
    docker push "$ACCOUNT".dkr.ecr."$REGION".amazonaws.com/"$PROJECT":leader || failure 3 "Line ${LINENO}"
fi

if [ -z ${WORKER+x} ];
then 
    echo "No worker set";
else
    docker tag "$WORKER" "$ACCOUNT".dkr.ecr."$REGION".amazonaws.com/"$PROJECT":worker || failure 4 "Line ${LINENO}"
    docker push "$ACCOUNT".dkr.ecr."$REGION".amazonaws.com/"$PROJECT":worker || failure 5 "Line ${LINENO}"
fi
