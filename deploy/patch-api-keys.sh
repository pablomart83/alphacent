#!/bin/bash
# patch-api-keys.sh — Write config/api_keys.yaml from AWS Secrets Manager.
#
# Run this on EC2 after any manual SCP deploy that might have touched config files.
# GitHub Actions runs this automatically as part of the deploy workflow.
#
# Usage:
#   ssh -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149
#   cd /home/ubuntu/alphacent && bash deploy/patch-api-keys.sh

set -euo pipefail

REGION="${AWS_REGION:-eu-west-1}"
CONFIG_DIR="config"

echo "Writing API keys from Secrets Manager (region: $REGION)..."

python3 << PYEOF
import subprocess, yaml, os, stat

def get_secret(name, fallback=""):
    try:
        r = subprocess.run(
            ["aws", "secretsmanager", "get-secret-value",
             "--secret-id", name, "--region", "${REGION}",
             "--query", "SecretString", "--output", "text"],
            capture_output=True, text=True, check=True
        )
        return r.stdout.strip()
    except Exception as e:
        print(f"  Warning: {name} not in Secrets Manager — using fallback")
        return fallback

# Read existing YAML to get any hardcoded keys as fallback
import os
_yaml_path = "${CONFIG_DIR}/autonomous_trading.yaml"
_existing = {}
if os.path.exists(_yaml_path):
    with open(_yaml_path) as _f:
        _existing = yaml.safe_load(_f) or {}
_ds = _existing.get("data_sources", {})

keys = {
    "financial_modeling_prep": {"api_key": get_secret("alphacent/fmp-api-key",
        _ds.get("financial_modeling_prep", {}).get("api_key", ""))},
    "alpha_vantage":           {"api_key": get_secret("alphacent/alpha-vantage-api-key",
        _ds.get("alpha_vantage", {}).get("api_key", ""))},
    "fred":                    {"api_key": get_secret("alphacent/fred-api-key",
        _ds.get("fred", {}).get("api_key", ""))},
    "marketaux":               {"api_key": get_secret("alphacent/marketaux-api-key",
        _ds.get("marketaux", {}).get("api_key", ""))},
}

path = "${CONFIG_DIR}/api_keys.yaml"
with open(path, "w") as f:
    yaml.dump(keys, f, default_flow_style=False, sort_keys=False)
os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600
print(f"Written {path} (mode 600)")
PYEOF

echo "Done. Restart the backend to pick up new keys:"
echo "  sudo systemctl restart alphacent"
