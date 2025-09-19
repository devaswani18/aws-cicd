import boto3
import json

def get_secret(secret_name, region_name):
    """Retrieves a secret from AWS Secrets Manager (supports plain text or JSON)."""
    client = boto3.client('secretsmanager', region_name=region_name)
    try:
        response = client.get_secret_value(SecretId=secret_name)
        if 'SecretString' in response:
            secret = response['SecretString']
            try:
                # Case 1: JSON { "github_token": "xxx" }
                return json.loads(secret).get('github_token', secret)
            except json.JSONDecodeError:
                # Case 2: Plain text "xxx"
                return secret
        else:
            return response['SecretBinary']
    except Exception as e:
        print(f"❌ Error retrieving secret '{secret_name}': {e}")
        return None

def ensure_codebuild_role(role_name):
    """Ensures a CodeBuild service role exists with trust policy and permissions."""
    iam = boto3.client('iam')
    try:
        role = iam.get_role(RoleName=role_name)
        print(f"✅ IAM Role '{role_name}' already exists.")
        return role['Role']['Arn']
    except iam.exceptions.NoSuchEntityException:
        print(f"⚠️ IAM Role '{role_name}' not found. Creating...")

        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "codebuild.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }

        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Service role for CodeBuild with S3 + build permissions"
        )

        # Attach required policies (free-tier friendly)
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/AmazonS3FullAccess"
        )
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/AWSCodeBuildDeveloperAccess"
        )

        print(f"✅ Created IAM Role '{role_name}' with policies.")
        return role['Role']['Arn']

def create_codepipeline(pipeline_name, s3_bucket_name, github_repo_name, github_owner,
                        codebuild_project_name, codedeploy_app_name, codedeploy_group_name,
                        codepipeline_role_arn, github_token, codebuild_role_arn):
    """Creates the CodePipeline resource using GitHub as source."""
    cp_client = boto3.client('codepipeline')

    try:
        cp_client.create_pipeline(
            pipeline={
                'name': pipeline_name,
                'roleArn': codepipeline_role_arn,
                'artifactStore': {
                    'type': 'S3',
                    'location': s3_bucket_name
                },
                'stages': [
                    {
                        'name': 'Source',
                        'actions': [
                            {
                                'name': 'Source',
                                'actionTypeId': {
                                    'category': 'Source',
                                    'owner': 'ThirdParty',
                                    'provider': 'GitHub',
                                    'version': '1'
                                },
                                'outputArtifacts': [{'name': 'SourceArtifact'}],
                                'configuration': {
                                    'Owner': github_owner,
                                    'Repo': github_repo_name,
                                    'Branch': 'main',
                                    'OAuthToken': github_token,
                                    'PollForSourceChanges': 'false'
                                }
                            }
                        ]
                    },
                    {
                        'name': 'Build',
                        'actions': [
                            {
                                'name': 'Build',
                                'actionTypeId': {
                                    'category': 'Build',
                                    'owner': 'AWS',
                                    'provider': 'CodeBuild',
                                    'version': '1'
                                },
                                'inputArtifacts': [{'name': 'SourceArtifact'}],
                                'outputArtifacts': [{'name': 'BuildArtifact'}],
                                'configuration': {
                                    'ProjectName': codebuild_project_name
                                }
                            }
                        ]
                    },
                    {
                        'name': 'Deploy',
                        'actions': [
                            {
                                'name': 'Deploy',
                                'actionTypeId': {
                                    'category': 'Deploy',
                                    'owner': 'AWS',
                                    'provider': 'CodeDeploy',
                                    'version': '1'
                                },
                                'inputArtifacts': [{'name': 'BuildArtifact'}],
                                'configuration': {
                                    'ApplicationName': codedeploy_app_name,
                                    'DeploymentGroupName': codedeploy_group_name
                                }
                            }
                        ]
                    }
                ]
            }
        )
        print(f"✅ CodePipeline '{pipeline_name}' created.")
    except Exception as e:
        print(f"❌ Error creating CodePipeline: {e}")

