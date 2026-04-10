#!/bin/bash
# =============================================================================
# AlphaCent AWS Infrastructure Setup
# =============================================================================
# RUN THIS IN AWS CLOUDSHELL (not your local machine)
#
# Creates: EC2 instance, Security Group, Key Pair, Elastic IP, Secrets Manager,
#          IAM role, S3 backup bucket
#
# After running, you'll need to:
# 1. Download the .pem key file (printed at the end)
# 2. Add GitHub secrets (printed at the end)
# 3. Push code to GitHub to trigger first deploy
# =============================================================================

set -euo pipefail

REGION="eu-west-1"
INSTANCE_TYPE="t3.medium"
KEY_NAME="alphacent-key"
SG_NAME="alphacent-sg"
INSTANCE_NAME="alphacent-trading"
ROLE_NAME="alphacent-ec2-role"
INSTANCE_PROFILE_NAME="alphacent-ec2-profile"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "============================================"
echo "  AlphaCent AWS Infrastructure Setup"
echo "  Region: $REGION | Account: $ACCOUNT_ID"
echo "============================================"

# --- Step 1: Resolve latest Ubuntu 22.04 AMI ---
echo ""
echo "[1/8] Resolving Ubuntu 22.04 LTS AMI..."
AMI_ID=$(aws ec2 describe-images \
    --region "$REGION" \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
              "Name=state,Values=available" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
    --output text)

if [ -z "$AMI_ID" ] || [ "$AMI_ID" = "None" ]; then
    echo "ERROR: Could not find Ubuntu 22.04 AMI"
    exit 1
fi
echo "  AMI: $AMI_ID"

# --- Step 2: Create Key Pair ---
echo ""
echo "[2/8] Creating EC2 key pair..."

if aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$REGION" &>/dev/null; then
    echo "  Key pair '$KEY_NAME' already exists"
    echo "  WARNING: If you lost the .pem file, delete the key pair and re-run this script"
else
    aws ec2 create-key-pair \
        --key-name "$KEY_NAME" \
        --region "$REGION" \
        --query 'KeyMaterial' \
        --output text > /tmp/${KEY_NAME}.pem
    chmod 600 /tmp/${KEY_NAME}.pem
    echo "  Created: /tmp/${KEY_NAME}.pem"
    echo "  >>> DOWNLOAD THIS FILE before CloudShell session expires <<<"
fi

# --- Step 3: Create Security Group ---
echo ""
echo "[3/8] Creating security group..."

VPC_ID=$(aws ec2 describe-vpcs \
    --region "$REGION" \
    --filters "Name=isDefault,Values=true" \
    --query 'Vpcs[0].VpcId' \
    --output text)

SG_ID=$(aws ec2 describe-security-groups \
    --region "$REGION" \
    --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null || echo "None")

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
    SG_ID=$(aws ec2 create-security-group \
        --group-name "$SG_NAME" \
        --description "AlphaCent Trading Platform" \
        --vpc-id "$VPC_ID" \
        --region "$REGION" \
        --query 'GroupId' \
        --output text)

    # SSH
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 22 --cidr 0.0.0.0/0 --region "$REGION"
    # HTTP
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 80 --cidr 0.0.0.0/0 --region "$REGION"
    # HTTPS
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" --protocol tcp --port 443 --cidr 0.0.0.0/0 --region "$REGION"

    echo "  Created: $SG_ID"
else
    echo "  Exists: $SG_ID"
fi

# --- Step 4: Create IAM Role ---
echo ""
echo "[4/8] Creating IAM role..."

if ! aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }' \
        --description "AlphaCent EC2 role" > /dev/null

    # Secrets Manager access
    aws iam put-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-name "alphacent-secrets-access" \
        --policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["secretsmanager:GetSecretValue","secretsmanager:DescribeSecret"],
                "Resource": "arn:aws:secretsmanager:'"$REGION"':'"$ACCOUNT_ID"':secret:alphacent/*"
            }]
        }'

    # S3 backup access
    aws iam put-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-name "alphacent-s3-backup-access" \
        --policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["s3:PutObject","s3:GetObject","s3:ListBucket"],
                "Resource": ["arn:aws:s3:::alphacent-backups-*","arn:aws:s3:::alphacent-backups-*/*"]
            }]
        }'

    echo "  Created role: $ROLE_NAME"
