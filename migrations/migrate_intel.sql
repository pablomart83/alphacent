-- Intel page: system_findings + intel_runs tables
-- Run once on EC2: sudo -u postgres psql alphacent -f /home/ubuntu/alphacent/migrations/migrate_intel.sql

CREATE TABLE IF NOT EXISTS system_findings (
    id              VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    check_id        VARCHAR NOT NULL,
    key             VARCHAR NOT NULL,
    category        VARCHAR NOT NULL,
    severity        VARCHAR NOT NULL,
    title           VARCHAR NOT NULL,
    detail          TEXT NOT NULL,
    evidence        TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    context_links   JSON,
    ask_kiro_prompt TEXT NOT NULL,
    first_seen      TIMESTAMP NOT NULL DEFAULT NOW(),
    last_seen       TIMESTAMP NOT NULL DEFAULT NOW(),
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    lookback_days   INTEGER NOT NULL DEFAULT 7,
    status          VARCHAR NOT NULL DEFAULT 'open',
    dismissed_reason VARCHAR,
    resolved_at     TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_system_findings_check_key
    ON system_findings (check_id, key);

CREATE INDEX IF NOT EXISTS idx_system_findings_status
    ON system_findings (status, severity, category);

CREATE INDEX IF NOT EXISTS idx_system_findings_last_seen
    ON system_findings (last_seen DESC);

CREATE TABLE IF NOT EXISTS intel_runs (
    id              VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    started_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMP,
    lookback_days   INTEGER NOT NULL,
    findings_created INTEGER DEFAULT 0,
    findings_updated INTEGER DEFAULT 0,
    findings_total   INTEGER DEFAULT 0,
    duration_s      FLOAT,
    error           TEXT,
    status          VARCHAR NOT NULL DEFAULT 'running'
);

CREATE INDEX IF NOT EXISTS idx_intel_runs_started_at
    ON intel_runs (started_at DESC);
