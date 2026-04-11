#!/bin/bash
# =============================================================================
# Add CloudWatch permissions to AlphaCent EC2 IAM role
# =============================================================================
# RUN THIS IN AWS CLOUDSHELL (not on EC2)
# This adds CloudWatch + SNS permissions to the existing alphacent-ec2-role
# =============================================================================

set -euo pipefail

ROLE_NAME="alphacent-ec2-role"
REGION="eu-west-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "Adding CloudWatch + SNS permissions to $ROLE_NAME..."

aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "alphacent-cloudwatch-access" \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "cloudwatch:PutMetricData",
                    "cloudwatch:GetMetricData",
                    "cloudwatch:GetMetricStatistics",
                    "cloudwatch:ListMetrics",
                    "cloudwatch:PutMetricAlarm",
                    "cloudwatch:DescribeAlarms"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams"
                ],
                "Resource": "arn:aws:logs:'"$REGION"':'"$ACCOUNT_ID"':log-group:/alphacent/*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "sns:CreateTopic",
                    "sns:Subscribe",
                    "sns:Publish",
                    "sns:ListTopics"
                ],
                "Resource": "arn:aws:sns:'"$REGION"':'"$ACCOUNT_ID"':alphacent-*"
            }
        ]
    }'

echo "Done. CloudWatch permissions added to $ROLE_NAME."
echo ""
echo "Next: SSH into EC2 and run deploy/cloudwatch-setup.sh"