else
    echo "  Role exists: $ROLE_NAME"
fi

# Instance profile
if ! aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" &>/dev/null; then
    aws iam create-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" > /dev/null
    aws iam add-role-to-instance-profile \
        --instance-profile-name "$INSTANCE_PROFILE_NAME" \
        --role-name "$ROLE_NAME"
    echo "  Created instance profile (waiting 10s for propagation...)"
    sleep 10
else
    echo "  Instance profile exists"
fi

# --- Step 5: Store secrets ---
echo ""
echo "[5/8] Storing secrets in Secrets Manager..."
echo "  You'll be prompted to enter each secret value."

store_secret() {
    local name="$1"
    local description="$2"
    local value="$3"

    if aws secretsmanager describe-secret --secret-id "$name" --region "$REGION" &>/dev/null; then
        aws secretsmanager put-secret-value \
            --secret-id "$name" --secret-string "$value" --region "$REGION" > /dev/null
        echo "  Updated: $name"
    else
        aws secretsmanager create-secret \
            --name "$name" --description "$description" \
            --secret-string "$value" --region "$REGION" > /dev/null
        echo "  Created: $name"
    fi
}

# Generate passwords
PG_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)
ADMIN_PASSWORD=$(openssl rand -base64 16 | tr -d '/+=' | head -c 16)

echo ""
echo "  Enter your secrets (copy from your local config files):"
echo ""

read -p "  Encryption key (from config/.encryption_key): " ENCRYPTION_KEY
read -p "  FMP API key (from autonomous_trading.yaml): " FMP_KEY
read -p "  Alpha Vantage API key: " AV_KEY
read -p "  FRED API key: " FRED_KEY

echo ""
echo "  Paste your eToro credentials JSON (from config/demo_credentials.json):"
echo "  (paste the entire JSON content, then press Enter):"
read -r ETORO_CREDS

store_secret "alphacent/encryption-key" "Fernet encryption key" "$ENCRYPTION_KEY"
store_secret "alphacent/etoro-credentials" "Encrypted eToro credentials" "$ETORO_CREDS"
store_secret "alphacent/fmp-api-key" "FMP API key" "$FMP_KEY"
store_secret "alphacent/alpha-vantage-api-key" "Alpha Vantage API key" "$AV_KEY"
store_secret "alphacent/fred-api-key" "FRED API key" "$FRED_KEY"
store_secret "alphacent/postgres-password" "PostgreSQL password" "$PG_PASSWORD"
store_secret "alphacent/admin-password" "Admin UI password" "$ADMIN_PASSWORD"

echo ""
echo "  ========================================="
echo "  SAVE THESE PASSWORDS:"
echo "  PostgreSQL: $PG_PASSWORD"
echo "  Admin UI:   $ADMIN_PASSWORD"
echo "  ========================================="

# --- Step 6: Launch EC2 ---
echo ""
echo "[6/8] Launching EC2 instance..."

EXISTING_INSTANCE=$(aws ec2 describe-instances \
    --region "$REGION" \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text 2>/dev/null || echo "None")

if [ "$EXISTING_INSTANCE" != "None" ] && [ -n "$EXISTING_INSTANCE" ]; then
    INSTANCE_ID="$EXISTING_INSTANCE"
    echo "  Instance exists: $INSTANCE_ID"
