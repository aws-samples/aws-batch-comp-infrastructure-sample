#!/usr/bin/env python3
import argparse
import logging
import boto3
from botocore.exceptions import ClientError, ProfileNotFound
import time
import re
import json
import sys

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Runner")
logger.setLevel(logging.INFO)


class STS: 
    def __init__(self, sts_client) -> None:
        self.sts = sts_client

    def get_account_number(self) -> str: 
        try: 
            return self.sts.get_caller_identity()["Account"]
        except Exception as e:
            logger.error(f"Failed to get profile account number: {e}")
            raise e

class ECR: 
    def __init__(self, ecr_client) -> None:
        self.ecr = ecr_client

    def delete_repository_images(self, repository_name) -> None:
        try: 
            images = self.ecr.list_images(
                repositoryName=repository_name
            )
            if images["imageIds"]:  
                self.ecr.batch_delete_image(
                    repositoryName=repository_name,
                    imageIds=images["imageIds"]
                )    
        except self.ecr.exceptions.RepositoryNotFoundException as e: 
            logger.info(f"Repository {repository_name} not found (already deleted).  Error: {e}")
        except Exception as e:
            logger.error(f"Failed to delete repository images: {e}")
            raise e

    def delete_project_repositories(self, project_name) -> None: 
        # These must be kept synchronized with Cfn.
        repository_name = project_name
        self.delete_repository_images(repository_name)


class S3Filesystem:
    def __init__(self, s3_client) -> None:
        self.s3 = s3_client

    def delete_bucket(self, bucket_name) -> None:
        try:
            bucket = self.s3.Bucket(bucket_name)
            bucket.objects.all().delete()
            bucket.object_versions.delete()
            bucket.Policy().delete()
        except Exception as e:
            logger.error(f"Failed to delete all objects in bucket: {e}")
            raise e

    def upload_file_to_s3(self, bucket_name: str, file_name: str, object_name=None) -> None:
        """Upload a file to an S3 bucket

        :param file_name: File to upload
        :param bucket: Bucket to upload to
        :param object_name: S3 object name. If not specified then file_name is used
        :return: True if file was uploaded, else False
        """

        # If S3 object_name was not specified, use file_name
        if object_name is None:
            object_name = file_name

        # Upload the file
        try:
            bucket = self.s3.Bucket(bucket_name)
            bucket.upload_file(file_name, object_name)
        except ClientError as e:
            logging.error(f"Failed to upload file to s3: {e}")
            raise e

class SSM:
    def __init__(self, ssm_client) -> None:
        self.ssm = ssm_client

    # Get the recommended AMI.  
    # The instance AMI describes the 
    # [Amazon Machine Image](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/AMIs.html), 
    # the basic software image to be loaded onto each EC2 instance, that describes the 
    # operating system and other configuration information. 
    def get_ami_image(self) -> str: 
        try:
            result = self.ssm.get_parameters(
                Names=["/aws/service/ecs/optimized-ami/amazon-linux-2/recommended"])
            logger.debug(f"Result of get_parameters is {result}")
            result_value = json.loads(result["Parameters"][0]["Value"])
            image_id = result_value["image_id"]
            logger.info(f"Recommended image id: {image_id}")
            return result_value["image_id"]
        except Exception as e:
            logger.error(f"Failed to call ssm.get_parameters to find the recommended AMI for linux: {e}")
            raise e


