import os
import secrets

from aws_cdk import (
    CfnOutput,
    CustomResource,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as aws_lambda
from aws_cdk import aws_s3_assets as s3assets
from aws_cdk import custom_resources as cr
from constructs import Construct


class ApiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        api_repo = ecr.Repository(
            self,
            "ApiLambdaRepo",
            image_scan_on_push=True,
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
        )

        api_src = s3assets.Asset(
            self,
            "ApiImageSrc",
            path=os.path.join(os.path.dirname(__file__), "..", "..", "api"),
        )

        api_project = codebuild.Project(
            self,
            "ApiImageBuild",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5,
                privileged=True,
            ),
            environment_variables={
                "REPO_URI": codebuild.BuildEnvironmentVariable(
                    value=api_repo.repository_uri
                ),
                "IMAGE_TAG": codebuild.BuildEnvironmentVariable(value=api_src.asset_hash),
                "SRC_BUCKET": codebuild.BuildEnvironmentVariable(
                    value=api_src.s3_bucket_name
                ),
                "SRC_KEY": codebuild.BuildEnvironmentVariable(value=api_src.s3_object_key),
                "AWS_REGION": codebuild.BuildEnvironmentVariable(value=self.region),
            },
            build_spec=codebuild.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "pre_build": {
                            "commands": [
                                "aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $REPO_URI",
                                "aws s3 cp s3://$SRC_BUCKET/$SRC_KEY src.zip",
                                "mkdir -p src && unzip -q src.zip -d src && cd src",
                            ]
                        },
                        "build": {
                            "commands": [
                                "docker build -f Dockerfile.api -t $REPO_URI:$IMAGE_TAG .",
                                "docker push $REPO_URI:$IMAGE_TAG",
                            ]
                        },
                    },
                    "artifacts": {"files": ["**/*"], "discard-paths": "yes"},
                }
            ),
        )

        api_src.grant_read(api_project)
        api_repo.grant_pull_push(api_project)
        api_project.node.add_dependency(api_repo)

        trigger_code = "\n".join(
            [
                "import boto3, os, time",
                "cb = boto3.client('codebuild')",
                "ecr = boto3.client('ecr')",
                "def handler(event, context):",
                "    project = os.environ['PROJECT']",
                "    repo_name = os.environ['REPO_NAME']",
                "    image_tag = os.environ['IMAGE_TAG']",
                "    physical_id = f'ApiImageBuild-{image_tag}'",
                "    if event.get('RequestType') == 'Delete':",
                "        return {'PhysicalResourceId': event.get('PhysicalResourceId', physical_id), 'Data': {}}",
                "    resp = cb.start_build(projectName=project)",
                "    build_id = resp.get('build', {}).get('id')",
                "    if not build_id:",
                "        raise Exception('Failed to start CodeBuild build')",
                "    while True:",
                "        time.sleep(5)",
                "        res = cb.batch_get_builds(ids=[build_id])",
                "        b = (res.get('builds') or [{}])[0]",
                "        status = b.get('buildStatus')",
                "        if status in ('SUCCEEDED', 'FAILED', 'FAULT', 'STOPPED', 'TIMED_OUT'):",
                "            if status != 'SUCCEEDED':",
                "                raise Exception(f'Build {build_id} failed: {status}')",
                "            break",
                "    for _ in range(60):",
                "        try:",
                "            ecr.describe_images(repositoryName=repo_name, imageIds=[{'imageTag': image_tag}])",
                "            break",
                "        except Exception:",
                "            time.sleep(2)",
                "    return {'PhysicalResourceId': physical_id, 'Data': {'ImageTag': image_tag}}",
            ]
        )

        trigger = aws_lambda.Function(
            self,
            "ApiImageBuildTrigger",
            runtime=aws_lambda.Runtime.PYTHON_3_12,  # type: ignore[attr-defined]
            handler="index.handler",
            code=aws_lambda.Code.from_inline(trigger_code),
            timeout=Duration.minutes(15),
            environment={
                "PROJECT": api_project.project_name,
                "REPO_NAME": api_repo.repository_name,
                "IMAGE_TAG": api_src.asset_hash,
            },
        )

        trigger.add_to_role_policy(
            iam.PolicyStatement(
                actions=["codebuild:StartBuild", "codebuild:BatchGetBuilds"],
                resources=[api_project.project_arn],
            )
        )
        trigger.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ecr:DescribeImages"],
                resources=[api_repo.repository_arn],
            )
        )

        provider = cr.Provider(
            self,
            "ApiImageBuildProvider",
            on_event_handler=trigger,  # type: ignore[arg-type]
        )
        build_resource = CustomResource(
            self,
            "BuildApiImage",
            service_token=provider.service_token,
            properties={
                "RepoName": api_repo.repository_name,
                "ImageTag": api_src.asset_hash,
            },
        )
        build_resource.node.add_dependency(api_repo)
        build_resource.node.add_dependency(api_project)

        api_fn = aws_lambda.DockerImageFunction(
            self,
            "BrickwatchApiFn",
            code=aws_lambda.DockerImageCode.from_ecr(
                api_repo, tag_or_digest=build_resource.get_att_string("ImageTag")
            ),
            architecture=aws_lambda.Architecture.X86_64,
            timeout=Duration.seconds(300),
            memory_size=512,
            environment={
                "AGENTCORE_ID_PARAM": "/rita/agentcore/id",
                "AGENTCORE_ALIAS_PARAM": "/rita/agentcore/alias",
                "AGENTCORE_INVOKE_PARAM": "/rita/agentcore/invoke-arn",
                "AGENTCORE_ROLE_PARAM": "/rita/agentcore/role-arn",
            },
        )
        api_fn.node.add_dependency(build_resource)

        api_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                    "ssm:GetParameterHistory",
                ],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/rita/agentcore/*",
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/rita/workflow-agent/*",
                ],
            )
        )

        api_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account}:function:BrickwatchApi-BrickwatchApiFn*"
                ],
            )
        )
        api_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=["*"],
            )
        )
        api_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:GetAgentRuntimeEndpoint",
                    "bedrock-agentcore:ListAgentRuntimeEndpoints",
                ],
                resources=["*"],
            )
        )
        api_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "ce:GetCostAndUsage",
                    "ce:GetCostForecast",
                    "ce:GetSavingsPlansCoverage",
                    "ce:GetReservationCoverage",
                    "ce:GetAnomalies",
                ],
                resources=["*"],
            )
        )
        api_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "compute-optimizer:GetEC2InstanceRecommendations",
                    "compute-optimizer:GetAutoScalingGroupRecommendations",
                    "compute-optimizer:GetEBSVolumeRecommendations",
                    "compute-optimizer:GetRDSInstanceRecommendations",
                    "compute-optimizer:GetLambdaFunctionRecommendations",
                ],
                resources=["*"],
            )
        )
        api_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "ec2:DescribeInstances",
                    "ec2:DescribeVolumes",
                    "ec2:DescribeInstanceStatus",
                    "ec2:StopInstances",
                    "ec2:StartInstances",
                    "ec2:ModifyInstanceAttribute",
                    "ec2:ModifyVolume",
                    "autoscaling:DescribeAutoScalingGroups",
                    "autoscaling:DescribeLaunchConfigurations",
                    "lambda:ListFunctions",
                    "lambda:ListProvisionedConcurrencyConfigs",
                    "lambda:GetProvisionedConcurrencyConfig",
                    "lambda:GetFunctionConfiguration",
                    "lambda:PutFunctionConcurrency",
                    "lambda:UpdateFunctionConfiguration",
                    "rds:DescribeDBInstances",
                    "rds:ModifyDBInstance",
                    "s3:ListAllMyBuckets",
                    "s3:GetLifecycleConfiguration",
                    "s3:PutLifecycleConfiguration",
                    "cloudwatch:GetMetricStatistics",
                    "cloudwatch:PutMetricData",
                ],
                resources=["*"],
            )
        )
        api_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "scheduler:CreateSchedule",
                    "scheduler:UpdateSchedule",
                    "scheduler:DeleteSchedule",
                    "scheduler:GetSchedule",
                ],
                resources=["*"],
            )
        )

        self.api = apigw.LambdaRestApi(
            self,
            "BrickwatchApiGateway",
            handler=api_fn,  # type: ignore[arg-type]
            proxy=False,
            deploy_options=apigw.StageOptions(stage_name="prod"),
            default_method_options=apigw.MethodOptions(api_key_required=True),
            rest_api_name="BrickwatchApi",
        )

        v1 = self.api.root.add_resource("v1")
        chat = v1.add_resource("chat")
        chat.add_cors_preflight(
            allow_origins=apigw.Cors.ALL_ORIGINS,
            allow_headers=apigw.Cors.DEFAULT_HEADERS,
            allow_methods=["POST", "OPTIONS"],
        )
        chat.add_method("POST", api_key_required=False)

        analyze = v1.add_resource("analyze")
        analyze.add_cors_preflight(
            allow_origins=apigw.Cors.ALL_ORIGINS,
            allow_headers=apigw.Cors.DEFAULT_HEADERS,
            allow_methods=["GET", "OPTIONS"],
        )
        analyze.add_method("GET", api_key_required=False)

        recommend = v1.add_resource("recommend")
        recommend.add_cors_preflight(
            allow_origins=apigw.Cors.ALL_ORIGINS,
            allow_headers=apigw.Cors.DEFAULT_HEADERS,
            allow_methods=["GET", "OPTIONS"],
        )
        recommend.add_method("GET", api_key_required=False)

        automation = v1.add_resource("automation")
        automation.add_cors_preflight(
            allow_origins=apigw.Cors.ALL_ORIGINS,
            allow_headers=apigw.Cors.DEFAULT_HEADERS,
            allow_methods=["POST", "OPTIONS"],
        )
        automation.add_method("POST", api_key_required=False)

        self.api.root.add_proxy(any_method=True)

        self.api_key_value = secrets.token_hex(16)
        key = apigw.ApiKey(self, "BrickwatchApiKey", value=self.api_key_value)
        plan = apigw.UsagePlan(
            self,
            "BrickwatchUsagePlan",
            name="BrickwatchPlan",
            throttle=apigw.ThrottleSettings(rate_limit=50, burst_limit=10),
        )
        plan.add_api_stage(api=self.api, stage=self.api.deployment_stage)
        plan.add_api_key(key)

        CfnOutput(self, "ApiUrl", value=self.api.url)
        CfnOutput(self, "ApiKey", value=self.api_key_value)
