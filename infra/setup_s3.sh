#!/usr/bin/env bash
# Phase 3 — create the S3 data lake bucket.
#
# Usage:
#   export AWS_PROFILE=ecochainai
#   ./infra/setup_s3.sh

set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-south-2}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="ecochainai-data-${ACCOUNT_ID}"   # account ID suffix guarantees global uniqueness

echo "== Creating bucket: $BUCKET (region: $AWS_REGION) =="
aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION" \
  || echo "Bucket may already exist, continuing..."

echo "== Blocking all public access (this is a private data lake, not a static site) =="
aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "== Enabling default encryption (SSE-S3, no extra cost) =="
aws s3api put-bucket-encryption \
  --bucket "$BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

echo ""
echo "=================================================================="
echo "Bucket ready: $BUCKET"
echo "Save this — you'll need it for upload_to_s3.sh and Phase 6 (EC2)."
echo "=================================================================="
echo "$BUCKET" > infra/.bucket_name
