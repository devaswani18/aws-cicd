import boto3
import json
import zipfile
import os
import time

# ----------------------------
# SETTINGS
# ----------------------------
LAMBDA_NAME = "contact-form-sender"
API_NAME = "ContactFormAPI"
REGION = "ap-south-1"
FROM_EMAIL = "aswanidev997@gmail.com"  # verified in SES
TO_EMAIL = "aswanidev997@gmail.com"    # verified if sandbox
SES_REGION = REGION

# ----------------------------
# IAM ROLE SETUP
# ----------------------------
iam_client = boto3.client('iam')
role_name = "ContactFormLambdaRole"
assume_role_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect":"Allow",
            "Principal":{"Service":"lambda.amazonaws.com"},
            "Action":"sts:AssumeRole"
        }
    ]
}

try:
    role = iam_client.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(assume_role_policy),
        Description="Lambda role for SES contact form"
    )
    print(f"IAM role '{role_name}' created.")
except iam_client.exceptions.EntityAlreadyExistsException:
    role = iam_client.get_role(RoleName=role_name)
    print(f"IAM role '{role_name}' already exists.")

role_arn = role['Role']['Arn']

# Attach policies
iam_client.attach_role_policy(
    RoleName=role_name,
    PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
)

ses_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect":"Allow",
            "Action":["ses:SendEmail","ses:SendRawEmail"],
            "Resource":"*"
        }
    ]
}

try:
    iam_client.put_role_policy(
        RoleName=role_name,
        PolicyName="SESSendEmailPolicy",
        PolicyDocument=json.dumps(ses_policy)
    )
except Exception as e:
    print("Error attaching inline SES policy:", e)

time.sleep(10)  # give IAM role time to propagate

# ----------------------------
# ZIP LAMBDA FUNCTION
# ----------------------------
zip_filename = "lambda_function.zip"
with zipfile.ZipFile(zip_filename, 'w') as zipf:
    zipf.write("lambda_function.py")

# ----------------------------
# CREATE OR UPDATE LAMBDA
# ----------------------------
lambda_client = boto3.client('lambda', region_name=REGION)

env_vars = {
    'FROM_EMAIL': FROM_EMAIL,
    'TO_EMAIL': TO_EMAIL,
    'SES_REGION': SES_REGION
}

try:
    with open(zip_filename, 'rb') as f:
        zipped_code = f.read()
    lambda_client.create_function(
        FunctionName=LAMBDA_NAME,
        Runtime="python3.11",
        Role=role_arn,
        Handler="lambda_function.lambda_handler",
        Code={"ZipFile": zipped_code},
        Timeout=10,
        Environment={"Variables": env_vars}
    )
    print(f"Lambda function '{LAMBDA_NAME}' created.")
except lambda_client.exceptions.ResourceConflictException:
    # If Lambda exists, update code and env vars
    with open(zip_filename, 'rb') as f:
        zipped_code = f.read()
    lambda_client.update_function_code(
        FunctionName=LAMBDA_NAME,
        ZipFile=zipped_code
    )
    lambda_client.update_function_configuration(
        FunctionName=LAMBDA_NAME,
        Environment={"Variables": env_vars}
    )
    print(f"Lambda function '{LAMBDA_NAME}' updated.")

# ----------------------------
# CREATE API GATEWAY
# ----------------------------
apig_client = boto3.client('apigatewayv2', region_name=REGION)

api = apig_client.create_api(
    Name=API_NAME,
    ProtocolType='HTTP',
)
api_id = api['ApiId']

# Create Lambda integration
integration = apig_client.create_integration(
    ApiId=api_id,
    IntegrationType='AWS_PROXY',
    IntegrationUri=f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31/functions/arn:aws:lambda:{REGION}:{boto3.client('sts').get_caller_identity()['Account']}:function:{LAMBDA_NAME}/invocations",
    PayloadFormatVersion='2.0'
)

# Create route
apig_client.create_route(
    ApiId=api_id,
    RouteKey='POST /contact',
    Target=f'integrations/{integration["IntegrationId"]}'
)

# Deploy API
deployment = apig_client.create_deployment(ApiId=api_id, Description="Contact Form Deployment")
stage = apig_client.create_stage(ApiId=api_id, StageName="prod", DeploymentId=deployment['DeploymentId'])

# Add permission for API Gateway to invoke Lambda
lambda_client.add_permission(
    FunctionName=LAMBDA_NAME,
    StatementId="APIGatewayInvoke",
    Action="lambda:InvokeFunction",
    Principal="apigateway.amazonaws.com",
    SourceArn=f"arn:aws:execute-api:{REGION}:{boto3.client('sts').get_caller_identity()['Account']}:{api_id}/*/*/contact"
)

print(f"Contact form API is live at: https://{api_id}.execute-api.{REGION}.amazonaws.com/prod/contact")
