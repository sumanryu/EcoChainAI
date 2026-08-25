#!/usr/bin/env bash
# Phase 1 — AWS foundations.
# Run this locally where the AWS CLI is installed and configured with your
# ROOT or an existing admin credential (one-time setup only — after this,
# use the new IAM user for everything else).
#
# Prereqs:
#   aws configure   # do this first with your account's admin/root keys
#
# Usage:
#   chmod +x infra/setup_foundations.sh
#   ./infra/setup_foundations.sh your-email@example.com

set -euo pipefail

ALERT_EMAIL="${1:?Usage: ./setup_foundations.sh your-email@example.com}"
AWS_REGION="${AWS_REGION:-us-east-1}"
IAM_USER="EcoChainAI"
POLICY_NAME="EcoChainAI_Permissions"

echo "== 1. Create IAM user (not root) =="
aws iam create-user --user-name "$IAM_USER" || echo "User may already exist, continuing..."

echo "== 2. Attach least-privilege policy =="
aws iam put-user-policy \
  --user-name "$IAM_USER" \
  --policy-name "$POLICY_NAME" \
  --policy-document file://infra/iam-policy-deployer.json

echo "== 3. Create access key for the deployer user =="
echo "   (save this output somewhere safe — the secret is shown ONCE)"
aws iam create-access-key --user-name "$IAM_USER"

echo ""
echo "== 4. Set up budget alerts (30 / 60 / 90 dollars) =="
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

cat > /tmp/budget.json <<EOF
{
  "BudgetName": "EcoChainAI-monthly",
  "BudgetLimit": {"Amount": "100", "Unit": "USD"},
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}
EOF

cat > /tmp/notifications.json <<EOF
[
  {
    "Notification": {"NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN", "Threshold": 30},
    "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "$ALERT_EMAIL"}]
  },
  {
    "Notification": {"NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN", "Threshold": 60},
    "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "$ALERT_EMAIL"}]
  },
  {
    "Notification": {"NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN", "Threshold": 90},
    "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "$ALERT_EMAIL"}]
  }
]
EOF

aws budgets create-budget \
  --account-id "$ACCOUNT_ID" \
  --budget file:///tmp/budget.json \
  --notifications-with-subscribers file:///tmp/notifications.json \
  || echo "Budget may already exist, check AWS console under Billing > Budgets"

echo ""
echo "== 5. Create a security group for the EC2 box (used in a later phase) =="
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text)

SG_ID=$(aws ec2 create-security-group \
  --group-name EcoChainAI-sg \
  --description "EcoChainAI - dashboard + SSH" \
  --vpc-id "$VPC_ID" \
  --query "GroupId" --output text 2>/dev/null || \
  aws ec2 describe-security-groups --filters "Name=group-name,Values=EcoChainAI-sg" --query "SecurityGroups[0].GroupId" --output text)

echo "Security group: $SG_ID"

# SSH only from your current IP, not the world
MY_IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress \
  --group-id "$SG_ID" \
  --protocol tcp --port 22 --cidr "${MY_IP}/32" \
  || echo "SSH rule may already exist"

# HTTP/HTTPS open to the world (this is the public dashboard)
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 80 --cidr 0.0.0.0/0 || true
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 443 --cidr 0.0.0.0/0 || true

echo ""
echo "=================================================================="
echo "DONE. Save these values — you'll need them in later phases:"
echo "  AWS_REGION=$AWS_REGION"
echo "  SECURITY_GROUP_ID=$SG_ID"
echo "  VPC_ID=$VPC_ID"
echo "=================================================================="
echo ""
echo "IMPORTANT NEXT STEP: reconfigure your AWS CLI to use the NEW"
echo "demand-intel-deployer access key from step 3, not your root/admin key,"
echo "for everything else in this project:"
echo "  aws configure --profile ecochainai"
echo "  export AWS_PROFILE=ecochainai"
