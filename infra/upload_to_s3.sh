#!/usr/bin/env bash
# Phase 3 — upload data to S3.
#
# Uploads:
#   - raw M5 CSVs (provenance — where the pipeline started)
#   - forecasts.parquet, insight_cards.json (final artifacts — what the
#     live dashboard/agents actually need)
#
# Deliberately SKIPS warehouse.duckdb (3.6GB) and features.parquet (951MB)
# — both are large intermediates, fully regenerable from raw data + code
# via `python -m src.pipeline.run_day1`. No reason to pay to store/transfer
# them when they're one command away from being rebuilt.
#
# Usage:
#   export AWS_PROFILE=ecochainai
#   ./infra/upload_to_s3.sh

set -euo pipefail

if [ ! -f infra/.bucket_name ]; then
  echo "Run setup_s3.sh first."
  exit 1
fi
BUCKET=$(cat infra/.bucket_name)

echo "== Uploading raw data (provenance) =="
aws s3 sync data/raw/ "s3://${BUCKET}/raw/" \
  --exclude "*" --include "*.csv"

echo "== Uploading processed artifacts (what the live app needs) =="
aws s3 cp data/forecasts.parquet "s3://${BUCKET}/processed/forecasts.parquet"
aws s3 cp data/insight_cards.json "s3://${BUCKET}/processed/insight_cards.json"

echo ""
echo "== Verifying =="
aws s3 ls "s3://${BUCKET}/raw/" --human-readable
aws s3 ls "s3://${BUCKET}/processed/" --human-readable

TOTAL_SIZE=$(aws s3 ls "s3://${BUCKET}" --recursive --human-readable --summarize | tail -2)
echo ""
echo "$TOTAL_SIZE"