if __name__ == "__main__":
    region = 'ap-south-1'
    s3_bucket_name = "cicd-artifact-bucket-980921729554-ap-south-1"
# 👆 replace 980921729554 with your AWS account ID
 # must be unique globally

    github_repo_name = "aws-cicd-project"
    github_owner = "your-github-username"
    github_secret_name = "github_pat_for_cicd"

    codebuild_project_name = "MyCICDProjectBuild"
    codedeploy_app_name = "MyCICDProjectApp"
    codedeploy_group_name = "MyCICDProjectGroup"

    # Pre-created IAM roles (replace with your stack outputs)
    codepipeline_role_arn = "arn:aws:iam::980921729554:role/MyCICDProjectStack-CodePipelineRole-BfBJkSvHRfJN"
    codedeploy_role_arn = "arn:aws:iam::980921729554:role/MyCICDProjectStack-CodeDeployRole-qrk0vjduap4d"

    # Ensure CodeBuild role exists
    codebuild_role_arn = ensure_codebuild_role("CodeBuildServiceRole")

    # Get GitHub PAT
    github_token = get_secret(github_secret_name, region)
    if not github_token:
        print("❌ Failed to retrieve GitHub token. Exiting.")
        exit(1)

    # Create S3 bucket
    s3_client = boto3.client('s3', region_name=region)
    try:
        s3_client.create_bucket(
            Bucket=s3_bucket_name,
            CreateBucketConfiguration={'LocationConstraint': region}
        )
        print(f"✅ S3 bucket '{s3_bucket_name}' created.")
    except Exception as e:
        print(f"⚠️ Error creating S3 bucket: {e}")

    # Create CodeDeploy application
    cd_client = boto3.client('codedeploy', region_name=region)
    try:
        cd_client.create_application(applicationName=codedeploy_app_name)
        print(f"✅ CodeDeploy application '{codedeploy_app_name}' created.")
    except Exception as e:
        print(f"⚠️ Error creating CodeDeploy application: {e}")

    # Create CodeBuild project
    cb_client = boto3.client('codebuild', region_name=region)
    try:
        cb_client.create_project(
            name=codebuild_project_name,
            serviceRole=codebuild_role_arn,
            artifacts={'type': 'CODEPIPELINE'},
            source={'type': 'CODEPIPELINE'},
            environment={
                'type': 'LINUX_CONTAINER',
                'computeType': 'BUILD_GENERAL1_SMALL',  # free tier
                'image': 'aws/codebuild/standard:5.0'
            }
        )
        print(f"✅ CodeBuild project '{codebuild_project_name}' created.")
    except Exception as e:
        print(f"❌ Error creating CodeBuild project: {e}")

    # Create CodeDeploy Deployment Group
    try:
        cd_client.create_deployment_group(
            applicationName=codedeploy_app_name,
            deploymentGroupName=codedeploy_group_name,
            serviceRoleArn=codedeploy_role_arn,
            deploymentStyle={
                'deploymentType': 'IN_PLACE',
                'deploymentOption': 'WITHOUT_TRAFFIC_CONTROL'
            },
            ec2TagFilters=[{'Key': 'Name', 'Value': 'MyEC2Instance', 'Type': 'KEY_AND_VALUE'}]
        )
        print(f"✅ CodeDeploy deployment group '{codedeploy_group_name}' created.")
    except Exception as e:
        print(f"❌ Error creating CodeDeploy deployment group: {e}")

    # Create CodePipeline
    create_codepipeline(
        pipeline_name="MyCICDProjectPipeline",
        s3_bucket_name=s3_bucket_name,
        github_repo_name=github_repo_name,
        github_owner=github_owner,
        codebuild_project_name=codebuild_project_name,
        codedeploy_app_name=codedeploy_app_name,
        codedeploy_group_name=codedeploy_group_name,
        codepipeline_role_arn=codepipeline_role_arn,
        github_token=github_token,
        codebuild_role_arn=codebuild_role_arn
    )
