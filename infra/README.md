# Infrastructure as Code (AWS CDK - Python)

This directory contains the Python CDK app for deploying Brickwatch's infrastructure.

## Purpose

Defines and deploys:
- Bedrock AgentCore runtimes for Analysis and Workflow agents
- API Gateway with Lambda orchestration
- S3 + CloudFront for web UI hosting
- IAM roles and policies
- Cognito authentication
- CloudWatch logging

## Stacks

### 1. `BrickwatchIam` (`stacks/iam_roles.py`)
Creates IAM roles and policies:
- **Analysis Agent Role**: Read-only access to AWS resources
- **Workflow Agent Role**: Write access for resource modifications
- **API Lambda Role**: Permission to invoke agents

**Deploy:**
```bash
npx cdk deploy BrickwatchIam
```

### 2. `BrickwatchAgentCore` (`stacks/agentcore.py`)
Deploys the Analysis Agent:
- Docker-based runtime image built in CodeBuild
- Bedrock AgentCore registration with Nova Pro model
- IAM role with read permissions for EC2, S3, Lambda, Cost Explorer, Compute Optimizer
- CloudWatch logging

**Deploy:**
```bash
npx cdk deploy BrickwatchAgentCore
```

**Build time**: 7-8 minutes (image build)

### 3. `BrickwatchWorkflowAgent` (`stacks/workflow_agent.py`)
Deploys the Workflow Agent:
- Docker-based runtime image built in CodeBuild
- Bedrock AgentCore registration with Nova Lite model
- IAM role with write permissions for resource modifications
- CloudWatch logging

**Deploy:**
```bash
npx cdk deploy BrickwatchWorkflowAgent
```

**Build time**: 7-8 minutes (image build)

### 4. `BrickwatchApi` (`stacks/api.py`)
Deploys the API Gateway and orchestration layer:
- Lambda function built from a container image
- API Gateway REST API with CORS
- Cognito User Pool for authentication
- SSM parameters for agent endpoints

**Deploy:**
```bash
npx cdk deploy BrickwatchApi
```

### 5. `BrickwatchSageMaker` (`stacks/sagemaker.py`)
Optional: ML-based cost forecasting endpoint
- SageMaker endpoint (optional, not required for core functionality)

**Deploy:**
```bash
npx cdk deploy BrickwatchSageMaker
```

### 6. `BrickwatchUi` (`stacks/ui_hosting.py`)
Deploys the web interface:
- S3 bucket for static website hosting
- CloudFront distribution for global CDN
- Origin Access Identity for secure S3 access

**Deploy:**
```bash
npx cdk deploy BrickwatchUi
```

## Deployment Order

Deploy stacks in this order to satisfy dependencies:

```bash
# 1. IAM roles (optional, can be created by other stacks)
npx cdk deploy BrickwatchIam

# 2. Agents (can be deployed in parallel)
npx cdk deploy BrickwatchAgentCore BrickwatchWorkflowAgent

# 3. API (depends on agents)
npx cdk deploy BrickwatchApi

# 4. UI (depends on API for configuration)
npx cdk deploy BrickwatchUi

# 5. Optional: SageMaker
npx cdk deploy BrickwatchSageMaker
```

Or deploy all at once (recommended):
```bash
npx cdk deploy --all
```

## CDK App Entry Point

### `app.py`
Main CDK app that instantiates all stacks:
```python
app = App()

IamRolesStack(app, "BrickwatchIam")
AgentCoreStack(app, "BrickwatchAgentCore", api_url="...")
WorkflowAgentStack(app, "BrickwatchWorkflowAgent", api_url="...", cognito_user_pool_id="...", cognito_user_pool_client_id="...")
ApiStack(app, "BrickwatchApi")
UiHostingStack(app, "BrickwatchUi", api_url="...", api_key_value="...", cognito_domain="...", user_pool_client_id="...", user_pool_id="...")
```

## Configuration

### `cdk.json`
CDK configuration file:
- Feature flags for CDK behavior
- Context values for stack customization

### Environment Variables
Set these before deploying:
```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=123456789012
export CDK_DEFAULT_REGION=us-east-1
export CDK_DEFAULT_ACCOUNT=123456789012
```

Or let CDK use your current AWS CLI profile:
```bash
export AWS_PROFILE=my-profile
npx cdk deploy --all
```

## Key Files

### `stacks/agentcore.py`
Analysis Agent deployment:
- **Docker Image**: Built from `../agentcore_runtime/`
- **Model**: Amazon Nova Pro (`amazon.nova-pro-v1:0`)
- **IAM Permissions**: Read-only access to AWS services

Key code:
```python
agent_role = iam.Role(self, "AgentRole", assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"))

agent_role.add_to_policy(iam.PolicyStatement(
    actions=[
        "ec2:DescribeInstances",
        "s3:ListAllMyBuckets",
        "lambda:ListFunctions",
        "ce:GetCostAndUsage",
        "compute-optimizer:GetEC2InstanceRecommendations",
        "cloudwatch:GetMetricStatistics",
    ],
    resources=["*"],
))
```

### `stacks/workflow_agent.py`
Workflow Agent deployment:
- **Docker Image**: Built from `../workflow_runtime/`
- **Model**: Amazon Nova Lite (`amazon.nova-lite-v1:0`)
- **IAM Permissions**: Write access for resource modifications

