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
