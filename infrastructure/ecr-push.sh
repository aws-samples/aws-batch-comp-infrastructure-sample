# /bin/bash

print_args() {
    echo "usage: ecr-push.sh -p PROFILE -j PROJECT -l LEADER [-h] [-w WORKER]"
    echo " "
    echo "required arguments:"
    echo "optional arguments:"
    echo "  -h, --help               show this message and exit"
    echo "  -p, --profile PROFILE    AWS profile"
    echo "  -j, --project PROJECT    Name of the project"
    echo "  -a. --account ACCOUNT    Account number"
    echo "  -r, --region REGION      Region"
    echo "  -l, --leader LEADER      Name of the leader local docker image"
    echo "  -w, --worker WORKER      Name of the worker local docker image"
}

POSITIONAL_ARGS=()

if [ $# -lt 4 ]; 
then
    print_args
    exit 1;
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
      echo ""
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

echo "Leader is: " $LEADER
echo "Worker is: " $WORKER
echo "Project is: " $PROJECT
echo "Profile is: " $PROFILE

if [ -z ${PROJECT+x} ] || [ -z ${PROFILE+x} ] || [ -z ${ACCOUNT+x} ] || [ -z ${REGION+x} ] ;
then 
    echo "account, region, project and profile are all required arguments"
    exit 1; 
fi

aws --profile $PROFILE --region $REGION ecr get-login-password  | docker login --username AWS --password-stdin "$ACCOUNT".dkr.ecr."$REGION".amazonaws.com

if [ -z ${WORKER+x} ];
then 
    echo "No worker set";
else
    echo docker tag "$WORKER" "$ACCOUNT".dkr.ecr."$REGION".amazonaws.com/"$PROJECT"-worker
    echo docker push "$ACCOUNT".dkr.ecr."$REGION".amazonaws.com/"$PROJECT"-worker
fi

if [ -z ${LEADER+x} ];
then 
    echo "No leader set";
else
    echo docker tag "$LEADER" "$ACCOUNT".dkr.ecr."$REGION".amazonaws.com/"$PROJECT"-leader
    echo docker push "$ACCOUNT".dkr.ecr."$REGION".amazonaws.com/"$PROJECT"-leader
fi


# aws --profile mww ecr get-login-password  | docker login --username AWS --password-stdin 834251193136.dkr.ecr.us-east-1.amazonaws.com

# docker tag $1:leader 269085374600.dkr.ecr.us-east-1.amazonaws.com/$1:leader
# docker push 269085374600.dkr.ecr.us-east-1.amazonaws.com/$1:leader
# docker tag $1:leader 834251193136.dkr.ecr.us-east-1.amazonaws.com/$1:leader
# docker push 834251193136.dkr.ecr.us-east-1.amazonaws.com/$1:leader
