# Migrations

Schema migrations applied to the AlphaCent PostgreSQL database.

Each file is a standalone SQL script that can be run with:
```bash
sudo -u postgres psql alphacent -f migrations/<filename>.sql
```

## Applied migrations

| File | Date | Description |
|---|---|---|
| `migrate_etoro_id_constraint.sql` | 2026-05-12 | Replace global `etoro_position_id` unique constraint with composite `(etoro_position_id, account_type)` — eToro reuses numeric IDs across demo/live accounts |
