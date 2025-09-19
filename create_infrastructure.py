import boto3

def create_or_update_cf_stack(stack_name, template_file, region):
    """Creates or updates a CloudFormation stack from a template file."""
    cf_client = boto3.client('cloudformation', region_name=region)
    with open(template_file, 'r') as f:
        template_body = f.read()

    try:
        # Check if stack exists
        cf_client.describe_stacks(StackName=stack_name)
        stack_exists = True
    except cf_client.exceptions.ClientError as e:
        if "does not exist" in str(e):
            stack_exists = False
        else:
            print(f"Error describing stack: {e}")
            return None

    if stack_exists:
        print(f"🔄 Updating CloudFormation stack '{stack_name}'...")
        try:
            cf_client.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Capabilities=['CAPABILITY_IAM']
            )
            cf_client.get_waiter('stack_update_complete').wait(StackName=stack_name)
            print(f"✅ Stack '{stack_name}' updated successfully.")
        except cf_client.exceptions.ClientError as e:
            if "No updates are to be performed" in str(e):
                print(f"ℹ️ Stack '{stack_name}' is already up-to-date, no changes to perform.")
            else:
                print(f"❌ Error updating CloudFormation stack: {e}")
                return None
    else:
        print(f"🚀 Creating CloudFormation stack '{stack_name}'...")
        try:
            cf_client.create_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Capabilities=['CAPABILITY_IAM']
            )
            cf_client.get_waiter('stack_create_complete').wait(StackName=stack_name)
            print(f"✅ Stack '{stack_name}' created successfully.")
        except Exception as e:
            print(f"❌ Error creating CloudFormation stack: {e}")
            return None
            
    # Fetch roles after creation or update
    try:
        resources = cf_client.describe_stack_resources(StackName=stack_name)
        role_arns = {}
        for res in resources['StackResources']:
            if res['ResourceType'] == 'AWS::IAM::Role':
                role_arns[res['LogicalResourceId']] = res['PhysicalResourceId']
        return role_arns
    except Exception as e:
        print(f"❌ Error fetching stack resources: {e}")
        return None


if __name__ == "__main__":
    region = 'ap-south-1'   # ✅ changed to ap-south-1
    cf_stack_name = "MyCICDProjectStack"
    template_file = "iac_ec2.yml"
    
    roles = create_or_update_cf_stack(cf_stack_name, template_file, region)
    if roles:
        print("\n✅ Infrastructure setup complete. IAM Roles created/managed:")
        for logical_id, arn in roles.items():
            print(f"- {logical_id}: {arn}")
    else:
        print("\n❌ CloudFormation stack operation failed.")