class CloudFormation:
    def __init__(self, cfn_client, stack_name: str) -> None:
        self.stack_name = stack_name
        self.cfn = cfn_client

    def create_parameters(self, project_name, instance_type, ami_id, container_memory): 
        return [
            {
                'ParameterKey': "ProjectName",
                'ParameterValue': project_name
            },
            {
                'ParameterKey': "AvailZoneId",
                'ParameterValue': "a"
            },
            {
                'ParameterKey': "InstanceType",
                'ParameterValue': instance_type
            },
            {
                'ParameterKey': "AmiImageId",
                'ParameterValue': ami_id
            },
            {
                'ParameterKey': "ContainerMemory",
                'ParameterValue': str(container_memory)
            },
        ]

    def get_stack(self): 
        return self.cfn.Stack(self.stack_name)

    def create_cloudformation_stack(self, project_name, instance_type, ami_id, container_memory) -> None:
        try:
            cf_template = open('solver-infrastructure.yaml').read()
            response = self.cfn.create_stack(
                StackName=self.stack_name,
                TemplateBody=cf_template,
                Capabilities=["CAPABILITY_IAM"],
                Parameters=self.create_parameters(project_name, instance_type, ami_id, container_memory)
            )
        except self.cfn.exceptions.AlreadyExistsException as exists:
            logger.error("Stack already exists: perhaps it failed to properly create?  Try deleting it with delete-solver-infrastructure.")
            raise e
        except Exception as e:
            logger.error(f"Failed to create stack: {e}")
            raise e

    def delete_cloudformation_stack(self) -> None:
        try:
            stack = self.cfn.Stack(self.stack_name)
            stack.delete()
        except Exception as e:
            logger.error(f"Failed to delete stack: {e}")
            raise e

    def update_cloudformation_stack(self, project_name, instance_type, ami_id, container_memory) -> None:
        try:
            cf_template = open('solver-infrastructure.yaml').read()
            stack = self.cfn.Stack(self.stack_name)
            response = stack.update(
                StackName=self.stack_name,
                TemplateBody=cf_template,
                Capabilities=["CAPABILITY_IAM"],
                Parameters=self.create_parameters(project_name, instance_type, ami_id, container_memory)
            )
        except Exception as e:
            logger.error(f"Failed to create stack: {e}")
            raise e

    def await_completion(self, mode) -> bool:
        while True:
            stack = self.get_stack()
            try: 
                status = stack.stack_status
            except Exception as e:
                logger.info(f"Stack {mode} operation in progress.  Cloudformation states stack is deleted.")
                return mode == 'delete'
            
            logger.info(f"Stack {mode} operation in progress.  Current status: {stack.stack_status}")

            if "IN_PROGRESS" in stack.stack_status:
                logger.info("Pausing 30 seconds")
                # Sleep time added to reduce cloudformation api calls to get status
                time.sleep(30)
            elif ("ROLLBACK" in stack.stack_status or
                "FAILED" in stack.stack_status):
                logger.info(f"Cloudformation operation {mode} failed!")
                return False
            elif "COMPLETE" in stack.stack_status:
                logger.info(f"Cloudformation operation {mode} succeeded!")
                return True
            else:
                logger.error(f"Unexpected cloudformation state {stack.stack_status}")
                raise Exception(f"Unexpected cloudformation state when awaiting completion: {stack.stack_status}")

def get_satcomp_bucket(account_number, region, project_name) -> str: 
    # needs to be synched with CloudFormation
    return str(account_number) + '-' + region + '-' + project_name

def delete_resources(session, s3, project_name, bucket) -> None: 
    # delete s3 bucket

    logger.info(f"Deleting S3 bucket {bucket}")
    s3_client = session.client('s3')

    try: 
        s3.delete_bucket(bucket)
    except s3_client.exceptions.NoSuchBucket as e:
        logger.info(f"No bucket {bucket} exists; perhaps it was already deleted.")

    # delete ecr instances
    ecr_client = session.client('ecr')
    ecr = ECR(ecr_client)
    logger.info(f"Deleting all images within ECR repository")
    ecr.delete_project_repositories(project_name)

