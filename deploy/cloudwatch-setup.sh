#!/bin/bash
# =============================================================================
# AlphaCent CloudWatch Monitoring Setup
# =============================================================================
# RUN THIS VIA SSH ON THE EC2 INSTANCE (not locally)
#
# Sets up:
# 1. CloudWatch Agent (memory + disk metrics)
# 2. App heartbeat cron (pushes custom metric every minute)
# 3. CloudWatch Alarms (CPU, memory, disk, status check, heartbeat)
# 4. SNS topic for email alerts
# 5. IAM permissions for CloudWatch
#
# Prerequisites:
# - EC2 instance with IAM role (alphacent-ec2-role)
# - AWS CLI configured
# =============================================================================

set -euo pipefail

REGION="eu-west-1"
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
SNS_TOPIC_NAME="alphacent-alerts"
NAMESPACE="AlphaCent"
ALARM_PREFIX="alphacent"

echo "============================================"
echo "  AlphaCent CloudWatch Monitoring Setup"
echo "  Instance: $INSTANCE_ID | Region: $REGION"
echo "============================================"

# --- Step 1: Add CloudWatch permissions to IAM role ---
echo ""
echo "[1/5] Checking IAM permissions..."

# Test if we can already put metrics
if aws cloudwatch put-metric-data \
    --namespace "$NAMESPACE" \
    --metric-name "SetupTest" \
    --value 1 \
    --region "$REGION" 2>/dev/null; then
    echo "  CloudWatch permissions OK"
else
    echo "  ERROR: Missing CloudWatch permissions on IAM role."
    echo "  Run this in AWS CloudShell or with admin credentials:"
    echo ""
    cat << 'POLICY_EOF'
  aws iam put-role-policy \
    --role-name alphacent-ec2-role \
    --policy-name alphacent-cloudwatch-access \
    --policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Action": [
          "cloudwatch:PutMetricData",
          "cloudwatch:GetMetricData",
          "cloudwatch:ListMetrics",
          "cloudwatch:PutMetricAlarm",
          "cloudwatch:DescribeAlarms",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ],
        "Resource": "*"
      }]
    }'
POLICY_EOF
    echo ""
    echo "  After adding the policy, re-run this script."
    exit 1
fi

# --- Step 2: Install and configure CloudWatch Agent ---
echo ""
echo "[2/5] Installing CloudWatch Agent..."

if command -v amazon-cloudwatch-agent-ctl &>/dev/null; then
    echo "  CloudWatch Agent already installed"
else
    wget -q https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb -O /tmp/cw-agent.deb
    sudo dpkg -i /tmp/cw-agent.deb
    rm /tmp/cw-agent.deb
    echo "  CloudWatch Agent installed"
fi

# Write agent config
sudo tee /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json > /dev/null << 'AGENTEOF'
{
  "agent": {
    "metrics_collection_interval": 300,
    "run_as_user": "root"
  },
  "metrics": {
    "namespace": "AlphaCent",
    "append_dimensions": {
      "InstanceId": "${aws:InstanceId}"
    },
    "metrics_collected": {
      "mem": {
        "measurement": ["mem_used_percent"],
        "metrics_collection_interval": 300
      },
      "disk": {
        "measurement": ["disk_used_percent"],
        "metrics_collection_interval": 300,
        "resources": ["/"]
      }
    }
  }
}
AGENTEOF

# Start agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -s \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json

echo "  CloudWatch Agent configured and started"

# --- Step 3: Create heartbeat script ---
echo ""
echo "[3/5] Setting up app heartbeat..."

sudo tee /home/ubuntu/alphacent/deploy/heartbeat.sh > /dev/null << 'HBEOF'
#!/bin/bash
# AlphaCent heartbeat — pushes 1 if healthy, 0 if not
REGION="eu-west-1"
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)

# Check backend health
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    VALUE=1
else
    VALUE=0
fi

aws cloudwatch put-metric-data \
    --namespace "AlphaCent" \
    --metric-name "AppHeartbeat" \
    --dimensions "InstanceId=$INSTANCE_ID" \
    --value "$VALUE" \
    --unit "Count" \
    --region "$REGION" 2>/dev/null
HBEOF

chmod +x /home/ubuntu/alphacent/deploy/heartbeat.sh

# Add to crontab (every minute)
(crontab -l 2>/dev/null | grep -v "heartbeat.sh" || true; echo "* * * * * /home/ubuntu/alphacent/deploy/heartbeat.sh") | crontab -

echo "  Heartbeat cron installed (every 1 minute)"

# --- Step 4: Create SNS topic ---
echo ""
echo "[4/5] Creating SNS alert topic..."

TOPIC_ARN=$(aws sns list-topics --region "$REGION" --query "Topics[?ends_with(TopicArn, ':${SNS_TOPIC_NAME}')].TopicArn" --output text 2>/dev/null)

if [ -z "$TOPIC_ARN" ] || [ "$TOPIC_ARN" = "None" ]; then
    TOPIC_ARN=$(aws sns create-topic --name "$SNS_TOPIC_NAME" --region "$REGION" --query "TopicArn" --output text)
    echo "  Created SNS topic: $TOPIC_ARN"
else
    echo "  SNS topic exists: $TOPIC_ARN"
fi

echo ""
echo "  Enter your email for alerts (or press Enter to skip):"
read -r ALERT_EMAIL

