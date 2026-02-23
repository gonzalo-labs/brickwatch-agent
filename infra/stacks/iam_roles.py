from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct


class IamRolesStack(Stack):
    """Shared IAM roles used by Brickwatch runtime components."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        executor_role = iam.Role(
            self,
            "BrickwatchExecutorRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),  # type: ignore[arg-type]
        )
        executor_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )
        executor_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ec2:StopInstances",
                    "ec2:StartInstances",
                    "ec2:ModifyInstanceAttribute",
                    "autoscaling:PutScheduledUpdateGroupAction",
                    "s3:PutLifecycleConfiguration",
                    "s3:GetLifecycleConfiguration",
                    "rds:StopDBInstance",
                    "rds:StartDBInstance",
                    "rds:ModifyDBInstance",
                    "eks:UpdateNodegroupConfig",
                    "eks:DescribeNodegroup",
                ],
                resources=["*"],
                conditions={"StringEquals": {"aws:ResourceTag/project": "rita"}},
            )
        )

        read_role = iam.Role(
            self,
            "BrickwatchReadOnlyRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),  # type: ignore[arg-type]
        )
        read_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )
        read_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ce:*",
                    "athena:*",
                    "glue:*",
                    "s3:Get*",
                    "s3:List*",
                    "compute-optimizer:*",
                    "budgets:View*",
                    "tag:Get*",
                    "cloudwatch:GetMetricData",
                    "cloudwatch:ListMetrics",
                    "rds:Describe*",
                    "eks:List*",
                    "eks:Describe*",
                ],
                resources=["*"],
            )
        )

        CfnOutput(self, "ExecutorRoleArn", value=executor_role.role_arn)
        CfnOutput(self, "ReadOnlyRoleArn", value=read_role.role_arn)

        self.outputs = {
            "executorRoleArn": executor_role.role_arn,
            "readOnlyRoleArn": read_role.role_arn,
        }
