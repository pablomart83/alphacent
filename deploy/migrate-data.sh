#!/bin/bash
# =============================================================================
# AlphaCent Data Migration — Local PostgreSQL → EC2 PostgreSQL
# =============================================================================
# RUN THIS FROM YOUR MAC (one-time, after server-config.sh)
#
# Usage: bash deploy/migrate-data.sh <EC2_IP> <path-to-pem-file>
# Example: bash deploy/migrate-data.sh 54.72.123.45 ~/Downloads/alphacent-key.pem
# =============================================================================

set -euo pipefail

PUBLIC_IP="${1:?Usage: bash deploy/migrate-data.sh <EC2_IP> <PEM_FILE>}"
KEY_FILE="${2:?Usage: bash deploy/migrate-data.sh <EC2_IP> <PEM_FILE>}"

echo "============================================"
echo "  AlphaCent Data Migration"
echo "  Local → EC2 ($PUBLIC_IP)"
echo "============================================"

# Step 1: Dump local PostgreSQL
echo ""
echo "[1/3] Dumping local PostgreSQL..."
DUMP_FILE="/tmp/alphacent_migration.sql.gz"
pg_dump -h localhost alphacent | gzip > "$DUMP_FILE"
DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo "  Dump: $DUMP_FILE ($DUMP_SIZE)"

# Step 2: Transfer
echo ""
echo "[2/3] Transferring to EC2..."
scp -i "$KEY_FILE" -o StrictHostKeyChecking=no "$DUMP_FILE" ubuntu@"$PUBLIC_IP":/tmp/
echo "  Done"

# Step 3: Restore
echo ""
echo "[3/3] Restoring on EC2..."
ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no ubuntu@"$PUBLIC_IP" << 'REMOTE'
set -euo pipefail

sudo systemctl stop alphacent 2>/dev/null || true

# Terminate existing connections and recreate DB
sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'alphacent' AND pid <> pg_backend_pid();" 2>/dev/null || true
sudo -u postgres dropdb alphacent 2>/dev/null || true
sudo -u postgres createdb alphacent -O alphacent_user

# Restore
gunzip -c /tmp/alphacent_migration.sql.gz | sudo -u postgres psql alphacent

# Fix permissions
sudo -u postgres psql alphacent -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO alphacent_user;"
sudo -u postgres psql alphacent -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO alphacent_user;"
sudo -u postgres psql alphacent -c "GRANT USAGE ON SCHEMA public TO alphacent_user;"
sudo -u postgres psql alphacent -c "ANALYZE;"

TABLE_COUNT=$(sudo -u postgres psql -t alphacent -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")
echo "Tables restored: $TABLE_COUNT"

sudo systemctl start alphacent
sleep 3
curl -sf http://localhost:8000/health && echo " - healthy" || echo " - starting..."

rm /tmp/alphacent_migration.sql.gz
REMOTE

rm "$DUMP_FILE"

echo ""
echo "============================================"
echo "  Migration Complete"
echo "  Dashboard: http://$PUBLIC_IP"
echo "============================================"
