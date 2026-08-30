# v2 Phase 1 — AWS Foundations

## Naming convention (fixed as of this phase)
Project name across everything — local folder, AWS resources, GitHub repo —
is **EcoChainAI**. S3 buckets use the prefix `ecochainai-`, the IAM user is
`EcoChainAI`, the policy is `EcoChainAI_Permissions`, the security group is
`EcoChainAI-sg`. Keep this consistent in every later phase so nothing
mismatches again.

## What this phase does
- Creates a dedicated IAM user (`EcoChainAI`) instead of using your root
  account for everything — root access keys are a real security risk if
  this repo is ever public (it will be, on GitHub).
- Attaches a **least-privilege** policy (`EcoChainAI_Permissions`) — only
  S3, EC2, Bedrock, and budget/monitoring permissions, nothing else. If this
  key ever leaked, the blast radius is limited to this project's resources.
- Sets up budget alerts at $30 / $60 / $90 so you get emailed before your
  $100 credit is at risk, instead of finding out too late.
- Creates a security group with SSH locked to YOUR current IP only (not
  0.0.0.0/0 — an open SSH port to the world is one of the most common ways
  small AWS projects get compromised and cost-drained by crypto miners).
  HTTP/HTTPS are open to the world since the dashboard needs to be public.

## Prereqs
1. Install the AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
2. Run `aws configure` once with your account's root or admin credentials
   (only for this one-time setup — after this script runs, switch to the
   new deployer user for everything else).

## Run it
```bash
chmod +x infra/setup_foundations.sh
./infra/setup_foundations.sh your-email@example.com
```

## After it runs
1. **Save the access key/secret printed in step 3** somewhere safe (password
   manager). It's shown once and can't be retrieved again — if you lose it,
   you'll need to generate a new one via IAM console.
2. Switch your CLI to the new deployer user:
   ```bash
   aws configure --profile ecochainai
   export AWS_PROFILE=ecochainai
   ```
   Use this profile for all remaining v2 phases — don't keep using root.
3. Confirm the budget alert exists: AWS Console -> Billing -> Budgets ->
   `EcoChainAI-monthly`.
4. Note down the `SECURITY_GROUP_ID` printed at the end — needed in Phase 6
   (EC2 deploy).

## Why a policy file instead of clicking through the console
This is `infra/iam-policy-deployer.json` — reviewable, version-controlled,
and re-runnable. Anyone can read exactly what
permissions this project's AWS access has.
("least privilege, defined as code")

## Cost check-in
Nothing in this phase costs money by itself — IAM users, budget alarms, and
security groups are free. Cost starts in later phases (S3 storage, EC2
compute, Bedrock inference).


# v2 Phase 3 — S3 Data Lake

## What's in the bucket, and why

```
s3://ecochainai-data-<your-account-id>/
  raw/                        # M5 CSVs — provenance, where the pipeline starts
    sales_train_validation.csv
    calendar.csv
    sell_prices.csv
  processed/                  # final artifacts — what the live app actually needs
    forecasts.parquet
    insight_cards.json
```

**Deliberately NOT uploaded:** `warehouse.duckdb` (3.6GB) and `features.parquet`
(951MB). Both are intermediate outputs, fully regenerable from `raw/` +
`python -m src.pipeline.run_day1`. Storing/transferring multi-GB regenerable
files is wasted cost and wasted time — this is a real data-engineering
judgment call worth stating explicitly if asked.

## IMPORTANT — the IAM policy changed, re-apply it

The S3 resource pattern in `iam-policy-deployer.json` was corrected from a
loose `ecochainai-*` wildcard to the actual bucket naming pattern
`ecochainai-data-*` (least privilege — don't grant access to buckets that
don't exist). Since the `EcoChainAI` IAM user already exists from Phase 1,
re-run just the policy attachment to pick up the fix:

```bash
export AWS_PROFILE=ecochainai
aws iam put-user-policy \
  --user-name EcoChainAI \
  --policy-name EcoChainAI_Permissions \
  --policy-document file://infra/iam-policy-deployer.json
```

## Run it

```bash
export AWS_PROFILE=ecochainai
export AWS_REGION=ap-south-2

chmod +x infra/setup_s3.sh infra/upload_to_s3.sh
./infra/setup_s3.sh        # creates the bucket, private + encrypted
./infra/upload_to_s3.sh    # uploads raw CSVs + processed artifacts
```

`setup_s3.sh` writes the actual bucket name to `infra/.bucket_name`
(gitignored — this is account-specific, not something to commit).

## Bucket settings, and why

- **Private, all public access blocked.** This is a data lake feeding an
  internal pipeline, not a public asset — nothing here should be
  browsable/downloadable by a random URL guess.
- **Default encryption (SSE-S3).** No extra cost, standard practice, worth
  having on by default rather than as an afterthought.
- **No versioning.** Keeping this simple for v1 — versioning adds cost and
  complexity that isn't earning its keep yet for a single-writer pipeline.
  Worth turning on later if this became a multi-contributor project.

## Cost check

Total upload is roughly 300-450MB (raw CSVs + the two processed files).
S3 Standard storage is about $0.023/GB/month — this bucket costs a few
cents a month, not a meaningful line item against your $100 credit.

## What this unlocks later

Phase 6 (EC2 deploy) will have the box pull `processed/forecasts.parquet`
and `processed/insight_cards.json` straight from this bucket at startup,
instead of the container needing the data baked in at build time — this is
what makes the Docker image itself small and fast to deploy/update.