else
    # User data script — runs on first boot to install base packages
    USER_DATA=$(cat << 'USERDATA'
#!/bin/bash
set -e

# Add PostgreSQL 16 repo
sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget -qO- https://www.postgresql.org/media/keys/ACCC4CF8.asc | tee /etc/apt/trusted.gpg.d/pgdg.asc > /dev/null

# Add Node.js 20 repo
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3.11 python3.11-venv python3.11-dev \
    postgresql-16 postgresql-client-16 \
    nginx certbot python3-certbot-nginx \
    git build-essential libpq-dev \
    nodejs jq

# Signal completion
touch /tmp/userdata-complete
USERDATA
)

    INSTANCE_ID=$(aws ec2 run-instances \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --security-group-ids "$SG_ID" \
        --iam-instance-profile Name="$INSTANCE_PROFILE_NAME" \
        --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30,"VolumeType":"gp3","Encrypted":true}}]' \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME}]" \
        --user-data "$USER_DATA" \
        --region "$REGION" \
        --query 'Instances[0].InstanceId' \
        --output text)

    echo "  Launched: $INSTANCE_ID"
    echo "  Waiting for running state..."
    aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
fi

# --- Step 7: Elastic IP ---
echo ""
echo "[7/8] Setting up Elastic IP..."

EXISTING_EIP=$(aws ec2 describe-addresses \
    --region "$REGION" \
    --filters "Name=instance-id,Values=$INSTANCE_ID" \
    --query 'Addresses[0].PublicIp' \
    --output text 2>/dev/null || echo "None")

if [ "$EXISTING_EIP" != "None" ] && [ -n "$EXISTING_EIP" ]; then
    PUBLIC_IP="$EXISTING_EIP"
    echo "  Exists: $PUBLIC_IP"
else
    ALLOC_ID=$(aws ec2 allocate-address --domain vpc --region "$REGION" --query 'AllocationId' --output text)
    aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" --region "$REGION" > /dev/null
    PUBLIC_IP=$(aws ec2 describe-addresses --allocation-ids "$ALLOC_ID" --region "$REGION" --query 'Addresses[0].PublicIp' --output text)
    echo "  Allocated: $PUBLIC_IP"
fi

# --- Step 8: Create S3 backup bucket ---
echo ""
echo "[8/8] Creating S3 backup bucket..."
BUCKET_NAME="alphacent-backups-${ACCOUNT_ID}"
aws s3 mb "s3://${BUCKET_NAME}" --region "$REGION" 2>/dev/null || echo "  Bucket exists"
echo "  Bucket: $BUCKET_NAME"

# --- Summary ---
echo ""
echo "============================================"
echo "  AWS Infrastructure Ready"
echo "============================================"
echo ""
echo "  Instance:    $INSTANCE_ID"
echo "  Public IP:   $PUBLIC_IP"
echo "  Region:      $REGION"
echo ""
echo "  NEXT STEPS:"
echo ""
echo "  1. DOWNLOAD the key file from CloudShell:"
echo "     Click Actions → Download file → /tmp/${KEY_NAME}.pem"
echo "     Save it somewhere safe on your Mac"
echo ""
echo "  2. Wait ~3 minutes for EC2 user-data to finish installing packages"
echo ""
echo "  3. Run the server config script from CloudShell:"
echo "     (paste the server-config.sh script contents)"
echo ""
echo "  4. Add these GitHub repository secrets:"
echo "     Settings → Secrets → Actions → New repository secret"
echo ""
echo "     EC2_HOST          = $PUBLIC_IP"
echo "     EC2_SSH_KEY       = (contents of /tmp/${KEY_NAME}.pem)"
echo "     EC2_USER          = ubuntu"
echo "     AWS_REGION        = $REGION"
echo ""
echo "  5. Push code to GitHub → auto-deploys via GitHub Actions"
echo ""
echo "  6. From your Mac, migrate PostgreSQL data:"
echo "     pg_dump -h localhost alphacent | gzip > /tmp/alphacent.sql.gz"
echo "     scp -i ~/path/to/${KEY_NAME}.pem /tmp/alphacent.sql.gz ubuntu@${PUBLIC_IP}:/tmp/"
echo "     ssh -i ~/path/to/${KEY_NAME}.pem ubuntu@${PUBLIC_IP}"
echo "     # Then on EC2: see migrate-data instructions"
echo ""
echo "============================================"
