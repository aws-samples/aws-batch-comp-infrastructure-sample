#!/usr/bin/env bash

set -x

if [ $# -ne 6 ] ; then
    echo "USAGE: "
    echo "build-solver-pipeline-github.sh PROFILE PROJECT_NAME GITHUB_TOKEN REPOSITORY_OWNER REPOSITORY_NAME REPOSITORY_BRANCH_NAME"
    echo "where: "
    echo "   PROFILE is a AWS CLI profile with administrator access to the account"
    echo "   PROJECT_NAME is the name of the project.  MUST BE ALL LOWERCASE. Regular expression for names is: "
    echo "       (?:[a-z0-9]+(?:[._-][a-z0-9]+)*/)*[a-z0-9]+(?:[._-][a-z0-9]+)*"
    echo "   GITHUB_TOKEN is a GITHUB OAuth token that can clone public repositories"
    echo "   REPOSITORY_OWNER is the owner of the repository"
    echo "   REPOSITORY_NAME is the name of the repository"
    echo "   REPOSITORY_BRANCH_NAME is the branch of the repository to use "
    exit 1
fi

PROFILE=$1
PROJECT=$2
TOKEN=$3
OWNER=$4
REPONAME=$5
BRANCH=$6

if [[ $PROJECT =~ [A-Z] ]]
then
  echo "ERROR profile name has uppercase letters"
fi

aws --profile $PROFILE cloudformation create-stack --stack-name build-$PROJECT \
--template-body file://build-solver-pipeline-github.yaml --capabilities CAPABILITY_IAM \
--parameters \
  ParameterKey=ProjectName,ParameterValue=$PROJECT \
  ParameterKey=GitHubToken,ParameterValue=$TOKEN \
  ParameterKey=RepositoryOwner,ParameterValue=$OWNER \
  ParameterKey=RepositoryName,ParameterValue=$REPONAME \
  ParameterKey=RepositoryBranchName,ParameterValue=$BRANCH
