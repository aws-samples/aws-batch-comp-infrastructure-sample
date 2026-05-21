# AWS Setup

This page covers creating an AWS account, configuring credentials, and understanding costs.

## Creating an AWS Account

We **strongly recommend** using a dedicated AWS account for your competition-related work.
This isolates competition resources from other projects. 
You can reuse accounts from prior years.

### Steps to Create an Account

1. Go to [aws.amazon.com](https://aws.amazon.com)
2. Click "Create Account" in the top-right corner
3. Provide:
   - Credit card number
   - Phone number
   - Physical address
   - Email address

### Email Address Tips

Every AWS account requires a unique email address. If you already have an AWS account
with your email, you can use plus addressing:

- Original: `email@university.edu`
- For SAT/SMT: `email+satcomp2026@university.edu`

This creates a "new" email address that routes to your existing inbox.

<!--
**For competitors:** You must use an institutional (`.edu`) email to receive AWS credits.
-->

### Finding Your Account ID

You'll need your account ID for various operations. Find it by:

1. Sign in to [AWS Console](https://console.aws.amazon.com)
2. Click the dropdown in the top-right corner
3. Account ID is displayed at the top

Write this down for reference.

## Configuring Credentials

### For Non-AWS Employees

You'll use a root-level access key to manage AWS resources.

1. Go to the [IAM Console](https://console.aws.amazon.com/iamv2/)
2. Click "My Security Credentials" on the right
3. Scroll to "Access keys"
4. Click "Create access key"
5. Copy both the Access Key ID and Secret Access Key

Create `~/.aws/credentials` with:

```ini
[default]
aws_access_key_id=YOUR_ACCESS_KEY
aws_secret_access_key=YOUR_SECRET_KEY
region=us-east-1
```

Verify configuration:
```bash
aws sts get-caller-identity
```

## Region Selection

We recommend using `us-east-1` for availability of larger EC2 instance types.

You can use any region, but once you deploy, the region must stay fixed. Changing
regions requires destroying all resources and redeploying.

To use a different region, update `config.yml`:
```yaml
region: us-west-2
```

Then bootstrap for the new region:
```bash
./satcomp.py bootstrap
```

## Understanding Costs

### Always-On Costs (while deployed)

| Resource | Cost | When Active |
|----------|------|-------------|
| VPC Endpoints | ~$3/day | From `provision` until `teardown all` |
| NAT Gateway | ~$1/day | From `provision` until `teardown all` |

**Total baseline:** ~$4/day while infrastructure is deployed

### Per-Use Costs

| Resource | Cost | Notes |
|----------|------|-------|
| EC2 Instances | Varies by type | Only while allocated |
| S3 Storage | ~$0.023/GB/month | Formulas and results |
| SQS Messages | ~$0.40/million | Negligible |
| Data Transfer | ~$0.09/GB | S3 to EC2 in same region is free |

### EC2 Instance Pricing (us-east-1, on-demand)

| Instance Type | vCPUs | Memory | ~Cost/Hour |
|---------------|-------|--------|------------|
| m6i.xlarge | 4 | 16 GB | $0.19 |
| m6i.2xlarge | 8 | 32 GB | $0.38 |
| m6i.4xlarge | 16 | 64 GB | $0.77 |
| m6i.8xlarge | 32 | 128 GB | $1.54 |

### Cost Example: Small Competition Run

- 10 solvers x m6i.xlarge x 8 hours = $15.20
- VPC endpoints for 1 day = $4.00
- S3 storage (10 GB) = $0.23
- **Total:** ~$20

### Cost Example: Full Competition

- 50 solvers x m6i.4xlarge x 24 hours = $924
- VPC endpoints for 3 days = $12
- S3 storage (100 GB) = $2.30
- **Total:** ~$940

### Managing Costs

1. **Always destroy when done:**
   ```bash
   ./satcomp.py teardown all
   ```

2. **Stop solvers promptly:** Running instances cost money even with empty queues:
   ```bash
   ./satcomp.py terminate-instances
   ```

3. **Use `standby-instances` for iteration:** Keeps EC2 instances ready without running tasks

4. **Monitor AWS Cost Explorer:** Set up billing alerts in AWS Console

<!--
## For Competitors: AWS Credits

Competition participants receive AWS credits. To receive credits:

1. Create your AWS account with an institutional email
2. Email your account ID to [solver-competitions@amazon.com](mailto:solver-competitions@amazon.com)

Credits will be applied to your account before the competition.
-->

## Next Steps

After setting up your AWS account, your next step is to begin [solver packaging](/docs/solver-preparation/README.md).