if [ -n "$ALERT_EMAIL" ]; then
    aws sns subscribe \
        --topic-arn "$TOPIC_ARN" \
        --protocol email \
        --notification-endpoint "$ALERT_EMAIL" \
        --region "$REGION" > /dev/null
    echo "  Subscription created — CHECK YOUR EMAIL to confirm"
else
    echo "  Skipped email subscription (add manually later)"
fi

# --- Step 5: Create CloudWatch Alarms ---
echo ""
echo "[5/5] Creating CloudWatch Alarms..."

# Alarm 1: EC2 Status Check Failed
aws cloudwatch put-metric-alarm \
    --alarm-name "${ALARM_PREFIX}-status-check-failed" \
    --alarm-description "EC2 instance status check failed — instance may be impaired" \
    --namespace "AWS/EC2" \
    --metric-name "StatusCheckFailed" \
    --dimensions "Name=InstanceId,Value=$INSTANCE_ID" \
    --statistic "Maximum" \
    --period 300 \
    --evaluation-periods 1 \
    --threshold 1 \
    --comparison-operator "GreaterThanOrEqualToThreshold" \
    --alarm-actions "$TOPIC_ARN" \
    --ok-actions "$TOPIC_ARN" \
    --treat-missing-data "breaching" \
    --region "$REGION"
echo "  ✓ Status check alarm"

# Alarm 2: CPU > 80% for 10 minutes
aws cloudwatch put-metric-alarm \
    --alarm-name "${ALARM_PREFIX}-high-cpu" \
    --alarm-description "CPU utilization above 80% for 10 minutes" \
    --namespace "AWS/EC2" \
    --metric-name "CPUUtilization" \
    --dimensions "Name=InstanceId,Value=$INSTANCE_ID" \
    --statistic "Average" \
    --period 300 \
    --evaluation-periods 2 \
    --threshold 80 \
    --comparison-operator "GreaterThanThreshold" \
    --alarm-actions "$TOPIC_ARN" \
    --ok-actions "$TOPIC_ARN" \
    --treat-missing-data "missing" \
    --region "$REGION"
echo "  ✓ High CPU alarm (>80% for 10min)"

# Alarm 3: Memory > 85%
aws cloudwatch put-metric-alarm \
    --alarm-name "${ALARM_PREFIX}-high-memory" \
    --alarm-description "Memory usage above 85% — risk of OOM" \
    --namespace "AlphaCent" \
    --metric-name "mem_used_percent" \
    --dimensions "Name=InstanceId,Value=$INSTANCE_ID" \
    --statistic "Average" \
    --period 300 \
    --evaluation-periods 2 \
    --threshold 85 \
    --comparison-operator "GreaterThanThreshold" \
    --alarm-actions "$TOPIC_ARN" \
    --ok-actions "$TOPIC_ARN" \
    --treat-missing-data "missing" \
    --region "$REGION"
echo "  ✓ High memory alarm (>85%)"

# Alarm 4: Disk > 80%
aws cloudwatch put-metric-alarm \
    --alarm-name "${ALARM_PREFIX}-high-disk" \
    --alarm-description "Disk usage above 80% on root volume" \
    --namespace "AlphaCent" \
    --metric-name "disk_used_percent" \
    --dimensions "Name=InstanceId,Value=$INSTANCE_ID,Name=path,Value=/,Name=device,Value=nvme0n1p1,Name=fstype,Value=ext4" \
    --statistic "Average" \
    --period 300 \
    --evaluation-periods 1 \
    --threshold 80 \
    --comparison-operator "GreaterThanThreshold" \
    --alarm-actions "$TOPIC_ARN" \
    --ok-actions "$TOPIC_ARN" \
    --treat-missing-data "missing" \
    --region "$REGION"
echo "  ✓ High disk alarm (>80%)"

# Alarm 5: App heartbeat missing (no healthy response for 5 minutes)
aws cloudwatch put-metric-alarm \
    --alarm-name "${ALARM_PREFIX}-app-down" \
    --alarm-description "Backend health check failing — app may be down" \
    --namespace "AlphaCent" \
    --metric-name "AppHeartbeat" \
    --dimensions "Name=InstanceId,Value=$INSTANCE_ID" \
    --statistic "Minimum" \
    --period 300 \
    --evaluation-periods 1 \
    --threshold 1 \
    --comparison-operator "LessThanThreshold" \
    --alarm-actions "$TOPIC_ARN" \
    --ok-actions "$TOPIC_ARN" \
    --treat-missing-data "breaching" \
    --region "$REGION"
echo "  ✓ App heartbeat alarm (down > 5min)"

echo ""
echo "============================================"
echo "  CloudWatch Monitoring Setup Complete"
echo "============================================"
echo ""
echo "  Alarms created:"
echo "    1. ${ALARM_PREFIX}-status-check-failed"
echo "    2. ${ALARM_PREFIX}-high-cpu (>80% for 10min)"
echo "    3. ${ALARM_PREFIX}-high-memory (>85%)"
echo "    4. ${ALARM_PREFIX}-high-disk (>80%)"
echo "    5. ${ALARM_PREFIX}-app-down (heartbeat missing 5min)"
echo ""
echo "  SNS Topic: $TOPIC_ARN"
echo "  Metrics namespace: AlphaCent"
echo ""
echo "  IMPORTANT: If you subscribed an email, confirm it now."
echo "  Metrics will start appearing in ~5 minutes."
echo "============================================"
