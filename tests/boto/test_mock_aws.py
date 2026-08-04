import pytest
import json
import tempfile
from pathlib import Path
from unittest import mock
from moto import mock_aws
import boto3

from alpaca.remote_controller import RemoteController


@pytest.fixture
def config_file():
    """Create a temporary config file"""
    config = {
        "AWS_REGION": "us-east-1",
        "AMI_ID": "ami-12345678",
        "INSTANCE_TYPE": "t3.small",
        "SECURITY_GROUP_ID": "sg-12345678",
        "SUBNET_ID": "subnet-12345678",
        "DISK_GB": 50,
        "EC2_NAME": "test-instance",
        "MAX_LIFETIME_HOURS": 1,
        "OASISLMF_VERSION": "1.0.0"
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        f.flush()  # Ensure data is written to disk
        config_path = f.name

    yield config_path
    Path(config_path).unlink()


@mock_aws
def test_remote_controller_creates_ec2_instance(config_file):
    """Test that RemoteController successfully creates an EC2 instance"""

    # Set up moto's mock AWS environment
    ec2 = boto3.client('ec2', region_name='us-east-1')

    # Create VPC and networking (required for EC2)
    vpc = ec2.create_vpc(CidrBlock='10.0.0.0/16')
    subnet = ec2.create_subnet(VpcId=vpc['Vpc']['VpcId'], CidrBlock='10.0.1.0/24')
    sg = ec2.create_security_group(
        GroupName='test-sg',
        Description='Test security group',
        VpcId=vpc['Vpc']['VpcId']
    )

    # Update config with real moto IDs
    with open(config_file, 'r') as f:
        config = json.load(f)
    config['SUBNET_ID'] = subnet['Subnet']['SubnetId']
    config['SECURITY_GROUP_ID'] = sg['GroupId']
    with open(config_file, 'w') as f:
        json.dump(config, f)

    # Create controller (but mock SSH since we can't actually connect)
    controller = RemoteController(config_file, required_config=[], optional_config=[])

    # Mock the SSH-related methods since moto doesn't run actual instances
    controller._wait_for_ssh = mock.Mock(return_value=mock.Mock())
    controller.run_commands = mock.Mock()

    # Test instance creation
    controller.setup_instance()

    # Verify instance was created
    assert controller.instance_id is not None
    assert controller.ec2 is not None

    # Verify instance exists in moto
    instances = ec2.describe_instances(InstanceIds=[controller.instance_id])
    assert len(instances['Reservations']) == 1
    instance = instances['Reservations'][0]['Instances'][0]

    # Verify instance configuration
    assert instance['InstanceType'] == 't3.small'
    assert instance['ImageId'] == 'ami-12345678'
    assert instance['State']['Name'] in ['pending', 'running']

    # Verify tags
    tags = {tag['Key']: tag['Value'] for tag in instance['Tags']}
    assert tags['Name'] == 'test-instance'
    assert 'ALPACA_END_TIME' in tags

    # Verify block device mapping exists (moto may not populate all fields)
    assert len(instance['BlockDeviceMappings']) > 0
    assert 'Ebs' in instance['BlockDeviceMappings'][0]

    # Cleanup
    controller.shutdown()

    # Verify instance was terminated
    instances = ec2.describe_instances(InstanceIds=[controller.instance_id])
    instance_state = instances['Reservations'][0]['Instances'][0]['State']['Name']
    assert instance_state in ['shutting-down', 'terminated']


@mock_aws
def test_remote_controller_with_iam_role(config_file):
    """Test that RemoteController handles IAM instance profiles correctly"""

    # Set up AWS mocks
    ec2 = boto3.client('ec2', region_name='us-east-1')
    iam = boto3.client('iam', region_name='us-east-1')

    # Create IAM role and instance profile
    iam.create_role(
        RoleName='test-role',
        AssumeRolePolicyDocument=json.dumps({
            'Version': '2012-10-17',
            'Statement': [{
                'Effect': 'Allow',
                'Principal': {'Service': 'ec2.amazonaws.com'},
                'Action': 'sts:AssumeRole'
            }]
        })
    )
    iam.create_instance_profile(InstanceProfileName='test-profile')
    iam.add_role_to_instance_profile(
        InstanceProfileName='test-profile',
        RoleName='test-role'
    )

    # Create VPC resources
    vpc = ec2.create_vpc(CidrBlock='10.0.0.0/16')
    subnet = ec2.create_subnet(VpcId=vpc['Vpc']['VpcId'], CidrBlock='10.0.1.0/24')
    sg = ec2.create_security_group(
        GroupName='test-sg',
        Description='Test',
        VpcId=vpc['Vpc']['VpcId']
    )
    # Update config
    with open(config_file, 'r') as f:
        config = json.load(f)
    config['SUBNET_ID'] = subnet['Subnet']['SubnetId']
    config['SECURITY_GROUP_ID'] = sg['GroupId']
    config['IAM_INSTANCE_PROFILE'] = 'test-profile'
    with open(config_file, 'w') as f:
        json.dump(config, f)

    # Test
    controller = RemoteController(config_file)
    controller._wait_for_ssh = mock.Mock(return_value=mock.Mock())
    controller.run_commands = mock.Mock()

    controller.setup_instance()

    # Verify IAM instance profile was attached
    instances = ec2.describe_instances(InstanceIds=[controller.instance_id])
    instance = instances['Reservations'][0]['Instances'][0]
    assert 'IamInstanceProfile' in instance
    assert instance['IamInstanceProfile']['Arn'].endswith('test-profile')

    controller.shutdown()


@mock_aws
def test_remote_controller_context_manager(config_file):
    """Test that context manager properly sets up and tears down resources"""

    # Set up moto environment
    ec2 = boto3.client('ec2', region_name='us-east-1')
    vpc = ec2.create_vpc(CidrBlock='10.0.0.0/16')
    subnet = ec2.create_subnet(VpcId=vpc['Vpc']['VpcId'], CidrBlock='10.0.1.0/24')
    sg = ec2.create_security_group(
        GroupName='test-sg',
        Description='Test',
        VpcId=vpc['Vpc']['VpcId']
    )
    # Update config
    with open(config_file, 'r') as f:
        config = json.load(f)
    config['SUBNET_ID'] = subnet['Subnet']['SubnetId']
    config['SECURITY_GROUP_ID'] = sg['GroupId']
    with open(config_file, 'w') as f:
        json.dump(config, f)

    instance_id = None

    # Test context manager
    with mock.patch.object(RemoteController, '_wait_for_ssh', return_value=mock.Mock()):
        with mock.patch.object(RemoteController, 'run_commands'):
            with RemoteController(config_file) as controller:
                instance_id = controller.instance_id
                assert instance_id is not None

                # Verify instance is running
                instances = ec2.describe_instances(InstanceIds=[instance_id])
                state = instances['Reservations'][0]['Instances'][0]['State']['Name']
                assert state in ['pending', 'running']

    # After context manager exits, instance should be terminated
    instances = ec2.describe_instances(InstanceIds=[instance_id])
    state = instances['Reservations'][0]['Instances'][0]['State']['Name']
    assert state in ['shutting-down', 'terminated']


@mock_aws
def test_remote_controller_config_from_environment():
    """Test that configuration can be overridden by environment variables"""
    import os

    # Minimal config file
    config = {
        "AWS_REGION": "us-east-1",
        "AMI_ID": "ami-12345678",
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        config_file = f.name

    # Set up AWS mocks
    ec2 = boto3.client('ec2', region_name='us-east-1')
    vpc = ec2.create_vpc(CidrBlock='10.0.0.0/16')
    subnet = ec2.create_subnet(VpcId=vpc['Vpc']['VpcId'], CidrBlock='10.0.1.0/24')
    sg = ec2.create_security_group(
        GroupName='test-sg',
        Description='Test',
        VpcId=vpc['Vpc']['VpcId']
    )
    # Override via environment variables
    os.environ['ALPACA_SUBNET_ID'] = subnet['Subnet']['SubnetId']
    os.environ['ALPACA_SECURITY_GROUP_ID'] = sg['GroupId']
    os.environ['ALPACA_DISK_GB'] = '200'

    try:
        required = [
            ("SUBNET_ID", "", ""),
            ("SECURITY_GROUP_ID", "", "")
        ]
        optional = [("DISK_GB", "", "")]

        controller = RemoteController(config_file, required, optional)

        # Verify config was loaded from environment
        assert controller.config['SUBNET_ID'] == subnet['Subnet']['SubnetId']
        assert controller.config['SECURITY_GROUP_ID'] == sg['GroupId']
        assert controller.config['DISK_GB'] == '200'

    finally:
        # Clean up environment
        del os.environ['ALPACA_SUBNET_ID']
        del os.environ['ALPACA_SECURITY_GROUP_ID']
        del os.environ['ALPACA_DISK_GB']
        Path(config_file).unlink()


@mock_aws
def test_remote_controller_shutdown_without_instance():
    """Test that shutdown handles case when no instance was created"""
    config = {
        "AWS_REGION": "us-east-1",
        "AMI_ID": "ami-12345678",
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        config_file = f.name

    try:
        controller = RemoteController(config_file)
        # Shutdown without creating instance should not raise
        controller.shutdown()

        # Verify no errors
        assert controller.instance_id is None

    finally:
        Path(config_file).unlink()
