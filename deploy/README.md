# AlphaCent AWS Deployment

## Overview

```
git push → GitHub Actions → SSH to EC2 → deploy + restart
```

## First-Time Setup (30 minutes)

### Step 1: Create GitHub repo

```bash
# On your Mac, in the project directory:
git init
git add .
git commit -m "Initial commit"
git remote add origin git@github.com:pablomart83/alphacent.git
git branch -M main
git push -u origin main
```

### Step 2: Provision AWS infrastructure (CloudShell)

1. Open AWS Console → switch to **eu-west-1 (Ireland)**
2. Open CloudShell (terminal icon in top nav)
3. Copy-paste the contents of `deploy/aws-setup.sh` into CloudShell
4. Follow the prompts to enter your secret values
5. **Download the .pem key file**: Actions → Download → `/tmp/alphacent-key.pem`
6. Save the PostgreSQL and Admin passwords printed at the end

### Step 3: Configure the server (CloudShell)

1. Wait ~3 minutes after Step 2 for EC2 packages to install
2. Copy-paste the contents of `deploy/server-config.sh` into CloudShell
3. Wait for it to complete

### Step 4: Add GitHub secrets

Go to: GitHub repo → Settings → Secrets and variables → Actions → New repository secret

| Secret Name    | Value                                    |
|----------------|------------------------------------------|
| `EC2_HOST`     | Your Elastic IP (from Step 2 output)     |
| `EC2_SSH_KEY`  | Contents of `alphacent-key.pem` file     |
| `EC2_USER`     | `ubuntu`                                 |
| `AWS_REGION`   | `eu-west-1`                              |

### Step 5: Trigger first deploy

```bash
git push origin main
```

Check: GitHub repo → Actions tab → watch the deploy run

### Step 6: Migrate your data (from your Mac)

```bash
bash deploy/migrate-data.sh <EC2_IP> ~/path/to/alphacent-key.pem
```

### Step 7: Verify

Open `http://<EC2_IP>` in your browser. Login with the admin password from Step 2.

## Ongoing Deployments

Just push to main:

```bash
git add .
git commit -m "your changes"
git push
```

GitHub Actions automatically deploys to EC2.

## Manual Operations

```bash
# SSH into server
ssh -i ~/path/to/alphacent-key.pem ubuntu@<EC2_IP>

# View logs
journalctl -u alphacent -f

# Restart service
sudo systemctl restart alphacent

# Check health
curl http://localhost:8000/health

# View app logs
tail -f /home/ubuntu/alphacent/logs/alphacent.log
```

## Cost

~$35-40/month (t3.medium + 30GB EBS + Secrets Manager + S3 backups)
