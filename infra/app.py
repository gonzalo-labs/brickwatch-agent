#!/usr/bin/env python3
import os

from aws_cdk import App, Environment

from stacks.iam_roles import IamRolesStack
from stacks.sagemaker import SageMakerStack
from stacks.api import ApiStack
from stacks.ui_hosting import UiHostingStack
from stacks.agentcore import AgentCoreStack
from stacks.workflow_agent import WorkflowAgentStack

app = App()

env = Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION") or "us-east-1",
)

IamRolesStack(app, "BrickwatchIam", env=env)
artifacts_dir = os.path.join(os.path.dirname(__file__), "..", "sagemaker_artifacts")
artifacts_dir = os.path.abspath(artifacts_dir)
sagemaker = None
if os.path.isdir(artifacts_dir):
    sagemaker = SageMakerStack(app, "BrickwatchSageMaker", env=env)
else:
    print(f"WARNING: Skipping BrickwatchSageMaker; missing artifacts at {artifacts_dir}")

api = ApiStack(app, "BrickwatchApi", env=env)

api_url_from_ctx = app.node.try_get_context("apiUrl")
if not api_url_from_ctx:
    print("WARNING: No --context apiUrl provided; BrickwatchAgentCore requires an API Gateway URL.")

agent_core = AgentCoreStack(
    app,
    "BrickwatchAgentCore",
    env=env,
    api_url=api_url_from_ctx
    or "https://example.execute-api.us-east-1.amazonaws.com/prod",
)

workflow_agent = WorkflowAgentStack(
    app,
    "BrickwatchWorkflowAgent",
    env=env,
    api_url=api_url_from_ctx
    or "https://example.execute-api.us-east-1.amazonaws.com/prod",
    cognito_user_pool_id=agent_core.cognito_user_pool_id,
    cognito_user_pool_client_id=agent_core.cognito_user_pool_client_id,
)

ui_api_url = app.node.try_get_context("uiApiUrl") or app.node.try_get_context("apiUrl")
ui_cognito_domain = app.node.try_get_context("uiCognitoDomain")
ui_user_pool_client_id = app.node.try_get_context("uiUserPoolClientId")
ui_user_pool_id = app.node.try_get_context("uiUserPoolId")

ui = None
if ui_api_url and ui_cognito_domain and ui_user_pool_client_id and ui_user_pool_id:
    ui = UiHostingStack(
        app,
        "BrickwatchUi",
        env=env,
        api_url=ui_api_url,
        api_key_value=api.api_key_value,
        cognito_domain=ui_cognito_domain,
        user_pool_client_id=ui_user_pool_client_id,
        user_pool_id=ui_user_pool_id,
    )
else:
    print(
        "WARNING: Skipping BrickwatchUi; set uiApiUrl/uiCognitoDomain/uiUserPoolClientId/uiUserPoolId in context."
    )

agent_core.add_dependency(api)
if sagemaker is not None:
    agent_core.add_dependency(sagemaker)
workflow_agent.add_dependency(agent_core)
if ui is not None:
    ui.add_dependency(api)
    ui.add_dependency(agent_core)

app.synth()
