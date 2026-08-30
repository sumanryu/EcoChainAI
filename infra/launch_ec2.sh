#!/usr/bin/env bash
# Phase 6 — launch EC2, no ~/.aws mount needed: the instance gets an IAM
# ROLE instead (this is the "production-correct" version of the local
# Docker credential trick from Phase 4).
#
# Usage:
#   export AWS_PROFILE=ecochainai
#   export AWS_REGION=ap-south-2
#   ./infra/launch_ec2.sh

set -euo pipefail
AWS_REGION="${AWS_REGION:-ap-south-2}"
ROLE_NAME="EcoChainAI-ec2-role"
PROFILE_NAME="EcoChainAI-ec2-profile"
KEY_NAME="ecochainai-key"

echo "== 1. Create IAM role for EC2 (replaces ~/.aws credential files) =="
aws iam create-role --role-name "$ROLE_NAME" \
  --assume-role-policy-document file://infra/ec2-trust-policy.json \
  || echo "Role may already exist, continuing..."

aws iam put-role-policy --role-name "$ROLE_NAME" \
  --policy-name EcoChainAI_Permissions \
  --policy-document file://infra/iam-policy-deployer.json

aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME" \
  || echo "Instance profile may already exist, continuing..."
aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE_NAME" \
  --role-name "$ROLE_NAME" 2>/dev/null || true

echo "== 2. Create SSH key pair (skip if you already have one) =="
if [ ! -f "${KEY_NAME}.pem" ]; then
  aws ec2 create-key-pair --key-name "$KEY_NAME" \
    --query "KeyMaterial" --output text > "${KEY_NAME}.pem"
  chmod 400 "${KEY_NAME}.pem"
  echo "Saved ${KEY_NAME}.pem — keep this safe, needed for SSH."
fi

echo "== 3. Find security group + a free-tier-eligible AMI =="
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=EcoChainAI-sg" \
  --query "SecurityGroups[0].GroupId" --output text)
AMI_ID=$(aws ec2 describe-images --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
  --query "sort_by(Images,&CreationDate)[-1].ImageId" --output text)

echo "== 4. Launch the instance (t3.small, Docker installed via user-data) =="
cat > /tmp/user-data.sh <<'EOF'
#!/bin/bash
apt-get update -y
apt-get install -y docker.io docker-compose-plugin git
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu
EOF

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type t3.small \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --user-data file:///tmp/user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=EcoChainAI}]' \
  --iam-instance-profile Name="$PROFILE_NAME" \
  --query "Instances[0].InstanceId" --output text)

echo "Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text)

echo ""
echo "=================================================================="
echo "Instance running: $INSTANCE_ID"
echo "Public IP: $PUBLIC_IP"
echo "SSH:  ssh -i ${KEY_NAME}.pem ubuntu@${PUBLIC_IP}"
echo "(wait ~1 min after this script finishes for Docker install to complete)"
echo "=================================================================="