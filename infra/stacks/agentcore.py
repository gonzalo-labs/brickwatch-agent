import os
import re
from typing import Any, Dict, Optional

from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    CustomResource,
    DockerVolume,
    Duration,
    Stack,
)
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as aws_lambda
from aws_cdk import aws_s3_assets as s3assets
from aws_cdk import aws_ssm as ssm
from aws_cdk import custom_resources as cr
from constructs import Construct


class AgentCoreStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        api_url: str,
        api_key_value: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        agent_role = iam.Role(
            self,
            "BrickwatchAgentCoreRole",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock.amazonaws.com"),  # type: ignore[arg-type]
                iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),  # type: ignore[arg-type]
            ),  # type: ignore[arg-type]
        )

        provisioner_path = os.path.join(
            os.getcwd(), "custom-resources", "agentcore_provisioner"
        )
        repo_root_from_provisioner = os.path.abspath(
            os.path.join(provisioner_path, "..", "..", "..")
        )
        manifest_path = os.path.join(
            repo_root_from_provisioner, "agentcore", "gateway.manifest.json"
        )

        on_event = aws_lambda.Function(
            self,
            "AgentCoreProvisionerFn",
            code=aws_lambda.Code.from_asset(
                provisioner_path,
                bundling=BundlingOptions(
                    image=aws_lambda.Runtime.PYTHON_3_12.bundling_image,  # type: ignore[attr-defined]
                    volumes=[
                        DockerVolume(
                            host_path=os.path.dirname(manifest_path),
                            container_path="/ext/agentcore",
                        )
                    ],
                    command=[
                        "bash",
                        "-lc",
                        "python -m pip install -r /asset-input/requirements.txt -t /asset-output "
                        "&& cp handler.py /asset-output/ "
                        "&& cp /ext/agentcore/gateway.manifest.json /asset-output/gateway.manifest.json",
                    ],
                ),
            ),
            handler="handler.handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,  # type: ignore[attr-defined]
            timeout=Duration.minutes(10),
        )

        on_event.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:CreateGateway",
                    "bedrock-agentcore:GetGateway",
                    "bedrock-agentcore:UpdateGateway",
                    "bedrock-agentcore:ListGateways",
                    "bedrock-agentcore:CreateGatewayTarget",
                    "bedrock-agentcore:ListGatewayTargets",
                    "bedrock-agentcore:CreateAgentRuntime",
                    "bedrock-agentcore:UpdateAgentRuntime",
                    "bedrock-agentcore:ListAgentRuntimes",
                    "bedrock-agentcore:CreateApiKeyCredentialProvider",
                    "bedrock-agentcore:GetApiKeyCredentialProvider",
                    "bedrock-agentcore:ListApiKeyCredentialProviders",
                    "bedrock-agentcore:CreateWorkloadIdentity",
                    "bedrock-agentcore:GetWorkloadIdentity",
                    "bedrock-agentcore:ListWorkloadIdentities",
                    "bedrock-agentcore:GetWorkloadIdentityDirectory",
                    "bedrock-agentcore:GetTokenVault",
                    "bedrock-agentcore:CreateTokenVault",
                    "bedrock-agentcore:SetTokenVaultCMK",
                ],
                resources=["*"],
            )
        )

        on_event.add_to_role_policy(
            iam.PolicyStatement(actions=["bedrock-agentcore:*"], resources=["*"])
        )

        on_event.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "secretsmanager:CreateSecret",
                    "secretsmanager:PutSecretValue",
                    "secretsmanager:TagResource",
                    "secretsmanager:DescribeSecret",
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:UpdateSecret",
                    "secretsmanager:DeleteSecret",
                ],
                resources=["*"],
            )
        )

        on_event.add_to_role_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[agent_role.role_arn],
                conditions={
                    "StringEquals": {
                        "iam:PassedToService": [
                            "bedrock.amazonaws.com",
                            "bedrock-agentcore.amazonaws.com",
                        ]
                    }
                },
            )
        )
        on_event.add_to_role_policy(
            iam.PolicyStatement(actions=["iam:CreateServiceLinkedRole"], resources=["*"])
        )

        runtime_repo = ecr.Repository(
            self,
            "AgentCoreRuntimeRepo",
            repository_name=f"rita-agentcore-runtime-{self.account}-{self.region}",
            image_scan_on_push=True,
        )
        agent_role.add_to_policy(
            iam.PolicyStatement(actions=["ecr:GetAuthorizationToken"], resources=["*"])
        )
        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                ],
                resources=[runtime_repo.repository_arn],
            )
        )

        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                ],
                resources=["*"],
            )
        )
        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )
        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:Converse",
                    "bedrock:ConverseStream",
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.nova-pro-v1:0",
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.nova-lite-v1:0",
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.nova-micro-v1:0",
                    "arn:aws:bedrock:eu-central-1:542508027791:inference-profile/eu.amazon.nova-2-lite-v1:0",
                    "arn:aws:bedrock:eu-central-1::foundation-model/amazon.nova-2-lite-v1:0",
                    "arn:aws:bedrock:eu-north-1::foundation-model/amazon.nova-2-lite-v1:0",
                    "arn:aws:bedrock:eu-west-1::foundation-model/amazon.nova-2-lite-v1:0",
                    "arn:aws:bedrock:eu-west-3::foundation-model/amazon.nova-2-lite-v1:0",
                    "arn:aws:bedrock:eu-south-1::foundation-model/amazon.nova-2-lite-v1:0",
                    "arn:aws:bedrock:eu-south-2::foundation-model/amazon.nova-2-lite-v1:0",
                ],
            )
        )
        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ce:GetCostAndUsage",
                    "ce:GetDimensionValues",
                    "ce:GetReservationCoverage",
                    "ce:GetReservationPurchaseRecommendation",
                    "ce:GetReservationUtilization",
                    "ce:GetRightsizingRecommendation",
                    "ce:GetSavingsPlansUtilization",
                    "ce:GetSavingsPlansUtilizationDetails",
                    "ce:GetUsageReport",
                    "ce:GetAnomalies",
                    "ce:GetAnomalyMonitors",
                    "ce:GetAnomalySubscriptions",
                ],
                resources=["*"],
            )
        )
        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "compute-optimizer:GetEC2InstanceRecommendations",
                    "compute-optimizer:GetEC2RecommendationProjectedMetrics",
                    "compute-optimizer:GetAutoScalingGroupRecommendations",
                    "compute-optimizer:GetEBSVolumeRecommendations",
                    "compute-optimizer:GetLambdaFunctionRecommendations",
                    "compute-optimizer:GetEnrollmentStatus",
                    "compute-optimizer:GetRecommendationSummaries",
                ],
                resources=["*"],
            )
        )
        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ec2:DescribeInstances",
                    "ec2:DescribeVolumes",
                    "ec2:DescribeSnapshots",
                    "rds:DescribeDBInstances",
                    "rds:DescribeDBClusters",
                    "lambda:ListFunctions",
                    "lambda:GetFunctionConfiguration",
                    "lambda:GetFunctionConcurrency",
                    "autoscaling:DescribeAutoScalingGroups",
                    "s3:ListAllMyBuckets",
                    "s3:GetBucketLocation",
                    "s3:GetLifecycleConfiguration",
                    "s3:GetBucketTagging",
                    "cloudwatch:GetMetricStatistics",
                ],
                resources=["*"],
            )
        )

        provider = cr.Provider(
            self,
            "AgentCoreProvider",
            on_event_handler=on_event,  # type: ignore[arg-type]
        )

        runtime_src = s3assets.Asset(
            self,
            "AgentCoreRuntimeSrc",
            path=os.path.join(os.path.dirname(__file__), "..", "..", "agentcore_runtime"),
        )
        project = codebuild.Project(
            self,
            "AgentCoreRuntimeBuild",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5,
                privileged=True,
            ),
            environment_variables={
                "REPO_URI": codebuild.BuildEnvironmentVariable(
                    value=runtime_repo.repository_uri
                ),
                "IMAGE_TAG": codebuild.BuildEnvironmentVariable(
                    value=runtime_src.asset_hash
                ),
                "SRC_BUCKET": codebuild.BuildEnvironmentVariable(
                    value=runtime_src.s3_bucket_name
                ),
                "SRC_KEY": codebuild.BuildEnvironmentVariable(
                    value=runtime_src.s3_object_key
                ),
                "AWS_REGION": codebuild.BuildEnvironmentVariable(value=self.region),
            },
            build_spec=codebuild.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "pre_build": {
                            "commands": [
                                "echo Logging into ECR",
                                "aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $REPO_URI",
                                "docker buildx create --use --name xbuilder || true",
                                "aws s3 cp s3://$SRC_BUCKET/$SRC_KEY src.zip",
                                "mkdir -p src && unzip -q src.zip -d src && cd src",
                            ]
                        },
                        "build": {
                            "commands": [
                                "docker buildx build --platform linux/arm64 -t $REPO_URI:$IMAGE_TAG --push ."
                            ]
                        },
                    },
                    "artifacts": {"files": ["**/*"], "discard-paths": "yes"},
                }
            ),
        )
        runtime_src.grant_read(project)
        runtime_repo.grant_pull_push(project)
        on_event.add_to_role_policy(
            iam.PolicyStatement(
                actions=["codebuild:StartBuild", "codebuild:BatchGetBuilds"],
                resources=[project.project_arn],
            )
        )

        user_pool = cognito.UserPool(
            self,
            "BrickwatchUserPool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
        )
        user_pool_client = cognito.UserPoolClient(
            self,
            "BrickwatchUserPoolClient",
            user_pool=user_pool,
            generate_secret=False,
        )
        domain_prefix = (
            f"rita-{self.account}-{self.region}".lower()
            .replace("_", "-")
            .replace(".", "-")
        )
        domain_prefix = re.sub(r"[^a-z0-9-]", "", domain_prefix)[:63]
        domain = user_pool.add_domain(
            "BrickwatchCognitoDomain",
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix=domain_prefix),
        )
        discovery_url = (
            f"https://cognito-idp.{self.region}.amazonaws.com/{user_pool.user_pool_id}"
            "/.well-known/openid-configuration"
        )

        self.cognito_user_pool_id = user_pool.user_pool_id
        self.cognito_user_pool_client_id = user_pool_client.user_pool_client_id
        self.cognito_domain = f"{domain.domain_name}.auth.{self.region}.amazoncognito.com"

        properties: Dict[str, Any] = {
            "AgentName": "Brickwatch",
            "SystemPrompt": "You are Brickwatch, a cost optimization assistant.",
            "InferenceModel": "arn:aws:bedrock:eu-central-1:542508027791:inference-profile/eu.amazon.nova-2-lite-v1:0",
            "AgentRoleArn": agent_role.role_arn,
            "ApiUrl": api_url,
            "EnableLogging": True,
            "LogLevel": "DEBUG",
            "EnableTracing": True,
            "RuntimeBuildProject": project.project_name,
            "RuntimeRepoUri": runtime_repo.repository_uri,
            "RuntimeImageTag": runtime_src.asset_hash,
            "RuntimeSrcBucket": runtime_src.s3_bucket_name,
            "RuntimeSrcKey": runtime_src.s3_object_key,
            "AuthorizerType": "CUSTOM_JWT",
            "JwtDiscoveryUrl": discovery_url,
            "JwtAllowedAudience": [user_pool_client.user_pool_client_id],
            "ApiKeyValue": api_key_value or None,
            "ApiKeyProviderArn": self.node.try_get_context("apiKeyProviderArn")
            or None,
            "OAuthProviderArn": self.node.try_get_context("oauthProviderArn") or None,
            "Tools": [{"name": "Ping", "method": "GET", "path": api_url}],
            "Nonce": self.node.try_get_context("agentCoreNonce") or "v2",
        }

        resource = CustomResource(
            self,
            "AgentCoreResource",
            service_token=provider.service_token,
            properties=properties,
        )

        CfnOutput(self, "GatewayId", value=resource.get_att_string("GatewayId"))
        CfnOutput(self, "AgentAlias", value=resource.get_att_string("AgentAlias"))
        CfnOutput(
            self,
            "RuntimeEndpointArn",
            value=resource.get_att_string("RuntimeEndpointArn"),
        )
        CfnOutput(
            self,
            "AgentRuntimeId",
            value=resource.get_att_string("AgentRuntimeId"),
        )
        CfnOutput(self, "AgentRoleArn", value=agent_role.role_arn)
        CfnOutput(self, "CognitoUserPoolId", value=self.cognito_user_pool_id)
        CfnOutput(
            self,
            "CognitoUserPoolClientId",
            value=self.cognito_user_pool_client_id,
        )
        CfnOutput(self, "CognitoDomain", value=self.cognito_domain)

        ns = "/rita/agentcore"
        ssm.StringParameter(
            self,
            "AgentIdParam",
            parameter_name=f"{ns}/id",
            string_value=resource.get_att_string("GatewayId"),
        )
        ssm.StringParameter(
            self,
            "AgentAliasParam",
            parameter_name=f"{ns}/alias",
            string_value=resource.get_att_string("AgentAlias"),
        )
        ssm.StringParameter(
            self,
            "AgentInvokeArnParam",
            parameter_name=f"{ns}/invoke-arn",
            string_value=resource.get_att_string("RuntimeEndpointArn"),
        )
        ssm.StringParameter(
            self,
            "AgentRuntimeIdParam",
            parameter_name=f"{ns}/runtime-id",
            string_value=resource.get_att_string("AgentRuntimeId"),
        )
        ssm.StringParameter(
            self,
            "AgentRoleArnParam",
            parameter_name=f"{ns}/role-arn",
            string_value=agent_role.role_arn,
        )
        ssm.StringParameter(
            self,
            "AgentRuntimeVersionParam",
            parameter_name=f"{ns}/runtime-version",
            string_value=resource.get_att_string("AgentRuntimeVersion"),
        )