Key code:
```python
workflow_agent_role.add_to_policy(iam.PolicyStatement(
    actions=[
        "ec2:StopInstances",
        "ec2:StartInstances",
        "ec2:ModifyInstanceAttribute",
        "s3:PutLifecycleConfiguration",
        "lambda:UpdateFunctionConfiguration",
        "lambda:PutFunctionConcurrency",
    ],
    resources=["*"],
))
```

### `stacks/api.py`
API Gateway and Lambda orchestration:
- **Runtime**: Container-based Lambda
- **Memory**: 512MB
- **Timeout**: 300 seconds
- **API**: REST API with CORS enabled
- **Auth**: Cognito User Pool

Key code:
```python
api = apigw.LambdaRestApi(self, "BrickwatchApi", handler=api_fn, proxy=False)

chat = api.root.add_resource("v1").add_resource("chat")
chat.add_method("POST", api_key_required=False)
```

## Outputs

After deployment, CDK outputs important values:

**BrickwatchApi:**
- `ApiUrl`: API Gateway endpoint (e.g., https://abc123.execute-api.us-east-1.amazonaws.com/prod)
- `ApiKey`: API key for authenticated requests

**BrickwatchAgentCore:**
- `AgentRuntimeId`: Bedrock AgentCore runtime ID
- `GatewayId`: Agent gateway ID
- `CognitoUserPoolId`: Cognito User Pool ID
- `CognitoUserPoolClientId`: Client ID for authentication

**BrickwatchWorkflowAgent:**
- `WorkflowAgentRuntimeId`: Workflow agent runtime ID
- `WorkflowGatewayId`: Workflow agent gateway ID

**BrickwatchUi:**
- `CdnUrl`: CloudFront URL for web interface
- `BucketName`: S3 bucket name for static assets

Retrieve outputs:
```bash
aws cloudformation describe-stacks \
  --stack-name BrickwatchApi \
  --query 'Stacks[0].Outputs'
```

## Dependencies

### Python CDK Packages
```bash
pip install -r requirements.txt
```

### Node.js (CDK CLI)
```bash
npm install -g aws-cdk
```

## Useful CDK Commands

```bash
# List all stacks
npx cdk list

# Show CloudFormation template
npx cdk synth BrickwatchApi

# Compare deployed vs. local changes
npx cdk diff BrickwatchApi

# Deploy specific stack
npx cdk deploy BrickwatchApi

# Deploy all stacks without approval prompts
npx cdk deploy --all --require-approval never

# Destroy all stacks (cleanup)
npx cdk destroy --all
```

## Bootstrap

First-time CDK setup in a new AWS account/region:

```bash
npx cdk bootstrap aws://ACCOUNT_ID/REGION
```

This creates:
- S3 bucket for CDK assets (Lambda code, Docker images)
- ECR repository for Docker images
- IAM roles for CloudFormation

## Cost Estimation

Approximate monthly costs for Brickwatch:

| Service | Usage | Cost |
|---------|-------|------|
| Bedrock Nova Pro | 1M input + 200K output tokens | $3.50 |
| Bedrock Nova Lite | 10M input + 2M output tokens | $1.10 |
| Lambda (API) | 100K invocations, 512MB, 1s avg | $0.50 |
| Lambda (Agents) | Included in Bedrock AgentCore | $0 |
| API Gateway | 100K requests | $0.35 |
| CloudFront | 10GB transfer | $0.85 |
| S3 | 5GB storage | $0.12 |
| CloudWatch Logs | 5GB logs | $2.50 |
| **Total** | | **~$9/month** |

**Savings ROI**: If Brickwatch saves $100/month in AWS costs, ROI is **11x**.

## Troubleshooting

### Issue: "CDK bootstrap required"
**Fix:** Run `npx cdk bootstrap`

### Issue: Docker build fails
**Fix:** Ensure Docker is running: `docker info`

### Issue: "Resource already exists"
**Fix:** Destroy and redeploy: `npx cdk destroy BrickwatchApi && npx cdk deploy BrickwatchApi`

### Issue: "Insufficient permissions"
**Fix:** Ensure your AWS credentials have Admin or PowerUser permissions

### Issue: Agent build takes too long (>10 minutes)
**Cause:** Slow image build (installing Python packages)
**Fix:** Use `--no-cache` flag or pre-build base image

## Security Best Practices

1. **Least Privilege IAM**: Only grant necessary permissions
2. **Resource Tagging**: Tag all resources for cost tracking
3. **Enable CloudTrail**: Audit all API calls
4. **VPC Integration**: Run Lambdas in private subnets (for production)
5. **Secrets Manager**: Store sensitive config (not environment variables)
6. **WAF Protection**: Add AWS WAF to API Gateway (for production)

## CI/CD Integration

Example GitHub Actions workflow:

```yaml
name: Deploy Brickwatch
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 20
      - name: Install dependencies
        run: cd infra && pip install -r requirements.txt
      - name: Deploy to AWS
        run: cd infra && npx cdk deploy --all --require-approval never
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          AWS_REGION: us-east-1
```

## Extending Infrastructure

### Adding New Stacks

1. Create new stack file: `stacks/my_new_stack.py`
```python
from aws_cdk import Stack
from constructs import Construct

class MyNewStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # Add resources here
```

2. Import in `app.py`:
```python
from stacks.my_new_stack import MyNewStack

MyNewStack(app, "MyNewStack")
```

3. Deploy:
```bash
npx cdk deploy MyNewStack
```
