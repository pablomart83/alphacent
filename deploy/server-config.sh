#!/bin/bash
# =============================================================================
# AlphaCent Server Configuration
# =============================================================================
# RUN THIS IN AWS CLOUDSHELL after aws-setup.sh completes
# and after waiting ~3 minutes for EC2 user-data to finish
#
# This SSHs into the EC2 instance and configures:
# - PostgreSQL database + user
# - Nginx reverse proxy
# - systemd service
# - Log rotation
# - Backup cron
# - Fetches secrets from Secrets Manager
# =============================================================================

set -euo pipefail

REGION="eu-west-1"
KEY_FILE="/tmp/alphacent-key.pem"

# Get instance IP
PUBLIC_IP=$(aws ec2 describe-instances \
    --region "$REGION" \
    --filters "Name=tag:Name,Values=alphacent-trading" "Name=instance-state-name,Values=running" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

if [ -z "$PUBLIC_IP" ] || [ "$PUBLIC_IP" = "None" ]; then
    echo "ERROR: Could not find running alphacent-trading instance"
    exit 1
fi

echo "============================================"
echo "  Configuring server: $PUBLIC_IP"
echo "============================================"

# Wait for user-data to complete
echo ""
echo "[1/4] Waiting for EC2 initialization..."
for i in $(seq 1 60); do
    if ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@"$PUBLIC_IP" "test -f /tmp/userdata-complete" &>/dev/null; then
        echo "  EC2 initialization complete"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "  WARNING: Timed out waiting for user-data. Packages may still be installing."
        echo "  Continuing anyway..."
    fi
    echo "  Waiting... ($i/60)"
    sleep 10
done

# Get PostgreSQL password from Secrets Manager
PG_PASSWORD=$(aws secretsmanager get-secret-value \
    --secret-id alphacent/postgres-password \
    --region "$REGION" \
    --query SecretString --output text)

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# --- Step 2: Configure PostgreSQL ---
echo ""
echo "[2/4] Configuring PostgreSQL..."

ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no ubuntu@"$PUBLIC_IP" << REMOTE_PG
set -euo pipefail

# Create user and database
sudo -u postgres psql -c "DO \\\$\\\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'alphacent_user') THEN CREATE ROLE alphacent_user WITH LOGIN PASSWORD '${PG_PASSWORD}'; END IF; END \\\$\\\$;" 2>/dev/null
sudo -u postgres psql -c "SELECT 1 FROM pg_database WHERE datname = 'alphacent'" | grep -q 1 || sudo -u postgres createdb alphacent -O alphacent_user

# Configure authentication
PG_HBA=\$(sudo -u postgres psql -t -c "SHOW hba_file" | tr -d ' ')
if ! grep -q "alphacent_user" "\$PG_HBA"; then
    sudo sed -i '/^# IPv4 local connections/a host    alphacent    alphacent_user    127.0.0.1/32    scram-sha-256' "\$PG_HBA"
    sudo systemctl reload postgresql
fi

echo "PostgreSQL ready"
REMOTE_PG

# --- Step 3: Configure Nginx + systemd ---
echo ""
echo "[3/4] Configuring Nginx and systemd..."

ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no ubuntu@"$PUBLIC_IP" << 'REMOTE_SERVICES'
set -euo pipefail

# --- systemd service ---
sudo tee /etc/systemd/system/alphacent.service > /dev/null << 'SVCEOF'
[Unit]
Description=AlphaCent Trading Backend
After=postgresql.service network.target
Wants=postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/alphacent
EnvironmentFile=/home/ubuntu/alphacent/.env.production
ExecStart=/home/ubuntu/alphacent/venv/bin/uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=10
StandardOutput=append:/home/ubuntu/alphacent/logs/backend-stdout.log
StandardError=append:/home/ubuntu/alphacent/logs/backend-stderr.log
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable alphacent

# --- Nginx ---
sudo tee /etc/nginx/sites-available/alphacent > /dev/null << 'NGXEOF'
server {
    listen 80;
    server_name _;

    location / {
        root /home/ubuntu/alphacent/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }
}
NGXEOF

sudo ln -sf /etc/nginx/sites-available/alphacent /etc/nginx/sites-enabled/alphacent
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

echo "Nginx and systemd configured"
REMOTE_SERVICES

# --- Step 4: Log rotation + backup cron ---
echo ""
echo "[4/4] Setting up log rotation and backups..."

ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no ubuntu@"$PUBLIC_IP" << REMOTE_CRON
set -euo pipefail

# Log rotation
sudo tee /etc/logrotate.d/alphacent > /dev/null << 'LOGEOF'
/home/ubuntu/alphacent/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
LOGEOF

# Daily backup cron
BUCKET="alphacent-backups-${ACCOUNT_ID}"
(crontab -l 2>/dev/null || true; echo "0 3 * * * pg_dump -U alphacent_user -h localhost alphacent | gzip > /tmp/alphacent_\\\$(date +\\%Y\\%m\\%d).sql.gz && aws s3 cp /tmp/alphacent_\\\$(date +\\%Y\\%m\\%d).sql.gz s3://\${BUCKET}/db/ --region ${REGION} && rm /tmp/alphacent_*.sql.gz") | sort -u | crontab -

# Create app directory structure
mkdir -p /home/ubuntu/alphacent/logs/cycles
mkdir -p /home/ubuntu/alphacent/config

echo "Cron and log rotation configured"
REMOTE_CRON

echo ""
echo "============================================"
echo "  Server Configuration Complete"
echo "============================================"
echo ""
echo "  The server is ready to receive deployments."
echo "  Push code to GitHub to trigger the first deploy."
echo ""
echo "  SSH: ssh -i ~/path/to/alphacent-key.pem ubuntu@$PUBLIC_IP"
echo "============================================"
