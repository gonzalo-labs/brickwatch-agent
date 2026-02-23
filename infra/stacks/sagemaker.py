import os

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_sagemaker as sagemaker
from constructs import Construct


class SageMakerStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        region = Stack.of(self).region or "us-east-1"
        image_repo_account = "763104351884"
        image_repo_name = "pytorch-inference"
        image_uri = (
            f"{image_repo_account}.dkr.ecr.{region}.amazonaws.com/{image_repo_name}"
            ":2.5.1-cpu-py311-ubuntu22.04-sagemaker"
        )

        model_bucket = s3.Bucket(
            self,
            "BrickwatchModelBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        deploy = s3deploy.BucketDeployment(
            self,
            "UploadModelTarGz",
            destination_bucket=model_bucket,
            destination_key_prefix="model",
            sources=[
                s3deploy.Source.asset(
                    os.path.join(os.path.dirname(__file__), "..", "..", "sagemaker_artifacts")
                )
            ],
            retain_on_delete=False,
        )

        sm_role = iam.Role(
            self,
            "BrickwatchSageMakerRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),  # type: ignore[arg-type]
        )

        model_bucket.grant_read(sm_role)

        sm_role.add_to_policy(
            iam.PolicyStatement(actions=["ecr:GetAuthorizationToken"], resources=["*"])
        )
        sm_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:DescribeImages",
                ],
                resources=[
                    f"arn:aws:ecr:{region}:{image_repo_account}:repository/{image_repo_name}"
                ],
            )
        )

        model_data_url = model_bucket.s3_url_for_object("model/model.tar.gz")

        model = sagemaker.CfnModel(
            self,
            "BrickwatchModel",
            execution_role_arn=sm_role.role_arn,
            primary_container=sagemaker.CfnModel.ContainerDefinitionProperty(
                image=image_uri,
                mode="SingleModel",
                model_data_url=model_data_url,
                environment={
                    "SAGEMAKER_PROGRAM": "inference.py",
                    "SAGEMAKER_SUBMIT_DIRECTORY": "/opt/ml/model/code",
                },
            ),
        )
        model.node.add_dependency(deploy)

        endpoint_config = sagemaker.CfnEndpointConfig(
            self,
            "BrickwatchEndpointConfig",
            production_variants=[
                sagemaker.CfnEndpointConfig.ProductionVariantProperty(
                    initial_instance_count=1,
                    instance_type="ml.m5.large",
                    model_name=model.attr_model_name,
                    initial_variant_weight=1.0,
                    variant_name="AllTraffic",
                )
            ],
        )

        endpoint = sagemaker.CfnEndpoint(
            self,
            "BrickwatchEndpoint",
            endpoint_config_name=endpoint_config.attr_endpoint_config_name,
        )

        CfnOutput(self, "SageMakerEndpointName", value=endpoint.ref)
        CfnOutput(self, "ModelBucketName", value=model_bucket.bucket_name)
