from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_autoscaling as autoscaling,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as elbv2_targets,
    CfnOutput,
    
)
from constructs import Construct

class GameStudioStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(
            self, "VPC",
            max_azs=1,
            nat_gateways=0
        )
        
        data = open("./p4d-files/configure-p4d.sh", "rb").read()
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(str(data, 'utf-8'))

        sg = ec2.SecurityGroup(
            self, "SecurityGroup",
            vpc=vpc,
            description="Allow tcp traffic from NLB to instances over port 1666",
            security_group_name="HelixCore SecurityGroup",
            allow_all_outbound=True,
        )

        sg.add_ingress_rule(
            ec2.Peer.ipv4('0.0.0.0/0'),
            ec2.Port.tcp(1666),
            "allow tcp traffic from nlb"
        )
        
        machine_image = ec2.GenericLinuxImage({
            "us-east-1": "ami-0e09d7c1e4eb188b0",
            "us-east-2": "ami-07b3240efb4d0fdc9",
            "us-west-1": "ami-0650ca268c0db8b36",
            "us-west-2": "ami-08480a22ed805bcb0",
        })
        
        p4d_instance = ec2.Instance(
            self, "P4DInstance",
            vpc=vpc,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.LARGE
            ),
            machine_image=machine_image,
            user_data=user_data,
            security_group=sg,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/sdb",
                    volume=ec2.BlockDeviceVolume.ebs(24)
                ),
                ec2.BlockDevice(
                    device_name="/dev/sdc",
                    volume=ec2.BlockDeviceVolume.ebs(24)
                    )
            ]
        )
        instance_target = elbv2_targets.InstanceTarget(p4d_instance, 1666)

        # Instance Role and SSM Managed Policy
        role = iam.Role(self, "CDKInstanceSSM", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"))

        role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"))

        lb = elbv2.NetworkLoadBalancer(
            self, "LB",
            vpc=vpc,
            internet_facing=True
        )

        listener = lb.add_listener(
            "PublicListener",
            port=1666,
        )

        health_check = elbv2.HealthCheck(
            protocol=elbv2.Protocol.TCP
        )

        listener.add_targets(
            "Ec2TargetGroup",
            port=1666,
            targets=[instance_target],
            health_check=health_check,
            protocol=elbv2.Protocol.TCP
        )

        CfnOutput(self, "LoadBalancer", export_name="LoadBalancer", value=lb.load_balancer_dns_name)
        CfnOutput(self, "InstanceID", export_name="InstanceID", value=p4d_instance.instance_id)

