"""
Runs once when a container starts, BEFORE the dashboard/agents actually
launch. Downloads the processed data artifacts from S3 (put there in
Phase 3) into the container's local data/ folder.

Why not bake the data INTO the image at build time? Two reasons:
1. Keeps the image small and fast to build/push — data can be large and
   changes independently of code.
2. Means updating the data (e.g. after a new model run) doesn't require
   rebuilding and redeploying the image — just re-upload to S3 and restart
   the container.

Run automatically by entrypoint.sh — you don't need to call this by hand.
"""

import os
import sys
from pathlib import Path

import boto3

DATA_DIR = Path("/app/data")
BUCKET_NAME_FILE = Path("/app/infra/.bucket_name")


def get_bucket_name() -> str:
    # env var takes priority (this is how docker-compose/EC2 will set it)
    if os.environ.get("S3_BUCKET"):
        return os.environ["S3_BUCKET"]
    if BUCKET_NAME_FILE.exists():
        return BUCKET_NAME_FILE.read_text().strip()
    print("ERROR: no S3_BUCKET env var set and infra/.bucket_name not found.")
    sys.exit(1)


def main() -> None:
    bucket = get_bucket_name()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-south-2"))

    files = {
        "processed/forecasts.parquet": DATA_DIR / "forecasts.parquet",
        "processed/insight_cards.json": DATA_DIR / "insight_cards.json",
    }

    for key, local_path in files.items():
        print(f"Downloading s3://{bucket}/{key} -> {local_path}")
        s3.download_file(bucket, key, str(local_path))

    print("Data fetch complete.")


if __name__ == "__main__":
    main()