def arg_parser() -> dict: 
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', required = False, help = "AWS profile (uses 'default' if not provided)")
    parser.add_argument('--project', required = False, default = 'comp24', help = "ADVANCED USERS ONLY: Name of the project (default: 'comp24').")
    parser.add_argument('--solver-type', required = True, choices = ('cloud', 'parallel'), help = "Either 'cloud' or 'parallel' depending on the desired configuration.")
    parser.add_argument('--mode', required = False, default = 'create', choices = ('create', 'update', 'delete'), help = "One of 'create', 'update', 'delete': create, update or delete the infrastructure.")
    # MWW: can add these back in for advanced users, but hiding for now.
    # parser.add_argument('--dryrun', type=bool, required = False, help = "Dry run ONLY.  Do not actually create resources.")
    # parser.add_argument('--instance', required = False, help = "EXPERTS ONLY: Override default machine instance type")
    # parser.add_argument('--ami', required = False, help = "EXPERTS ONLY: Override default instance AMI")
    # parser.add_argument('--memory', type=int, required = True, help = "EXPERTS ONLY: Override default max memory for container (61000 for cloud, 253000 for parallel)")
    
    args = parser.parse_args()

    # argument checking.    
    # matcher = re.compile(allowable_project_names_mask)
    if not re.match(r"^[a-z]([a-z\d\/_-])*$", args.project): 
        logger.error(f"Invalid project name '{args.project}'.")
        logger.error(f"Project names must start with a lowercase letter and can consist only of lowercase numbers, digits, '/', '_', or '-' characters.")
        sys.exit(-1)
    
    return args


def main() -> None: 
    args = arg_parser()

    if args.solver_type == "cloud":
        instance_type = 'm6i.4xlarge'
        memory = '61000'
    elif args.solver_type == "parallel":
        instance_type = 'm6i.16xlarge'
        memory = '253000'
    else:
        raise Exception('Solver type argument must be one of "cloud" or "parallel"')

    profile = args.profile
    #profile = "default"
    project_name = args.project

    stack_name = f"solver-infrastructure-{project_name}"
    
    #RBJ# 
    try:
        if profile:
            session = boto3.Session(profile_name=profile)
        else:
            session = boto3.Session() 
    except ProfileNotFound as e:
        logger.error(f"Unable to create AWS session.  Please check that default profile is set up in the ~/.aws/config file and has appropriate rights (or if --profile was provided, that this profile has appropriate rights)")
        sys.exit(1)
    
    
    if not session.region_name:
        logger.error(f"Profile does not have a region defined.  Please add a region (recommend: us-east-1) to profile '{profile}' in the ~/.aws/config file")
        sys.exit(1)

    try: 
        # link to AWS services
        ssm_client = session.client('ssm')
        ssm = SSM(ssm_client)

        sts_client = session.client('sts')
        sts = STS(sts_client)
        
        s3 = session.resource('s3')
        s3_file_system = S3Filesystem(s3)

        cloudformation = session.resource('cloudformation')
        cfn = CloudFormation(cloudformation, stack_name)

        # set up parameters
        account_number = sts.get_account_number()
        region = session.region_name
        ami_id = ssm.get_ami_image()
        satcomp_bucket = get_satcomp_bucket(account_number, region, project_name)

        # logger.info("Exiting early so as not to actually do anything")
        # return 

        if args.mode == "update":
            cfn.update_cloudformation_stack(project_name, instance_type, ami_id, memory)
            cfn.await_completion("update")
        elif args.mode == "delete":
            delete_resources(session, s3_file_system, project_name, satcomp_bucket)
            cfn.delete_cloudformation_stack()
            cfn.await_completion("delete")
        elif args.mode == "create":
            cfn.create_cloudformation_stack(project_name, instance_type, ami_id, memory)
            ok = cfn.await_completion("create")
            if ok:
                logger.info(f"Uploading test.cnf file to the {satcomp_bucket} bucket")
                s3_file_system.upload_file_to_s3(satcomp_bucket, "test.cnf")

        else:
            logger.error(f"Unexpected operation {args.mode}")
            raise Exception("Internal error: unexpected operation {args.mode}")
    except ClientError as ce: 
        logger.error("An error occurred during an AWS operation.  Usually this is caused by the AWS session having insufficient rights to resources.  Please double check that the default profile is properly set up in your AWS Config.")
        logger.error("Error description: {ce}")
        raise ce


if __name__ == "__main__":
    main()