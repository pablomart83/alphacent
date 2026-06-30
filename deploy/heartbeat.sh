#!/bin/bash
# AlphaCent heartbeat — pushes 1 if healthy, 0 if not.
# Installed as a per-minute cron (see deploy/cloudwatch-setup.sh).
# Backs the CloudWatch alarm "alphacent-app-down" (missing/0 for 5min -> alert).
REGION="eu-west-1"

# Instance ID via IMDS (v2 token first, fall back to v1).
TOKEN=$(curl -s --max-time 3 -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null)
if [ -n "$TOKEN" ]; then
    INSTANCE_ID=$(curl -s --max-time 3 -H "X-aws-ec2-metadata-token: $TOKEN" \
        http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null)
else
    INSTANCE_ID=$(curl -s --max-time 3 http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null)
fi

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
