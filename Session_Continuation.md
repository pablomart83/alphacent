can # AlphaCent — Session Continuation Prompt

Read `#File:.kiro/steering/trading-system-context.md` for full system context, then read this prompt carefully before proceeding.

---

## Philosophy

AlphaCent is not a side project. It is the technology backbone of a systematic trading operation built to institutional standards. Every line of code, every architectural decision, every deployment choice is made as if managing a $100B book. We don't ship code that "works" — we ship code that is correct, resilient, and auditable.

**Development principles:**
- Correctness over speed. A bug in a trading system is a P&L event.
- Defensive programming. Every external call can fail. Every assumption can be wrong.
- Operational reliability. The system runs 24/7 unattended. If it can't handle 3am on a Sunday, it's not ready.
- Data integrity. Stale data, missing bars, and silent failures are existential risks.
- Risk-first thinking. Every feature is evaluated through the lens of capital preservation.
- Clean architecture. No dead code, no orphaned files, no "temporary" hacks that become permanent.

**What we are building:**
An end-to-end autonomous trading platform that proposes, validates, executes, monitors, and retires trading strategies across 306 symbols (stocks, ETFs, crypto, forex, indices, commodities) on eToro. The system generates alpha through diversified strategy templates, walk-forward validated backtesting, and position-level risk management — all without human intervention.

**Current phase:** Pre-Production (DEMO). Proving consistent returns on $465K virtual capital before deploying real money.

---

## System Architecture

```
Frontend (React/Vite)  →  Nginx (SSL/443)  →  Backend (FastAPI/uvicorn)
                                                    ├── MonitoringService (24/7)
                                                    │   ├── Position sync (60s)
                                                    │   ├── Trailing stops (30s)
                                                    │   ├── Partial exits (5s)
                                                    │   ├── Position health checks
                                                    │   ├── Quick price update (10min)
                                                    │   ├── Full price sync (55min)
                                                    │   └── Fundamental exits (daily)
                                                    ├── TradingScheduler
                                                    │   ├── Signal generation (30min)
                                                    │   ├── Risk validation
                                                    │   └── Order execution
                                                    └── PostgreSQL 16
```

**Key components:**
- `src/core/monitoring_service.py` — 24/7 position monitoring, trailing stops, price syncs
- `src/core/trading_scheduler.py` — Signal generation and order execution loop
- `src/core/order_monitor.py` — Position sync with eToro, cache management
- `src/core/symbol_registry.py` — Centralized symbol config loaded from `config/symbols.yaml`
- `src/core/auth.py` — DB-backed user authentication with role-based permissions
- `src/strategy/strategy_engine.py` — DSL + Alpha Edge signal generation, backtesting
- `src/strategy/portfolio_manager.py` — Position-level risk management, decay scoring
- `src/api/etoro_client.py` — eToro API client with circuit breakers
- `src/models/orm.py` — SQLAlchemy ORM with EnumString, NumpySafeJSON type decorators
- `src/models/database.py` — PostgreSQL connection pooling, numpy adapters

---

## Infrastructure (AWS)

### Access

| Resource | Details |
|---|---|
| Dashboard | https://alphacent.co.uk |
| Health check | https://alphacent.co.uk/health |
| EC2 instance | `i-035d5576835fcef0a` (t3.medium, eu-west-1) |
| Public IP | `34.252.61.149` |
| SSH | `ssh -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149` |
| Domain | `alphacent.co.uk` (Route 53) |
| SSL | Let's Encrypt, auto-renews via certbot |
| GitHub | `github.com/pablomart83/alphacent` (private) |

### Services on EC2

| Service | Manager | Command |
|---|---|---|
| Backend (uvicorn) | systemd | `sudo systemctl restart alphacent` |
| Nginx | systemd | `sudo systemctl reload nginx` |
| PostgreSQL 16 | systemd | `sudo systemctl status postgresql` |
| DB backups | cron | Daily pg_dump to S3 at 03:00 UTC |
| SSL renewal | certbot timer | Auto every 90 days |

### Secrets (AWS Secrets Manager, eu-west-1)

| Secret | Purpose |
|---|---|
| `alphacent/encryption-key` | Fernet key for eToro credential decryption |
| `alphacent/etoro-credentials` | Encrypted eToro public_key + user_key (DEMO) |
| `alphacent/fmp-api-key` | Financial Modeling Prep API |
| `alphacent/alpha-vantage-api-key` | Alpha Vantage API |
| `alphacent/fred-api-key` | FRED economic data API |
| `alphacent/postgres-password` | PostgreSQL alphacent_user password |
| `alphacent/admin-password` | Web UI admin password |

### Key files on EC2

| File | Purpose |
|---|---|
| `/etc/systemd/system/alphacent.service` | systemd service definition |
| `/etc/nginx/sites-available/alphacent` | Nginx config (SSL + proxy + SPA) |
| `/home/ubuntu/alphacent/.env.production` | DATABASE_URL + ADMIN_PASSWORD |
| `/home/ubuntu/alphacent/config/.encryption_key` | Fernet key (fetched from Secrets Manager) |
| `/home/ubuntu/alphacent/config/demo_credentials.json` | Encrypted eToro creds |
| `/home/ubuntu/alphacent/config/autonomous_trading.yaml` | Trading config (API keys patched from Secrets Manager) |

### Security

- SSL/TLS on all traffic (Let's Encrypt)
- Security group: ports 22, 80, 443 restricted to operator IP; port 8000 removed
- Backend listens on 127.0.0.1:8000 only (not publicly accessible)
- Session-based authentication on all API endpoints
- eToro credentials encrypted at rest (Fernet)
- API keys stored in AWS Secrets Manager, not in code

---

## CI/CD

### Deployment flow

```
Local code change → git commit → git push → GitHub Actions → EC2 deploy
```

### Push command (Code Defender bypass required on corporate machines)

```bash
git add .
git commit -m "description"
git -c core.hooksPath=/dev/null push
```

### GitHub Actions workflow (`.github/workflows/deploy.yml`)

On push to `main`:
1. Checkout code
2. SSH into EC2 via `EC2_SSH_KEY` secret
3. rsync code (excludes secrets, venv, node_modules, logs)
4. Install Python deps
5. Fetch secrets from Secrets Manager → write config files
6. Patch API keys in YAML
7. Build frontend (`npm run build` with HTTPS env vars)
8. Restart systemd service
9. Health check

### GitHub Secrets required

| Secret | Value |
|---|---|
| `EC2_HOST` | `34.252.61.149` |
| `EC2_SSH_KEY` | Contents of `alphacent-key.pem` |
| `EC2_USER` | `ubuntu` |
| `AWS_REGION` | `eu-west-1` |

### Manual deployment (if GitHub Actions fails)

```bash
# SSH into EC2
ssh -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149

# Pull latest code (via curl from GitHub raw)
cd /home/ubuntu/alphacent
curl -sL https://raw.githubusercontent.com/pablomart83/alphacent/main/path/to/file -o path/to/file

# Rebuild frontend
cd frontend
VITE_API_BASE_URL=https://alphacent.co.uk VITE_WS_BASE_URL=wss://alphacent.co.uk npm run build

# Restart backend
sudo systemctl restart alphacent
```

### Nginx config (must be maintained manually on EC2)

The Nginx config at `/etc/nginx/sites-available/alphacent` explicitly routes:
- `/assets/*`, `/vite.svg` → static files
- `/ws` → WebSocket proxy to backend
- API routes (`/auth`, `/config`, `/account`, `/strategies`, etc.) → proxy to backend
- Everything else → `index.html` (React SPA routing)

If new API route prefixes are added to the backend, they must be added to the Nginx regex. (Note: `/control` was added on April 10, 2026.)

---

## Agent Operational Procedures

**IMPORTANT: The AI agent (Kiro) has full terminal access and can independently operate the entire deployment pipeline.** No manual steps are needed from the user unless explicitly stated. The agent should use these procedures directly.

### SSH Access

The agent can SSH into EC2 directly from the local terminal:

```bash
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149
```

For single commands:
```bash
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'command here'
```

### File Deployment (SCP)

GitHub Actions rsync has a known issue where it sometimes skips changed files (timestamp-based comparison). The `--checksum` flag was added to fix this, but for immediate deployment the agent should SCP files directly:

```bash
# Backend Python files
scp -i ~/Downloads/alphacent-key.pem src/path/to/file.py ubuntu@34.252.61.149:/home/ubuntu/alphacent/src/path/to/file.py

# Config files
scp -i ~/Downloads/alphacent-key.pem config/autonomous_trading.yaml ubuntu@34.252.61.149:/home/ubuntu/alphacent/config/autonomous_trading.yaml

# Frontend files (must rebuild after)
scp -i ~/Downloads/alphacent-key.pem frontend/src/pages/SomePage.tsx ubuntu@34.252.61.149:/home/ubuntu/alphacent/frontend/src/pages/SomePage.tsx
```

### Backend Restart

After deploying Python/config changes, restart the backend:

```bash
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo systemctl restart alphacent && sleep 10 && curl -sf http://localhost:8000/health'
```

Expected output: `{"status":"healthy","service":"alphacent-backend"}`

If health check fails, check logs:
```bash
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo journalctl -u alphacent --no-pager -n 50'
```

### Frontend Build & Deploy

After deploying frontend `.tsx`/`.ts` files, rebuild on EC2:

```bash
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'cd /home/ubuntu/alphacent/frontend && VITE_API_BASE_URL=https://alphacent.co.uk VITE_WS_BASE_URL=wss://alphacent.co.uk npm run build 2>&1 | tail -5'
```

Expected output: `✓ built in X.XXs` — no TypeScript errors.

If there are TS errors, fix them locally, SCP again, and rebuild. No backend restart needed for frontend-only changes.

### Git Commit & Push

After all changes are verified working on EC2:

```bash
git add .
git commit -m "descriptive message"
git -c core.hooksPath=/dev/null push
```

The `core.hooksPath=/dev/null` bypasses Code Defender hooks on the corporate machine. GitHub Actions will trigger on push to `main` but the code is already deployed via SCP — the Actions run is for consistency.

### Standard Deployment Workflow

For any code change, the agent follows this sequence:

1. **Edit files locally** (in the workspace)
2. **Run `getDiagnostics`** to check for syntax/type errors
3. **SCP changed files to EC2** (immediate deployment)
4. **Restart backend** if Python/config files changed
5. **Rebuild frontend** if `.tsx`/`.ts` files changed
6. **Verify health** (`curl -sf http://localhost:8000/health`)
7. **Check logs** if anything fails (`sudo journalctl -u alphacent --no-pager -n 50`)
8. **Git add, commit, push** to persist changes in repo

### Database Access

```bash
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 "sudo -u postgres psql alphacent -t -A -c 'SQL QUERY HERE'"
```

### Log Monitoring

```bash
# Live logs
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo journalctl -u alphacent --no-pager -n 200 2>/dev/null | grep -i "search term" | tail -30'

# Filtered by component
ssh ... 'sudo journalctl -u alphacent --no-pager -n 500 2>/dev/null | grep -i "forex\|crypto\|activation\|failed" | tail -50'
```

### CloudWatch Alarms

```bash
# Check alarm states
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'aws cloudwatch describe-alarms --alarm-name-prefix "alphacent" --region eu-west-1 --query "MetricAlarms[].{Name:AlarmName,State:StateValue}" --output table'
```

---

## Current System State (April 11, 2026)

- **Database:** PostgreSQL 16 on EC2, 32 tables (added `users`), 780K+ rows
- **Account:** eToro DEMO, balance ~$124K, equity ~$465K
- **Symbol universe:** 306 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 11 crypto)
- **Active strategies:** ~98 (141 total including backtested/proposed)
- **Open positions:** ~122
- **Position sync:** 1 second for 122 positions
- **Monitoring:** 24/7 — trailing stops, partial exits, position health, price syncs
- **Signal generation:** Every 10 minutes for active strategies
- **Market regime:** ranging_low_vol
- **Auth:** DB-backed with role-based permissions (admin/trader/viewer)

---

## Troubleshooting

```bash
# SSH into EC2
ssh -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149

# Live backend logs
sudo journalctl -u alphacent -f

# Last 50 lines
sudo journalctl -u alphacent --no-pager -n 50

# Check service status
sudo systemctl status alphacent

# Restart backend
sudo systemctl restart alphacent

# Check Nginx
sudo nginx -t
sudo tail -f /var/log/nginx/error.log

# PostgreSQL
sudo -u postgres psql alphacent
# Useful queries:
#   SELECT count(*) FROM strategies WHERE status = 'ACTIVE';
#   SELECT count(*) FROM positions WHERE closed_at IS NULL;
#   SELECT symbol, date, close FROM historical_price_cache ORDER BY date DESC LIMIT 5;

# Check health
curl https://alphacent.co.uk/health
```

---

## Monthly AWS Cost

| Resource | Cost |
|---|---|
| EC2 t3.medium (24/7) | ~$30 |
| EBS 30GB gp3 | ~$2.40 |
| Secrets Manager (7 secrets) | ~$2.80 |
| S3 backups | ~$0.50 |
| Data transfer | ~$1-2 |
| **Total** | **~$36-38/month** |

---

## Open Items

### From V9 Session
1. Signal generation — Are conviction scores using meaningful inputs?
2. Template-symbol matching — Should template weights decay over time?
3. Risk controls — Portfolio-level VaR check before new positions
4. Order execution — Is signal coordination too aggressive?
5. Performance feedback loop — Is it chasing past winners?

### Infrastructure
- ~~Change default admin password from `admin123`~~ ✅ Done (DB-backed auth, password changed)
- Restrict security group ports 80/443 to operator IP (or leave open with auth)
- Set up CloudWatch monitoring / alerting
- Consider t3.small downgrade to save ~$10/month (CPU headroom confirmed — viable)
- Fix GitHub Actions deploy workflow — rsync not syncing all files reliably (14s deploys)
- FMP API rate limit (300/min) — may need upgrade with 232 stocks now

### Data
- Forex carry bias — FRED rate data available but not wired into scoring
- Transcript sentiment — Module built but not integrated
- ~~Daily P&L timezone — DB dates are UTC, frontend displays as-is~~ ✅ Fixed (utcToLocal helper)
- FMP `/insider-trading` endpoint returning 404 — insider buying checks silently skipped

### Analytics
- Historical stress tests (COVID, Lehman, SVB)
- Drawdown recovery analysis
- R-Multiple distribution
- SPY benchmark comparison on equity curve

### Session Improvements (April 10-11, 2026)

#### 59. DB-Backed User Management with Role-Based Permissions ✅
- `UserORM` table in PostgreSQL (username, password_hash, role, permissions, is_active)
- `AuthenticationManager` rewritten: DB-backed users, in-memory sessions
- Three roles: admin (full access), trader (trade + strategies), viewer (read-only)
- API endpoints: change password, CRUD users, reset password, role assignment
- Middleware injects role/permissions into request state
- `require_role()` and `require_action()` dependency helpers for route protection
- Frontend: Users tab in Settings with create/delete/role change/password reset
- Sidebar filters nav items based on user permissions, shows role badge
- **Files**: `src/core/auth.py`, `src/api/routers/auth.py`, `src/api/app.py`, `src/api/middleware.py`, `src/api/dependencies.py`, `src/models/orm.py`, `frontend/src/pages/SettingsNew.tsx`, `frontend/src/services/auth.ts`, `frontend/src/components/Sidebar.tsx`

#### 60. Symbol Universe Expansion (155 → 306) ✅
- Added 151 new symbols across all themes: AI/data center, defense, nuclear, fintech, healthcare, industrials, software, semis, energy, telecom, REITs, mining, autos, space, crypto-adjacent
- All 306 symbols verified on eToro DEMO API with real instrument IDs
- European defense stocks added: RHM.DE (Rheinmetall), RR.L (Rolls-Royce)
- **Files**: `config/symbols.yaml`, `src/core/tradeable_instruments.py`, `src/utils/instrument_mappings.py`, `src/risk/risk_manager.py`

#### 61. Centralized Symbol Config (config/symbols.yaml) ✅
- Single YAML file as source of truth for all symbols, eToro IDs, sectors, asset classes
- `src/core/symbol_registry.py` loads YAML, provides all lookups
- `tradeable_instruments.py` and `instrument_mappings.py` are now thin backward-compatible wrappers
- `SYMBOL_SECTOR_MAP` in risk_manager.py loaded from registry at import time
- To add a new symbol: edit `config/symbols.yaml`, restart backend. No code changes needed.
- Fixed YAML `ON` → boolean `True` gotcha (ON Semiconductor)
- **Files**: `config/symbols.yaml`, `src/core/symbol_registry.py`, `src/core/tradeable_instruments.py`, `src/utils/instrument_mappings.py`, `src/risk/risk_manager.py`

#### 62. Fundamental Data Exclusion Fixes ✅
- `fundamental_data_provider.py` now uses `DEMO_ALLOWED_ETFS` for skip logic (no hardcoded ETF list)
- Monitoring service fundamental exits use dynamic ETF detection (`sector.endswith("ETF")`)
- Strategy engine fundamental filter skips ETFs alongside crypto/forex/indices/commodities
- Data quality validator uses dynamic crypto/forex lists from `tradeable_instruments`
- **Files**: `src/data/fundamental_data_provider.py`, `src/core/monitoring_service.py`, `src/strategy/strategy_engine.py`, `src/data/data_quality_validator.py`

#### 63. UTC Timezone Fix ✅
- `date-utils.ts`: `parseUTC()` appends 'Z' to bare timestamps so browser interprets them as UTC
- Added `utcToLocal()` and `formatUTC()` helpers
- Fixed OverviewNew, OrdersNew, RiskNew, AutonomousNew, SettingsNew, DataManagementNew
- All backend timestamps now display in user's local timezone
- **Files**: `frontend/src/lib/date-utils.ts`, all page components

#### 64. Bug Fixes ✅
- `OrderORM` UnboundLocalError in `reconcile_on_startup` — removed redundant lazy imports that shadowed module-level import
- `init_database()` returns `None` — fixed `app.py` to use `get_database()` for `auth_manager.set_database()`
- Added `lark` to `requirements.txt` (DSL parser dependency missing on EC2)
- Added `/control` to Nginx proxy regex (was falling through to SPA catch-all)
- **Files**: `src/core/order_monitor.py`, `src/api/app.py`, `requirements.txt`


### Session Improvements (April 11, 2026 — Session 2)

#### 65. CloudWatch Monitoring & Alerting ✅
- CloudWatch Agent installed on EC2 (memory + disk metrics every 5 min)
- App heartbeat cron pushing health status every minute
- 5 alarms: status check failed, CPU >80% (10min), memory >85% (10min), disk >80%, app down (15min)
- SNS topic `alphacent-alerts` → email notifications
- IAM role updated with CloudWatch + SNS permissions
- **Files**: `deploy/cloudwatch-setup.sh`, `deploy/cloudwatch-iam-policy.sh`, `deploy/heartbeat.sh`

#### 66. GitHub Actions Deploy Fix ✅
- Added `--checksum` to rsync (fixes clock-skew file skip bug)
- Changed `.env.*` exclude to explicit `.env.production` (wildcard was too broad)
- Fixed frontend build to use `https://alphacent.co.uk` + `wss://alphacent.co.uk` (was `http://$EC2_HOST`)
- Fixed verify step to use HTTPS
- **Files**: `.github/workflows/deploy.yml`

#### 67. FMP Rate Limiter Bug Fix ✅
- Moved `record_call()` into `_fmp_request` so each individual API call is counted
- Previously called once per symbol in `_fetch_from_fmp`, undercounting by 4-5x
- Added `base_url` parameter to `_fmp_request` for v4 endpoints
- Cleaned up 3 stale `record_call()` in `get_institutional_ownership`, `get_price_target_consensus`, `get_upgrades_downgrades`
- **Files**: `src/data/fundamental_data_provider.py`

#### 68. FMP Insider Trading 404 Fix ✅
- Insider trading endpoint was hitting `/stable/insider-trading` (doesn't exist)
- Fixed to use `https://financialmodelingprep.com/api/v4/insider-trading`
- **Files**: `src/data/fundamental_data_provider.py`

#### 69. Non-US Symbol FMP Skip ✅
- `RR.L` (Rolls-Royce) and `RHM.DE` (Rheinmetall) returning 402 Payment Required
- Added skip for symbols containing `.` in `get_fundamental_data()` and `get_historical_fundamentals()`
- **Files**: `src/data/fundamental_data_provider.py`

#### 70. Forex Carry Bias Integration ✅
- `get_carry_rates()` in `MarketStatisticsAnalyzer` — fetches central bank rates from FRED for USD, EUR, GBP, JPY, AUD, CAD, CHF
- Computes rate differentials for each forex pair (EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF)
- `_score_carry_bias()` in `ConvictionScorer` — ±1 to ±5 points on forex signal conviction based on carry alignment
- Carry bias at proposal time in `_score_symbol_for_template()` — +10 for with-carry, -8 for against-carry, +5 extra for mean-reversion on high-carry pairs
- **Files**: `src/strategy/market_analyzer.py`, `src/strategy/conviction_scorer.py`, `src/strategy/strategy_proposer.py`

#### 71. Transaction Cost Model Correction ✅ (CRITICAL)
- Forex was 3-7x too high (0.06% → 0.02% per side) — eToro majors are 1-2 pips
- Crypto was 4x too low (0.25% → 1.1% per side) — eToro charges 1% per side
- Stocks/ETFs adjusted for CFD costs (0.05% → 0.17% per side) — eToro CFDs are 0.15%
- Indices were 3x too high (0.07% → 0.025%) — eToro SPX500/NSDQ100 = 0.015%
- Impact: All 18 crypto strategies would fail under real costs; forex strategies now pass activation
- **Files**: `config/autonomous_trading.yaml`

#### 72. Crypto Trading Overhaul ✅
- **4 new low-frequency momentum templates**: Crypto Trend Breakout, Crypto Weekly Trend Follow, Crypto Deep Dip Accumulation, Crypto Golden Cross
- **Halving cycle overlay**: `get_crypto_cycle_phase()` — determines accumulation/bull/distribution/bear phase, feeds into proposal scoring (+15/-25) and conviction scoring (±5)
- **BTC/ETH only**: Removed 9 altcoins from `config/symbols.yaml` — eToro's 1% fee makes altcoin strategies unprofitable
- **Min return per trade**: Crypto bumped from 0.2% to 4% — only strategies generating 4%+ per trade pass activation
- **Min holding period**: Crypto bumped from 7 to 21 days — kills high-frequency scalping
- **Stochastic validation**: Bumped `entry_max` from 30 to 35 to unblock crypto templates
- **Regime coverage fix**: Added RANGING_LOW_VOL to all new crypto templates (current regime)
- **Files**: `config/autonomous_trading.yaml`, `config/symbols.yaml`, `src/strategy/strategy_templates.py`, `src/strategy/market_analyzer.py`, `src/strategy/conviction_scorer.py`

#### 73. Per-Asset-Class Regime Detection ✅
- `_detect_forex_regime()` using EURUSD, GBPUSD, USDJPY as benchmarks
- `_detect_commodity_regime()` using GOLD, OIL, SILVER as benchmarks
- Crypto already had independent detection via BTC/ETH
- Wired into `_filter_templates_by_macro_regime()` — each asset class uses its own regime for template selection
- **Files**: `src/strategy/strategy_proposer.py`

#### 74. Comprehensive Regime Analytics Tab ✅
- New `/analytics/regime-comprehensive` endpoint returning per-asset-class regimes, FRED macro data, crypto cycle, carry rates, performance by regime, transitions, strategy heatmap
- Frontend regime tab now shows: Current Market Regimes (4 asset classes), Macro Market Context (12 FRED indicators), Bitcoin Halving Cycle, Forex Carry Rates, Performance by Regime, Regime Transitions, Strategy Performance Heatmap
- Regime data fetched in Phase 1 (no flash of empty state on tab switch)
- **Files**: `src/api/routers/analytics.py`, `frontend/src/pages/AnalyticsNew.tsx`, `frontend/src/services/api.ts`

---

## Current System State (April 11, 2026 — Updated)

- **Database:** PostgreSQL 16 on EC2, 32 tables, 780K+ rows
- **Account:** eToro DEMO, balance ~$124K, equity ~$465K
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto — BTC/ETH only)
- **Active strategies:** ~101 (including 18 crypto that will be retired under new cost model)
- **Open positions:** ~123
- **Monitoring:** 24/7 + CloudWatch alerting (5 alarms, email notifications)
- **Market regime:** Equity: ranging_low_vol, Crypto: trending_up_strong, Forex: ranging_low_vol, Commodity: ranging_high_vol
- **Crypto cycle:** ~24 months post-halving (late_bull/distribution boundary)

---

## Open Items (Updated)

### From V9 Session
1. Signal generation — Are conviction scores using meaningful inputs? *(partially addressed with carry bias + cycle overlay)*
2. Template-symbol matching — Should template weights decay over time?
3. Risk controls — Portfolio-level VaR check before new positions
4. Order execution — Is signal coordination too aggressive?
5. Performance feedback loop — Is it chasing past winners?

### Infrastructure
- ~~Change default admin password~~ ✅
- ~~CloudWatch monitoring/alerting~~ ✅
- ~~GitHub Actions deploy fix~~ ✅
- ~~FMP rate limiter bug~~ ✅
- Security group ports 80/443 — decided to keep open with auth ✅
- Consider t3.small downgrade — waiting on CloudWatch memory data (1 week)
- FMP API rate limit (300/min) — monitor with corrected per-call counting

### Data
- ~~Forex carry bias~~ ✅ (wired into scoring)
- Transcript sentiment — Module built but not integrated
- ~~FMP `/insider-trading` 404~~ ✅ (fixed to v4 endpoint)
- ~~Non-US symbol 402 errors~~ ✅ (skip symbols with `.`)

### Analytics
- Historical stress tests (COVID, Lehman, SVB)
- Drawdown recovery analysis
- R-Multiple distribution
- **SPY benchmark comparison on equity curve** ← MISSING, high priority

---

## UI/UX Overhaul — Research & Design Brief

### Research Findings: How Top Quant Platforms Structure Their UI

**QuantConnect (industry standard for quant platforms):**
- Results page layout: Runtime statistics banner at top → Equity curve with benchmark overlay (SPY default) → Drawdown chart → Exposure chart → Holdings table → Orders table → Trades table → Logs
- Built-in charts: Strategy Equity, Capacity, Drawdown, Benchmark, Exposure, Asset Sales Volume, Portfolio Turnover, Portfolio Margin, Performance
- Key insight: Equity curve and benchmark are ALWAYS visible together — this is the #1 thing institutional investors look at
- Statistics shown: Equity, Fees, Holdings, Net Profit, PSR (Probabilistic Sharpe Ratio), Return, Unrealized, Volume
- Asset plots: Individual asset price charts with order event annotations (buy/sell arrows)

**Institutional Trading Platforms (Bloomberg Terminal, Refinitiv Eikon):**
- Dark theme is dominant — reduces eye strain for 12+ hour sessions
- Information density is high but organized in clear visual hierarchy
- Color coding: green/red for P&L, blue for neutral/informational, yellow/orange for warnings
- Key metrics always visible without scrolling (sticky headers, summary bars)
- Charts are interactive with zoom, pan, crosshair, and period selectors (1D, 1W, 1M, 3M, 1Y, ALL)

**Design Principles from Research:**
- Data-first: Show numbers, not decorations. Every pixel should convey information.
- Hierarchy: Most important metrics (P&L, Sharpe, drawdown) at the top, always visible
- Consistency: Same chart style, same color coding, same interaction patterns across all pages
- Density: Institutional users want MORE data per screen, not less. Whitespace is wasted space.
- Benchmark: ALWAYS show performance relative to a benchmark (SPY for equities, BTC for crypto)

### Current AlphaCent UI Issues

1. **Missing SPY benchmark on equity curve** — The #1 thing any CIO looks at. Our equity curve shows absolute performance but no benchmark comparison. Need SPY overlay on the same chart.

2. **Page structure inconsistency** — Each page has a different layout pattern. Overview, Strategies, Orders, Risk, Analytics, Autonomous, Settings all feel like different apps.

3. **Information density too low** — Large cards with single metrics waste screen space. Institutional users want dense metric grids.

4. **Charts lack interactivity** — No zoom, no period selectors, no crosshair. Static charts feel amateur.

5. **No global summary bar** — Top quant platforms have a persistent summary bar showing key metrics (equity, daily P&L, open positions, active strategies) visible on every page.

6. **Color coding inconsistent** — Some pages use green/red for P&L, others don't. No consistent visual language.

7. **Loading states** — Tab switches show empty states briefly before data loads. Need skeleton loaders or pre-fetched data.

8. **Mobile responsiveness** — Cards stack poorly on smaller screens. Grid layouts break.

### Proposed UI/UX Improvements (Next Session)

#### Priority 1: Equity Curve with SPY Benchmark
- Add SPY price data to the equity curve chart (normalized to same starting point)
- Show alpha (portfolio return - SPY return) as a separate line or shaded area
- Period selectors: 1W, 1M, 3M, 6M, 1Y, ALL
- Drawdown chart below equity curve (synchronized zoom)

#### Priority 2: Global Summary Bar
- Persistent bar at top of every page (below navbar)
- Shows: Total Equity, Daily P&L ($ and %), Open Positions, Active Strategies, Current Regime, System Health
- Updates in real-time via WebSocket

#### Priority 3: Overview Page Redesign
- Hero section: Equity curve with SPY benchmark (full width)
- Below: 4-column metric grid (Equity, Daily P&L, Sharpe, Max Drawdown)
- Below: 2-column layout — Left: Position summary by asset class, Right: Recent trades
- Below: Strategy pipeline (proposed → backtested → active → retired)

#### Priority 4: Consistent Design System
- Standardize card sizes, padding, font sizes across all pages
- Consistent color coding: green (#22c55e) for positive, red (#ef4444) for negative, blue (#3b82f6) for neutral
- Consistent chart styling: dark background, grid lines, axis labels
- Consistent table styling: alternating row colors, sortable columns, pagination

#### Priority 5: Chart Interactivity
- Add Recharts/Lightweight Charts zoom and pan
- Period selectors on all time-series charts
- Crosshair with tooltip showing exact values
- Click-to-drill-down on data points

#### Priority 6: Page-Specific Improvements
- **Strategies page**: Add mini equity curves per strategy, sortable by Sharpe/return/trades
- **Risk page**: Add correlation matrix heatmap, sector exposure pie chart
- **Orders page**: Add order flow timeline visualization
- **Autonomous page**: Add cycle pipeline visualization (propose → WF → backtest → activate)

#### Priority 7: Performance Optimizations
- Pre-fetch all tab data on page load (not just active tab)
- WebSocket-driven real-time updates for equity, positions, P&L
- Lazy load heavy charts only when scrolled into view
- Cache API responses client-side with SWR or React Query

### Session Improvements (April 11, 2026 — Session 3: Institutional-Grade UI/UX Overhaul)

#### 75. Design System Foundation ✅
- Created `frontend/src/lib/design-tokens.ts` — centralized color constants, chart theme, card/table/layout tokens, spacing scale, typography rules
- Added CSS custom properties: `--color-positive`, `--color-negative`, `--color-chart-bg`, `--color-table-alt-row`, `--layout-section-gap`
- Updated Card.tsx and Table.tsx to use design tokens consistently
- Pre-built Recharts helpers: `chartAxisProps`, `chartGridProps`, `chartTooltipStyle`
- **Files**: `frontend/src/lib/design-tokens.ts`, `frontend/src/index.css`, `frontend/src/components/ui/Card.tsx`, `frontend/src/components/ui/Table.tsx`

#### 76. InteractiveChart Component ✅
- Reusable chart wrapper with mouse-wheel zoom, click-and-drag pan, crosshair tooltip, PeriodSelector (1W/1M/3M/6M/1Y/ALL)
- Dynamic Line/Area/Bar rendering from `dataKeys` prop, `children` prop for custom reference elements
- Used by ~15 charts across the platform
- **Files**: `frontend/src/components/charts/InteractiveChart.tsx`, `frontend/src/components/charts/PeriodSelector.tsx`, `frontend/src/components/charts/index.ts`

#### 77. GlobalSummaryBar ✅
- Persistent 48px bar below header on every page: Total Equity, Daily P&L ($+%), Open Positions, Active Strategies, Market Regime, System Health
- Green/red P&L coloring, yellow warning when WebSocket disconnected
- Real-time WebSocket updates, 30s polling fallback
- Condensed Multi-Timeframe returns (1D/1W/1M/YTD) at viewport > 1440px
- **Files**: `frontend/src/components/GlobalSummaryBar.tsx`, `frontend/src/components/DashboardLayout.tsx`

#### 78. Sidebar Responsive Collapse ✅
- Icon-only mode (64px) below 1024px, chevron toggle, Radix tooltips on hover
- localStorage persistence, smooth 300ms transitions, "A" branding when collapsed
- **Files**: `frontend/src/components/Sidebar.tsx`, `frontend/src/hooks/useMediaQuery.ts`

#### 79. Enhanced Skeleton Loaders ✅
- Shape-matching skeletons: ChartSkeleton, MetricGridSkeleton, TableSkeleton, HeatmapSkeleton, SummaryBarSkeleton, PageSkeleton
- `DataSection` wrapper: loading → skeleton, loaded → 200ms fade-in, error → retry button, 10s timeout
- Shimmer animation via CSS `@keyframes shimmer`
- **Files**: `frontend/src/components/ui/loading-skeletons.tsx`, `frontend/src/components/ui/skeleton.tsx`

#### 80. WebSocket Polling Optimization ✅
- `usePolling` hook: `skipWhenWsConnected` option — suppresses REST polling when WS connected, 30s fallback on disconnect, full refresh on reconnect
- Applied to GlobalSummaryBar, DashboardLayout, OverviewNew, PortfolioNew, OrdersNew
- **Files**: `frontend/src/hooks/usePolling.ts`, all consumer pages

#### 81. EquityCurveChart with SPY Benchmark ✅
- Portfolio (blue) + SPY (gray dashed) normalized to 100, alpha shading (green/red between lines)
- Crosshair tooltip with portfolio value, SPY value, alpha %
- Synchronized drawdown sub-chart (1/3 height), "Benchmark unavailable" badge
- Backend: `GET /analytics/spy-benchmark?period=3M` — queries historical_price_cache, falls back to Yahoo Finance
- **Files**: `frontend/src/components/charts/EquityCurveChart.tsx`, `src/api/routers/analytics.py`

#### 82. MultiTimeframeView ✅
- Compact horizontal row: 1D/1W/1M/3M/6M/YTD/1Y/ALL with absolute return + alpha
- Green/red background tint, clickable to update equity curve period, "N/A" for unavailable periods
- **Files**: `frontend/src/components/charts/MultiTimeframeView.tsx`

#### 83. Overview Page Redesign ✅
- Hero: full-width EquityCurveChart with SPY benchmark
- MultiTimeframeView row, 4-column Metric Grid (Equity, Daily P&L, Sharpe 30d, Max Drawdown)
- 2-column: position summary by asset class + recent trades (last 10)
- Strategy Pipeline: proposed → backtested → active → retired with clickable navigation
- **Files**: `frontend/src/pages/OverviewNew.tsx`, `frontend/src/services/api.ts`

#### 84. Rolling Statistics & Advanced Metrics Tab ✅
- Analytics tab: Rolling Sharpe, Beta, Alpha, Volatility charts with 30d/60d/90d window toggle
- Metric cards: PSR, Information Ratio, Treynor Ratio, Tracking Error
- Backend: `GET /analytics/rolling-statistics` — computes from equity snapshots + SPY benchmark
- **Files**: `frontend/src/pages/analytics/RollingStatisticsTab.tsx`, `src/api/routers/analytics.py`

#### 85. Performance Attribution Tab ✅
- Brinson model: allocation, selection, interaction effects per sector/asset class
- Stacked bar chart, attribution summary table, cumulative effects time-series
- Backend: `GET /analytics/performance-attribution` — Brinson decomposition from closed trades
- **Files**: `frontend/src/pages/analytics/PerformanceAttributionTab.tsx`, `src/api/routers/analytics.py`

#### 86. Tear Sheet Tab ✅
- Underwater plot (red filled area), worst drawdowns table (top 5), return distribution histogram with normal overlay
- Cumulative returns by year (green/red bars), monthly returns heatmap (year×month grid)
- Backend: `GET /analytics/tear-sheet` — drawdown, distribution, skew/kurtosis, annual/monthly returns
- **Files**: `frontend/src/pages/analytics/TearSheetTab.tsx`, `frontend/src/components/charts/UnderwaterPlot.tsx`, `frontend/src/components/charts/ReturnDistribution.tsx`, `frontend/src/components/charts/MonthlyReturnsHeatmap.tsx`

#### 87. TCA (Transaction Cost Analysis) Tab ✅
- "Cost as % of Alpha" headline metric, slippage by symbol/time/size, implementation shortfall table
- Fill rate analysis, execution quality trend, per-asset-class breakdown, worst executions (top 10)
- Backend: `GET /analytics/tca` — full TCA from filled orders
- **Files**: `frontend/src/pages/analytics/TCATab.tsx`, `src/api/routers/analytics.py`

#### 88. Strategies Page Enhancements ✅
- Inline sparkline equity curves per strategy, template rankings table (175+ templates), blacklists section, idle demotions log
- Backend: `GET /strategies/template-rankings` — aggregate metrics per template
- **Files**: `frontend/src/pages/StrategiesNew.tsx`, `src/api/routers/strategies.py`

#### 89. Risk Page Enhancements ✅
- Correlation heatmap (top 20 positions), sector exposure pie with P&L coloring
- Risk contribution bar chart, portfolio turnover chart, long/short exposure stacked area
- **Files**: `frontend/src/pages/RiskNew.tsx`, `frontend/src/components/charts/CorrelationHeatmap.tsx`

#### 90. Orders Page Timeline ✅
- Order flow timeline: scatter chart showing placed/filled/cancelled events on horizontal time axis (last 7 days)
- **Files**: `frontend/src/pages/OrdersNew.tsx`, `frontend/src/components/charts/OrderFlowTimeline.tsx`

#### 91. Autonomous Page Enhancements ✅
- Walk-forward analytics: per-cycle stats, pass rate chart over time
- Conviction score decomposition (horizontal stacked bars), similarity rejection display
- Backend: `GET /strategies/autonomous/walk-forward-analytics`
- **Files**: `frontend/src/pages/AutonomousNew.tsx`, `src/api/routers/strategies.py`

#### 92. Position Detail Drill-Down ✅
- New page at `/portfolio/:symbol` with asset plot (price chart + buy/sell order annotations)
- P&L time-series chart, order history table, "Order history unavailable" badge
- Backend: `GET /account/positions/{symbol}/detail`
- **Files**: `frontend/src/pages/PositionDetailView.tsx`, `frontend/src/components/charts/AssetPlot.tsx`, `src/api/routers/account.py`

#### 93. Data Management Enhancements ✅
- Data quality table: 297 symbols with quality score (color-coded), sortable/filterable
- FMP cache status, data source health (eToro/Yahoo/FMP/FRED), price sync timeline with progress bars
- Historical data coverage heatmap
- Backend: `GET /data/quality`
- **Files**: `frontend/src/pages/DataManagementNew.tsx`, `src/api/routers/data_management.py`

#### 94. System Health Page ✅
- New page at `/system-health`: circuit breaker states (green/yellow/red), monitoring service sub-tasks
- Trading scheduler status, eToro API health, background thread status, cache statistics
- 24-hour event timeline, WebSocket-driven updates, alert banner when circuit breaker OPEN
- Backend: `GET /control/system-health`
- **Files**: `frontend/src/pages/SystemHealthPage.tsx`, `frontend/src/lib/stores/system-health-store.ts`, `src/api/routers/control.py`

#### 95. Audit Log Page ✅
- New page at `/audit-log`: chronological log with virtual scrolling (@tanstack/react-virtual)
- Multi-filter (event type, symbol, strategy, severity, date range), full-text search (200ms debounce)
- Trade lifecycle detail view (signal → risk → order → fill → position → close)
- Signal rejections, strategy lifecycle events, risk limit events tabs
- CSV export: `AlphaCent_AuditLog_{start}_{end}.csv`
- Backend: `GET /audit/log`, `GET /audit/trade-lifecycle/{trade_id}`, `GET /audit/export`
- **Files**: `frontend/src/pages/AuditLogPage.tsx`, `frontend/src/lib/stores/audit-store.ts`, `src/api/routers/audit.py`

#### 96. Command Palette ✅
- Ctrl+K (Cmd+K on Mac) opens fuzzy search across symbols, strategies, pages, actions
- Radix Dialog, fuse.js fuzzy search, keyboard navigation (↑↓ + Enter), recent items in localStorage
- Rendered at App level, accessible from any page
- **Files**: `frontend/src/components/CommandPalette.tsx`, `frontend/src/hooks/useFuzzySearch.ts`, `frontend/src/App.tsx`

#### 97. PDF Tear Sheet Export ✅
- "Download Tear Sheet" button on Overview and Analytics pages
- Period selector (1M/3M/6M/1Y/ALL), html2canvas + jspdf for client-side PDF generation
- Professional layout: AlphaCent header, key stats table, chart captures, sector exposure, top/bottom performers
- Filename: `AlphaCent_TearSheet_{period}_{YYYY-MM-DD}.pdf`
- **Files**: `frontend/src/components/pdf/TearSheetGenerator.tsx`, `frontend/src/pages/OverviewNew.tsx`, `frontend/src/pages/AnalyticsNew.tsx`

#### 98. Mobile Responsive Layout ✅
- GlobalSummaryBar: Equity + Daily P&L only below 768px, horizontal scroll for rest
- Metric grids: 4 → 2 columns below 768px, charts: min 200px height, 2-column → single column below 640px
- Sidebar: icon-only below 1024px
- **Files**: All page components, `frontend/src/components/GlobalSummaryBar.tsx`, `frontend/src/components/charts/InteractiveChart.tsx`

#### 99. Design System Audit ✅
- Verified consistent card padding (16px), border radius (8px), border/bg colors across all pages
- Consistent color coding (green/red/blue/yellow), chart theme (dark bg, grid, axis), table alternating rows
- Font-mono for all numeric values, sans for labels
- **Files**: All page components

---

## New Dependencies Added (Session 3)
- `html2canvas` — DOM-to-canvas for PDF chart captures (~40KB)
- `jspdf` — PDF document generation (~280KB)
- `@tanstack/react-virtual` — Virtual scrolling for audit log (~10KB)
- `fuse.js` — Fuzzy search for command palette (~15KB)

## New Routes Added (Session 3)
- `/system-health` — System Health page (circuit breakers, monitoring, API health)
- `/audit-log` — Audit Log page (decision trail, trade lifecycle)
- `/portfolio/:symbol` — Position Detail view (asset plot, P&L chart)

## New Sidebar Nav Items (Session 3)
- System (◍) — System Health page
- Audit (◔) — Audit Log page

## New Backend Endpoints (Session 3)
- `GET /analytics/spy-benchmark` — SPY price data for benchmark overlay
- `GET /analytics/rolling-statistics` — Rolling Sharpe/Beta/Alpha/Volatility + PSR/IR/Treynor
- `GET /analytics/performance-attribution` — Brinson model decomposition
- `GET /analytics/tear-sheet` — Underwater plot, drawdowns, return distribution, monthly returns
- `GET /analytics/tca` — Full transaction cost analysis
- `GET /strategies/template-rankings` — Template performance rankings
- `GET /strategies/autonomous/walk-forward-analytics` — Walk-forward pass rates
- `GET /account/positions/{symbol}/detail` — Position drill-down with price history + order annotations
- `GET /control/system-health` — Circuit breakers, monitoring, scheduler, API health, cache stats
- `GET /data/quality` — Per-symbol data quality scores
- `GET /audit/log` — Filterable, paginated audit log
- `GET /audit/trade-lifecycle/{trade_id}` — Full trade lifecycle chain
- `GET /audit/export` — CSV export of audit log

## New Frontend Components (Session 3)
- `InteractiveChart` — Reusable chart with zoom/pan/crosshair/period selector
- `PeriodSelector` — 1W/1M/3M/6M/1Y/ALL button row
- `EquityCurveChart` — Portfolio + SPY benchmark with alpha shading + drawdown sub-chart
- `MultiTimeframeView` — Compact return cells across 8 timeframes
- `GlobalSummaryBar` — Persistent metrics bar on every page
- `CommandPalette` — Ctrl+K fuzzy search navigation
- `TearSheetGenerator` — PDF export with period selection
- `UnderwaterPlot` — Drawdown area chart
- `ReturnDistribution` — Histogram with normal overlay
- `MonthlyReturnsHeatmap` — Year×month color-coded grid
- `CorrelationHeatmap` — Pairwise correlation matrix
- `OrderFlowTimeline` — Scatter chart of order events
- `AssetPlot` — Price chart with buy/sell annotations
- `DataSection` — Loading/error/timeout state wrapper

## New Zustand Stores (Session 3)
- `system-health-store.ts` — Circuit breakers, monitoring, scheduler state
- `audit-store.ts` — Audit log entries, filters, pagination, CSV export

## New Analytics Tab Components (Session 3)
- `RollingStatisticsTab` — Rolling metrics + PSR/IR/Treynor/Tracking Error
- `PerformanceAttributionTab` — Brinson model with sector/asset class toggle
- `TearSheetTab` — Underwater plot, drawdowns, distribution, heatmap
- `TCATab` — Slippage analysis, implementation shortfall, fill rates

## New TypeScript Types (Session 3)
- `frontend/src/types/analytics.ts` — RollingStatsData, AttributionData, TearSheetData, TCAData


### Session Improvements (April 11, 2026 — Session 4)

#### 75. UI Data Fixes Across All Pages ✅
- **Overview**: Strategy Pipeline now shows cumulative counts (Backtested includes all that passed through Proposed, etc.)
- **Portfolio**: Position Allocation changed from pie chart to horizontal bar chart; value calculation falls back to entry_price when current_price is 0
- **Settings**: Width fixed from `max-w-7xl` (1280px) to `max-w-[1800px]` to match all other pages
- **Strategies**: Blacklisted Combos and Idle Demotions now fetch from dedicated backend endpoints (`/strategies/blacklisted-combos`, `/strategies/idle-demotions`) reading from config JSON files instead of strategy metadata
- **Autonomous**: Lifecycle Metrics now show cumulative totals across ALL cycles (SUM of all AutonomousCycleRunORM records) instead of just last cycle
- **Analytics**: Template Performance fixed — was reading template name from `strategy.rules.template` (wrong field), now reads from `strategy.strategy_metadata.template_name`
- **Data Management**: Data Quality API call fixed wrong response key (`data` → `entries`); Data Source Health treats "configured" status as blue instead of red; added eToro and Yahoo Finance status to monitoring endpoint
- **System**: Fixed eToro API health reading wrong attribute (`_etoro_client` → `etoro_client`); added `_signals_last_run`, `_orders_last_run`, `_next_run_time` tracking to trading scheduler
- **Audit Log**: Fixed total count field name mismatch (`total_count` → `total`) in audit store
- **Files**: `frontend/src/pages/OverviewNew.tsx`, `PortfolioNew.tsx`, `SettingsNew.tsx`, `StrategiesNew.tsx`, `DataManagementNew.tsx`, `frontend/src/services/api.ts`, `frontend/src/lib/stores/audit-store.ts`, `src/api/routers/strategies.py`, `analytics.py`, `control.py`, `data_management.py`, `src/core/trading_scheduler.py`

#### 76. Position Sync UniqueViolation Fix ✅
- `sync_positions()` only loaded open positions into lookup map — when eToro returned a position whose `etoro_position_id` existed on a closed DB record, it tried to INSERT a duplicate
- Added check for closed positions with same `etoro_position_id` before INSERT — reopens closed record instead of creating duplicate
- Added safety catch on commit for remaining edge cases (rollback + retry next cycle)
- **Files**: `src/core/order_monitor.py`

#### 77. Deferred Strategy Retirement ✅ (CRITICAL)
- **Problem**: Strategies with health_score=0 or decay_score=0 were immediately retired AND force-closed all open positions via `pending_closure=True`. This crystallized paper losses — 7 of 11 stop-loss exits would have been profitable if held.
- **Fix**: Strategies with open positions are now marked `pending_retirement` in metadata instead of immediately retired. No positions get force-closed. The strategy stops generating new signals (excluded from signal generation loop), but existing positions run to their SL/TP naturally via trailing stops. Once all positions close, the next health check finalizes the retirement to RETIRED status.
- Signal generation in `trading_scheduler.py` now skips strategies with `pending_retirement=True`
- Pending retirement finalization runs at the top of `_check_strategy_health()` — checks if all positions for pending-retirement strategies have closed
- **Files**: `src/core/monitoring_service.py`, `src/core/trading_scheduler.py`

#### 78. SL/TP and Risk Parameter Overhaul ✅ (CRITICAL)
- **Problem**: 4% stop losses on stocks were too tight for multi-day holds — getting whipsawed on normal volatility. 34% win rate on closed trades. Average loser held 45h vs winner 77h.
- **Asset class parameters widened**:
  - Stocks: SL 4%→6%, TP 10%→15% (2.5:1 R:R)
  - ETFs: SL 4.5%→6%, TP 10%→15%
  - Forex: SL 1.5%→2%, TP 3%→5%
  - Crypto: SL 6%→8%, TP 12%→20%
  - Index: SL 4%→5%, TP 10%→12%
  - Commodity: SL 3%→4%, TP 8%→10%
- **ATR floor raised**: 1.5x → 2x ATR (both at proposal time and order execution time)
- **Strategy type baselines widened**: Mean reversion SL 2%→3%, trend following SL 4%→5%/TP 10%→15%
- **SL clamp ceiling raised**: 8% → 12% (high-beta stocks need room)
- **Minimum R:R ratio**: 1.5:1 → 2:1 (enforced at proposal and asset class override)
- **Trailing stops**: Activation 5%→8% profit, distance 3%→4% trail
- **Partial exits**: First level at 10% profit taking 33% (was 5% profit taking 50%)
- **Note**: These changes affect NEW strategies only. Existing positions keep their current SL/TP on eToro.
- **Files**: `config/autonomous_trading.yaml`, `src/strategy/strategy_proposer.py`, `src/execution/order_executor.py`

---

## Current System State (April 11, 2026 — Updated Session 4)

- **Database:** PostgreSQL 16 on EC2, 32 tables, 780K+ rows
- **Account:** eToro DEMO, balance ~$162K, equity ~$464K
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto)
- **Active strategies:** ~98 (some now in pending_retirement state)
- **Open positions:** ~123 (82 profitable, 32 losing, +$5,517 unrealized)
- **Closed positions (April):** 95 trades, -$674 realized, 34% win rate
- **Total P&L (April):** +$4,781 ($5,517 unrealized - $736 realized)
- **Top templates:** RSI Dip Buy (+$3,010), BB Middle Band Bounce (+$1,760)
- **Monitoring:** 24/7 + CloudWatch alerting
- **Market regime:** Equity: ranging_low_vol
- **Key change:** Retirement no longer force-closes positions; wider SL/TP for new strategies

---

## Open Items (Updated Session 4)

### Performance
- Monitor win rate on closed trades after SL/TP changes (target: >45% from current 34%)
- Track whipsaw rate: how many stopped-out positions would have been profitable if held
- Consider ATR-based dynamic SL per position instead of fixed percentage per asset class
- Evaluate if trailing stop activation at 8% is optimal (was 5%)

### From Previous Sessions
1. Signal generation — Are conviction scores using meaningful inputs? *(partially addressed)*
2. Template-symbol matching — Should template weights decay over time?
3. Risk controls — Portfolio-level VaR check before new positions
4. Order execution — Is signal coordination too aggressive?
5. Performance feedback loop — Is it chasing past winners?

### Infrastructure
- Consider t3.small downgrade — waiting on CloudWatch memory data
- FMP API rate limit (300/min) — monitor with corrected per-call counting


### Session Improvements (April 11, 2026 — Session 5: Profitability Audit & Alpha Generation)

#### 79. Profitability Audit & Short Exposure Reduction ✅
- Full P&L audit: 95 closed trades, -$674 realized, 34% win rate, +$5,539 unrealized
- **Root cause #1**: Shorts bleeding -$1,114 (29% win rate) — fighting a recovering market
- **Root cause #2**: "Etoro Closed" positions (-$571) — DEMO account artifact
- **Root cause #3**: R-multiples terrible — almost no trades above +1R
- Reduced `min_short_pct` from 35% to 15% in ranging/ranging_low_vol regimes
- **Files**: `config/autonomous_trading.yaml`

#### 80. Minimum Position Size $2K ✅
- Raised minimum from $10 to $2,000 for all asset classes (was 57 positions under $1K generating noise)
- Bump guard raised from 3x to 10x — allows $200+ calculated sizes to be bumped to $2K
- Post-adjustment minimum also set to $2K with same 10x guard
- **Files**: `src/risk/risk_manager.py`, `src/execution/order_executor.py`

#### 81. Partial Exit & Trailing Stop Optimization ✅
- Removed first partial exit at 10% profit (was capping winners too early)
- Only partial exit now at 18% profit taking 33%
- Trailing stop activation raised from 8% to 12% (was getting shaken out on normal volatility)
- **Files**: `config/autonomous_trading.yaml`

#### 82. Conviction Threshold & Dynamic Template Weighting ✅
- Conviction threshold raised from 55 to 60
- Performance feedback range widened: template weights 0.4x-1.5x (was 0.7x-1.15x)
- P&L-weighted scoring with confidence scaling (more trades = more trust)
- Symbol score cap widened to ±15 (was ±5)
- **Files**: `config/autonomous_trading.yaml`, `src/strategy/strategy_proposer.py`

#### 83. Direction-Aware Fundamental Quality Scoring ✅ (±15 conviction points)
- New conviction component: `_score_fundamental_quality()` in ConvictionScorer
- LONG signals: strong fundamentals (earnings beat, revenue growth, insider buying, high ROE, buybacks) → up to +15
- SHORT signals: weak fundamentals → up to +15 (don't short quality, short garbage)
- Uses FundamentalData from FMP: earnings_surprise, revenue_growth, insider_net_buying, roe, shares_change_percent
- Only applies to stocks — forex/crypto/commodities/indices/ETFs return 0
- **Files**: `src/strategy/conviction_scorer.py`

#### 84. Multi-Strategy Confluence ✅
- Multiple strategies can now open positions in the same symbol (was blocked at 1)
- Position limit: 5 per symbol per timeframe bucket (1d/4h/1h independent)
- Same-strategy dedup preserved (a strategy can't double its own position)
- Cross-strategy pending order blocking removed (was preventing confluence)
- Signal coordination keeps top N by confidence instead of just top 1
- **Files**: `src/core/trading_scheduler.py`, `config/autonomous_trading.yaml`

#### 85. EXIT Signal Processing ✅ (CRITICAL)
- **Problem**: DSL exit conditions (e.g., `RSI(14) > 62`) were evaluated in backtesting but silently dropped in live trading. Positions only closed via SL/TP/trailing stops.
- **Fix**: EXIT_LONG/EXIT_SHORT signals now flow through the trading scheduler. When a strategy's exit conditions fire, the position is marked `pending_closure` and the monitoring service closes it on eToro.
- This closes the gap between backtest performance (which assumed exits) and live performance (which ignored them)
- **Files**: `src/core/trading_scheduler.py`

#### 86. Position Matching Fix ✅
- **Bug**: When multiple strategies traded the same symbol, the position creation code matched ANY open position with same symbol/side — stealing another strategy's eToro position ID
- **Fix**: Match by eToro position ID first, then fall back to same-strategy + symbol + side with no eToro ID yet
- **Files**: `src/core/trading_scheduler.py`

#### 87. Crypto 4H/1H Templates ✅
- **Research**: HTX/KuCoin backtests show 4H MACD on BTC: +96% vs +49% buy-and-hold, ETH: +205% vs +53%. 1H and below underperform 90% of the time.
- **4H templates** (proven alpha timeframe): Crypto 4H MACD Trend, Crypto 4H RSI Dip Buy, Crypto 4H EMA Momentum, Crypto 4H BB Squeeze Breakout
- **1H templates** (selective, high-conviction only): Crypto 1H RSI Extreme Bounce (RSI < 20), Crypto 1H BB Extreme Dip (BB lower at 2.5 std)
- Per-timeframe position limits: 5 per symbol per 1d/4h/1h bucket (BTC can have up to 15 total)
- **Files**: `src/strategy/strategy_templates.py`, `src/core/trading_scheduler.py`

#### 88. Crypto Template SL/TP Fix ✅
- All ~40 pre-existing crypto intraday templates were missing `"interval": "1h"` in metadata
- Auto-set interval from `intraday`/`interval_4h` flags in `__post_init__`
- Enforced 4% SL / 8% TP floor for all crypto templates (eToro's 2% round-trip cost)
- Pre-existing 4H crypto templates widened from 3.5-4% SL / 6-8% TP to 5-6% SL / 12-15% TP
- **Files**: `src/strategy/strategy_templates.py`

#### 89. Full Template Audit ✅ (252 → 241 templates)
- **Removed 11 duplicates**: RSI Overbought Short, Stochastic Overbought Short, Bollinger Band Short, Bollinger Volatility Breakout, Low Vol RSI Mean Reversion, Volume Dry-Up Reversal Long, Keltner Midline Bounce Long, Stochastic Midrange Long, MACD Momentum, 4H Downtrend Oversold Bounce (R:R=1.1), BB Midband Reversion Tight (entry≈exit)
- **Enforced floors in `__post_init__`**: 1d stocks: 3% SL / 5% TP minimum. Crypto: 4% SL / 8% TP minimum. All templates: R:R ≥ 1.5 (auto-widens TP)
- 3 removed templates have 6 open positions — will run their course naturally, just won't be reproduced
- **Files**: `src/strategy/strategy_templates.py`

---

## Current System State (April 11, 2026 — Updated Session 5)

- **Database:** PostgreSQL 16 on EC2, 32 tables, 780K+ rows
- **Account:** eToro DEMO, balance ~$162K, equity ~$464K
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto)
- **Active strategies:** ~101 DEMO + 97 BACKTESTED
- **Open positions:** ~125 (including 2 new BTC + 2 new ETH from multi-strategy confluence)
- **Templates:** 241 (was 252, removed 11 duplicates)
- **Crypto templates:** 77 total (56 on 1h, 10 on 4h, 11 on 1d)
- **Monitoring:** 24/7 + CloudWatch alerting + EXIT signal processing
- **Market regime:** Equity: ranging_low_vol, Crypto: trending_up
- **Key changes:** EXIT signals now close positions, multi-strategy confluence (up to 5 per symbol per timeframe), $2K minimum positions, direction-aware fundamental scoring

---

## Open Items (Updated Session 5)

### Performance Monitoring (Next Week)
- Monitor win rate impact of wider SL/TP and EXIT signal processing (target: >45%)
- Track how many positions are closed by EXIT signals vs SL/TP vs trailing stops
- Monitor multi-strategy confluence: are 5 BTC LONGs from different strategies correlated or independent?
- Check if $2K minimum is rejecting too many signals (watch for "below minimum" log frequency)
- Evaluate fundamental quality scoring impact on short selection quality

### From Previous Sessions
1. ~~Signal generation — Are conviction scores using meaningful inputs?~~ ✅ (fundamental quality + carry + cycle)
2. Template-symbol matching — Should template weights decay over time? *(addressed with dynamic weighting)*
3. Risk controls — Portfolio-level VaR check before new positions
4. ~~Order execution — Is signal coordination too aggressive?~~ ✅ (multi-strategy confluence)
5. ~~Performance feedback loop — Is it chasing past winners?~~ ✅ (P&L-weighted, confidence-scaled)
6. ~~EXIT signals not being processed~~ ✅ (wired through trading scheduler)

### Infrastructure
- Consider t3.small downgrade — waiting on CloudWatch memory data
- FMP API rate limit (300/min) — monitor with corrected per-call counting

### Session Improvements (April 12, 2026 — Session 6: QuantFury-Inspired UI Overhaul Planning)

#### 100. Tab Styling Overhaul ✅ (minor, pre-planning)
- Replaced pill/rounded-bg tab style with underline-indicator pattern across all pages
- Active tabs: green (#10b981) bottom border (2px) + green text, inactive: muted gray
- Removed all per-page tab overrides (StrategiesNew, AnalyticsNew, OrdersNew, SettingsNew, PortfolioNew, AutonomousNew, RiskNew)
- Cleaned up TabsList grid layouts to `w-full overflow-x-auto` everywhere
- Card shadow deepened, sidebar active state changed to left accent bar, scrollbars thinned
- **Files**: `frontend/src/components/ui/tabs.tsx`, `frontend/src/components/ui/Card.tsx`, `frontend/src/components/Sidebar.tsx`, `frontend/src/components/GlobalSummaryBar.tsx`, `frontend/src/components/DashboardLayout.tsx`, `frontend/src/index.css`, all page components with TabsList

#### 101. QuantFury-Inspired UI Overhaul — Spec Updated (NOT YET IMPLEMENTED)
- **Problem identified**: The UI has all the right data but presents it poorly. Flat vertical-scroll layout, sidebar eating 256px, no visual hierarchy, can't tell which tab is active, low information density, no command-center feel. Compared against QuantFury, Quant Landing, and Bloomberg-style trading terminals.
- **Research conducted**: QuantFury web platform (horizontal nav, multi-panel layout, live position strip, contextual widgets, dense data), Devexperts trading UX best practices (simplicity + power, avoid clutter, every pixel serves a purpose), HedgeUI resizable panel patterns (react-resizable-panels, CSS-based resize, localStorage persistence), professional trading terminal design patterns.
- **Spec updated**: Added Requirements 22-30 and Phase 2 tasks (17-24) to `.kiro/specs/quant-platform-ui-overhaul/`
- **9 new requirements**:
  - Req 22: Horizontal TopNavBar replacing sidebar (reclaim ~200px horizontal space)
  - Req 23: Multi-panel resizable layout system (react-resizable-panels)
  - Req 24: Live position ticker strip with WebSocket updates
  - Req 25: Contextual bottom widget panels on ALL pages (Top Movers, Recent Signals, Market Regime, Strategy Alerts, Macro Pulse)
  - Req 26: Compact metric rows + dense tables (2x data density)
  - Req 27: Panel title bars with collapse/refresh/close actions
  - Req 28: Chart-as-hero layout on Overview (≥60% of content area)
  - Req 29: Consistent PageTemplate across all 11 pages
  - Req 30: Micro-interactions (animated numbers, flash on change, hover glow, tab transitions)
- **Phase 2 tasks** (all unchecked, ready to execute):
  - Task 17: Build ALL shared components (TopNavBar, MetricsBar, PositionTickerStrip, PanelHeader, ResizablePanelLayout, PageTemplate, CompactMetricRow, BottomWidgetZone, 5 widgets, DenseTable, tighter Cards) + 3 backend endpoints + DashboardLayout restructure
  - Task 18: Checkpoint
  - Task 19: Redesign ALL 11 pages with panel layouts (Overview 3-panel, Portfolio/Orders/Strategies/Autonomous/Risk/Data/System/Audit 2-panel, Analytics/Settings full-width)
  - Task 20: Checkpoint
  - Task 21: Micro-interactions (animated numbers, flash, hover glow, tab fade-in)
  - Task 22: Checkpoint
  - Task 23: Cross-page audit + performance audit + cleanup deprecated components
  - Task 24: Final checkpoint + deploy
- **New dependency**: `react-resizable-panels` (~12KB)
- **New backend endpoints needed**: `GET /dashboard/top-movers`, `GET /dashboard/recent-signals`, `GET /dashboard/strategy-alerts`
- **Components to deprecate**: Sidebar.tsx (→ TopNavBar), GlobalSummaryBar.tsx (→ MetricsBar)
- **NOT YET IMPLEMENTED** — spec is ready, execution starts next session from Task 17
- **Files**: `.kiro/specs/quant-platform-ui-overhaul/requirements.md`, `design.md`, `tasks.md`

---

## Current System State (April 12, 2026 — Updated Session 6)

- **Database:** PostgreSQL 16 on EC2, 32 tables, 780K+ rows
- **Account:** eToro DEMO, balance ~$162K, equity ~$464K
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto)
- **Active strategies:** ~101 DEMO + 97 BACKTESTED
- **Open positions:** ~125
- **Templates:** 241
- **Monitoring:** 24/7 + CloudWatch alerting + EXIT signal processing
- **Market regime:** Equity: ranging_low_vol, Crypto: trending_up
- **Frontend:** Tab underline styling applied, all other Phase 1 UI overhaul complete (tasks 1-16 done). Phase 2 (QuantFury layout overhaul, tasks 17-24) spec'd but NOT started.
- **Key next action:** Execute Phase 2 starting from Task 17 in `.kiro/specs/quant-platform-ui-overhaul/tasks.md`

---

## Open Items (Updated Session 6)

### UI/UX — Phase 2 Execution (NEXT SESSION PRIORITY)
- Execute Phase 2 tasks 17-24 from `.kiro/specs/quant-platform-ui-overhaul/tasks.md`
- Start with Task 17: install react-resizable-panels, build all shared components, backend endpoints, restructure DashboardLayout
- Then Task 19: redesign all 11 pages with panel layouts
- Then Tasks 21-24: micro-interactions, audit, cleanup, deploy

### Performance Monitoring
- Monitor win rate impact of wider SL/TP and EXIT signal processing (target: >45%)
- Track EXIT signal vs SL/TP vs trailing stop close ratios
- Monitor multi-strategy confluence correlation
- Check $2K minimum rejection frequency
- Evaluate fundamental quality scoring on short selection

### Infrastructure
- Consider t3.small downgrade — waiting on CloudWatch memory data
- FMP API rate limit (300/min) — monitor with corrected per-call counting
- **Deploy workflow improvement needed**: When SCP'ing `autonomous_trading.yaml` to EC2, API keys get overwritten. Either: (a) re-patch keys after SCP via Secrets Manager fetch, or (b) only SCP the config sections that changed and leave keys alone. Current workaround: always run the Secrets Manager patch step after any config file SCP. This should be automated in the deploy script.

### From Previous Sessions
1. ~~Signal generation — conviction scores~~ ✅
2. Template-symbol matching — dynamic weighting ✅
3. Risk controls — Portfolio-level VaR check before new positions (still open)
4. ~~Order execution — multi-strategy confluence~~ ✅
5. ~~Performance feedback loop~~ ✅
6. ~~EXIT signals~~ ✅


### Session Improvements (April 12, 2026 — Session 7: Phase 2 QuantFury Layout Overhaul)

#### 102. Layout Foundation — Shared Components + Dependencies ✅
- Installed `react-resizable-panels` (v4.10.0)
- **TopNavBar** replaces Sidebar: horizontal nav (48px), brand left, 11 nav links center, account actions right. Active page: green bottom border + green text. Hamburger menu below 768px. Preserves badge counts, permission filtering, user info.
- **MetricsBar** merges Header + GlobalSummaryBar into single 40px row: connection dot, Equity, Daily P&L ($+%), Positions, Strategies, Regime badge, Health score, Last Synced. Green/red P&L, yellow on WS disconnect. Condensed Multi-Timeframe at >1440px.
- **PositionTickerStrip** (36px): horizontal scrollable strip, top 15 positions by value, WS-driven flash animation, click → `/portfolio/:symbol`, hidden below 768px.
- **PanelHeader**: darker bg header with collapse/expand (persisted to localStorage), refresh, optional close. Flex container with overflow-auto body.
- **ResizablePanelLayout**: wraps react-resizable-panels, horizontal/vertical splits, min 250px panels, CSS-based resize, persist sizes to localStorage, single-column below 1024px.
- **PageTemplate**: consistent page shell with header zone + main content + BottomWidgetZone. `compact` prop eliminates 64px title, shows 36px action bar only.
- **CompactMetricRow**: single 40px row, 4-8 inline metrics with AnimatedNumber, trend indicators.
- **BottomWidgetZone**: horizontal row of 5 lazy-loaded closable mini-widgets (TopMovers, RecentSignals, MarketRegime, StrategyAlerts, MacroPulse), max 200px, visibility persisted to localStorage.
- **DenseTable variant**: 32px rows, 12px font, 8px/4px padding on Table.tsx.
- **Card.tsx**: reduced padding to p-3, hover glow border transition.
- **DashboardLayout restructured**: `flex flex-col h-screen` → TopNavBar → MetricsBar → PositionTickerStrip → `<main>` (full width). Sidebar and old header removed.
- **Files**: `frontend/src/components/TopNavBar.tsx`, `MetricsBar.tsx`, `PositionTickerStrip.tsx`, `PageTemplate.tsx`, `BottomWidgetZone.tsx`, `layout/PanelHeader.tsx`, `layout/ResizablePanelLayout.tsx`, `trading/CompactMetricRow.tsx`, `widgets/*.tsx`, `ui/Table.tsx`, `ui/Card.tsx`, `DashboardLayout.tsx`

#### 103. Backend Widget Endpoints ✅
- `GET /dashboard/top-movers?mode=DEMO` — top 5 gainers + losers by P&L %
- `GET /dashboard/recent-signals?mode=DEMO&limit=5` — last N signals with conviction, direction, symbol
- `GET /dashboard/strategy-alerts?mode=DEMO&limit=10` — lifecycle events (activations, retirements, pending closures, demotions)
- **Files**: `src/api/routers/dashboard.py`, `src/api/app.py`, `frontend/src/services/api.ts`

#### 104. All 11 Pages Redesigned with Panel Layouts ✅
- **Overview**: 3-panel command center (25% metrics/pipeline, 50% equity curve hero, 25% activity)
- **Portfolio**: 2-panel (70% positions DenseTable with inline tabs, 30% summary with pie/allocation). Tabs moved INTO PanelHeader bar. All Card wrappers removed.
- **Orders**: 2-panel (65% OrderFlowTimeline hero + orders DenseTable, 35% execution quality + recent fills)
- **Strategies**: 2-panel (65% strategy tables with 10 inline tabs, 35% intelligence sidebar with rankings + lifecycle events). Custom inline tab buttons in PanelHeader.
- **Autonomous**: 2-panel (65% all 7 tabs, 35% cycle intelligence with progress + WF sparkline)
- **Risk**: 2-panel (60% correlation hero + tabs, 40% risk summary with sector pie + contribution bars)
- **Analytics**: full-width with CompactMetricRow + 10 tabs. MetricCards replaced with compact key-value grids.
- **Data Management**: 2-panel (65% quality DenseTable, 35% data health + FMP cache + sync progress)
- **System Health**: 2-panel (60% event timeline + service cards, 40% circuit breakers + API health)
- **Audit Log**: 2-panel (65% virtual-scroll DenseTable + filters, 35% summary + rejections + lifecycle)
- **Settings**: full-width with tabs, compact mode
- All pages use `compact={true}` on PageTemplate (eliminates 64px page title)
- **Files**: All 11 page components in `frontend/src/pages/`

#### 105. Micro-Interactions and Visual Polish ✅
- **AnimatedNumber**: count-up/down over 300ms using requestAnimationFrame with ease-out cubic. Applied to MetricsBar, PositionTickerStrip, CompactMetricRow.
- **FlashWrapper**: green/red 20% opacity flash fading 500ms on value change. Applied to MetricsBar equity/P&L, PositionTickerStrip chips.
- **Hover glow**: Card border-color transition, table row highlight, resize handle highlight, ticker chip scale(1.02).
- **Tab fade-in**: 150ms fade-in animation on TabsContent switch via CSS keyframes.
- **React.memo**: Applied to MetricsBar, PositionTickerStrip, AnimatedNumber, FlashWrapper, CompactMetricRow to prevent unnecessary re-renders.
- **Files**: `frontend/src/components/ui/animated-number.tsx`, `flash-wrapper.tsx`, `Card.tsx`, `tabs.tsx`, `Table.tsx`, `index.css`

#### 106. Cleanup and Audit ✅
- Removed deprecated `Sidebar.tsx` and `GlobalSummaryBar.tsx` (zero remaining imports)
- Cross-page visual audit: verified TopNavBar active states, PanelHeader consistency, DenseTable usage, CompactMetricRow presence, BottomWidgetZone on all pages
- Performance audit: lazy-loaded all 5 bottom widgets, verified CSS-based panel resize (no JS re-renders during drag)
- Fixed scroll clipping: PanelHeader updated to `flex flex-col h-full min-h-0` with `overflow-auto` body wrapper. Removed redundant `overflow-hidden` from all panel wrappers.
- Fixed Strategies crash: `useState` hook was declared after early return (React error #310) — moved to top of component.
- Removed redundant panel titles: "Autonomous" → "Control & Activity", "Risk" → "Analysis", "System" → "Services"

#### 107. Bloomberg Terminal Density Redesign ✅
- **Problem**: Initial Phase 2 implementation just wrapped old content in new panel containers ("pig with lipstick"). Old card-based layout with big headers, excessive padding, and wasted vertical space persisted inside panels.
- **Fix**: Proper redesign eliminating all Card wrappers inside panels, replacing MetricCards with compact key-value grids, moving tabs into PanelHeader bars, reducing spacing from gap-4/6 to gap-2, reducing padding from p-3/4 to p-2.
- Portfolio: tabs inline in PanelHeader, edge-to-edge table, direct key-value pairs in side panel
- Strategies: 10 tabs inline in PanelHeader with custom buttons, all Card wrappers removed from Overview/Active/Backtested tabs
- Analytics: MetricCards → compact grids, CIO Metrics → inline grid, spacing tightened throughout
- All other pages: compact mode, tightened spacing, removed Card wrappers

---

## Current System State (April 12, 2026 — Updated Session 7)

- **Database:** PostgreSQL 16 on EC2, 32 tables, 780K+ rows
- **Account:** eToro DEMO, balance ~$162K, equity ~$463K
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto)
- **Active strategies:** ~97 DEMO + backtested
- **Open positions:** ~127
- **Monitoring:** 24/7 + CloudWatch alerting + EXIT signal processing
- **Market regime:** Equity: ranging_low_vol
- **UI:** Phase 2 QuantFury layout complete — TopNavBar, MetricsBar, PositionTickerStrip, resizable panels, compact PageTemplate, DenseTable, BottomWidgetZone on all pages

---

## Phase 2 Polish — Remaining Items

These items were identified during user testing of the Phase 2 layout and should be addressed before starting Phase 3:

### Visual Polish
- Some pages still have Card-wrapped sections inside tabs that could be further flattened (Autonomous Control tab, Risk Advanced tab)
- Orders page: "Execution Quality" section in side panel still uses large font sizes for the 3 metrics — could be more compact
- Autonomous page: "Trading Cycle Pipeline" component still uses old circular icon style — could be redesigned to match the new dense aesthetic
- Analytics Performance tab: Daily P&L table still uses Card wrapper — should be a direct table

### Data Issues
- `/strategies/blacklisted-combos` returns 422 (Unprocessable Entity) — endpoint may need `mode` query parameter
- `/strategies/template-rankings` returns 404 — endpoint may not be deployed or route not registered
- `/strategies/idle-demotions` returns 422 — same mode parameter issue

### Functional
- Settings page: still has old-style form layout with large headings ("✨ Alpha Edge Settings") — could be more compact
- BottomWidgetZone: "Never synced" shows in MetricsBar — should show actual last sync time after first sync

---

## Phase 3 Plan: Professional Charting + Real-Time Streaming + Workspace Presets

Phase 3 replaces Recharts with TradingView Lightweight Charts for all time-series visualizations, adds real-time price streaming via WebSocket, and implements saved workspace presets. See `.kiro/specs/quant-platform-ui-overhaul/tasks.md` Tasks 25-32 for full details.

### Key deliverables:
1. **TradingView Lightweight Charts migration** (Tasks 25.1-25.6): TvChart wrapper, EquityCurveChart migration, AssetPlot candlestick chart, all remaining time-series charts, non-time-series alternatives (custom SVG), Recharts removal
2. **Real-time price streaming** (Tasks 27.1-27.2): Backend WebSocket price ticks, frontend chart updates via `series.update()`
3. **Saved workspace presets** (Tasks 29.1-29.2): 5 user presets + 3 defaults (Trading/Monitoring/Analysis), workspace switcher in TopNavBar

### Dependencies:
- `lightweight-charts` — TradingView charting library
- Recharts fully removed after migration

### New files:
- `frontend/src/components/charts/TvChart.tsx` — TradingView wrapper
- `frontend/src/components/charts/TvPeriodSelector.tsx` — Period selector for TvChart
- `frontend/src/lib/workspace-presets.ts` — Preset management

---

## Nginx Config Reminder

The Nginx config at `/etc/nginx/sites-available/alphacent` must include `/dashboard` in the API proxy regex (added in Session 7 for the widget endpoints). Current proxy regex includes: `/auth`, `/config`, `/account`, `/strategies`, `/orders`, `/market-data`, `/control`, `/ws`, `/performance`, `/risk`, `/analytics`, `/signals`, `/alerts`, `/data`, `/audit`, `/dashboard`.


---

### Session Improvements (April 12, 2026 — Session 8: Tab Interior Redesign + Font Normalization)

#### 103. Cross-Cutting UI Polish ✅
- **DataFreshnessIndicator**: Replaced verbose "Data as of: Apr 12, 2026, 15:40 GMT+1" with compact colored dot + relative time (e.g. "2m")
- **TearSheetGenerator**: Icon-only download button instead of full text "Tear Sheet" button
- **All pages**: Replaced verbose "Refresh" / "Export" buttons with compact icon-only buttons
- **Tabs component**: Increased font size from `text-sm` (14px) to `text-[13px] font-semibold` for better visibility
- **PageTemplate**: Compact mode now renders 0px header (was 36px wasted row with just dot + icon)
- **Files**: `DataFreshnessIndicator.tsx`, `TearSheetGenerator.tsx`, `tabs.tsx`, `PageTemplate.tsx`, all page files

#### 104. Overview Page Fixes ✅
- Added more quant metrics: Unrealized P&L, Win Rate, Cash, Daily % (separate from Daily P&L)
- Fixed Daily P&L display — no more compound string with floating point issues
- Equity curve restored with `height={450}` (was broken by `height="100%"` causing 0px container)
- **Files**: `OverviewNew.tsx`, `EquityCurveChart.tsx`, `InteractiveChart.tsx`

#### 105. New Utility Components for Tab Interior Design ✅
- **SectionLabel**: Flat uppercase label (11px gray-400) replacing nested PanelHeaders inside tabs
- **MetricGrid**: Dense inline metric boxes (10px labels, 13px values) replacing MetricCard grids
- **FilterBar**: Compact inline filter row replacing scattered filter patterns
- **Files**: `frontend/src/components/ui/SectionLabel.tsx`, `MetricGrid.tsx`, `FilterBar.tsx`

#### 106. Tab Interior Redesign — All 11 Pages ✅
- **Autonomous** (7 tabs): All nested PanelHeaders flattened. Control tab: status badges + research filters + controls + schedule all flat. Lifecycle: stage buttons + filter bar + table. Activity: filter bar + table. Signals: metric grid + rejection bars + signal table. Performance: 8-metric grid + template bars + threshold grid. Walk-Forward: cycle table + pass rate chart + similarity table. Conviction: flat stacked bars.
- **Risk** (5 tabs): Overview: SectionLabel for Risk Status/Limits/Alerts, MetricGrid for metrics. Positions: FilterBar + DataTable. Advanced: SectionLabel for VaR/Stress/CIO. History: SectionLabel + charts. Exposure: SectionLabel + charts.
- **Strategies** (10 tabs): Overview: MetricGrid + SectionLabel for distributions + top performers. Active/Backtested/Retired: FilterBar + DataTable. Rankings: FilterBar + dense table. Blacklists/Demotions: flat tables.
- **Analytics** (10+ tabs, 30+ nested PanelHeaders): Performance: CIO metrics, P&L breakdown, streaks, execution, pipeline health, trade quality. Attribution: strategy contribution table + chart. Trades: metric grid + distribution charts. Regime: current regimes, macro context, crypto cycle, carry rates. Alpha Edge: filter stats, conviction distribution, template performance, cost savings. Trade Journal: filters + table + MAE/MFE + patterns + recommendations.
- **Settings** (9 tabs, 71 Card/CardHeader usages): All Card wrappers removed, replaced with flat SectionLabel sections. All form fields, switches, inputs, validation preserved.
- **Orders**: Removed "Order Book" PanelHeader wrapper — timeline + tabs start immediately.
- **WatchlistPage**: Card wrappers → flat bordered divs + SectionLabel.
- **PositionDetailView**: Card wrappers → flat bordered divs + SectionLabel.
- **Analytics sub-tabs** (4 files): RollingStatisticsTab, TCATab, TearSheetTab, PerformanceAttributionTab all flattened.
- **Files**: All page files in `frontend/src/pages/`, all analytics sub-tab files, `TradingCyclePipeline.tsx`

#### 107. Main Panel PanelHeader Removal (QuantFury Style) ✅
- Autonomous: removed "Control & Activity" PanelHeader — tabs sit at panel top
- Risk: removed "Analysis" PanelHeader — correlation heatmap + tabs start immediately
- Orders: removed "Order Book" PanelHeader — timeline + tabs start immediately
- Side panels keep their PanelHeaders (they don't have tabs)
- Reclaims 32px per page on the main content area
- **Files**: `AutonomousNew.tsx`, `RiskNew.tsx`, `OrdersNew.tsx`

#### 108. TradingCyclePipeline Modernization ✅
- Removed Card/CardHeader/CardTitle wrappers from pipeline and cycle history
- Removed framer-motion animation from summary card
- SectionLabel for section titles, flat bordered divs for content
- Pipeline stepper circles preserved (w-9 h-9)
- **Files**: `frontend/src/components/trading/TradingCyclePipeline.tsx`

#### 109. Font Size Normalization (Partial) ✅
- PanelHeader title: `text-xs` (12px) → `text-[13px]`, color `gray-300` → `gray-200`
- SectionLabel: `text-[10px]` → `text-[11px]`, color `gray-500` → `gray-400`
- MetricGrid labels: `text-[9px]` → `text-[10px]`, values: `text-sm` → `text-[13px]`
- Autonomous page: all inline metric labels 9px→10px, section labels 10px→11px, metric values sm→13px, template names 11px→12px, threshold labels/values bumped
- **Files**: `PanelHeader.tsx`, `SectionLabel.tsx`, `MetricGrid.tsx`, `AutonomousNew.tsx`

---

## Current System State (April 12, 2026 — Updated Session 8)

- **Database:** PostgreSQL 16 on EC2, 32 tables, 780K+ rows
- **Account:** eToro DEMO, balance ~$162K, equity ~$463K
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto)
- **Active strategies:** ~97 DEMO + backtested
- **Open positions:** ~127
- **Monitoring:** 24/7 + CloudWatch alerting + EXIT signal processing
- **Market regime:** Equity: ranging_low_vol
- **UI:** Phase 2 QuantFury layout complete + Phase 2.5 tab interior redesign complete. All 11 pages flattened. Zero Card/CardHeader usage in any page file. New utility components: SectionLabel, MetricGrid, FilterBar. Consistent flat design across all tabs.

---

## Open Items for Next Session (Session 9)

### Priority 1: Font Size & Typography Audit (CRITICAL)
The font normalization from Session 8 was partial — many inconsistencies remain:
- **Too small**: Some data values, numbers, and text are too small to read comfortably (especially in side panels and metric grids)
- **Too large**: Some elements are oversized and don't match the platform aesthetic (e.g. PanelHeader titles like "Metrics", "Activity", "Equity Curve" on Overview page — see screenshot)
- **Inconsistent**: Font sizes vary between pages and even between tabs on the same page
- **Action needed**: Full frontend-wide typography audit. Establish a definitive font scale and apply it consistently:
  - Define the scale: what size for panel titles, section labels, metric labels, metric values, table headers, table cells, badges, buttons, form labels, descriptions
  - Audit every page against the scale
  - Fix all deviations
  - Reference: QuantFury uses clean, consistent sizing — no element feels out of place

### Priority 2: Tab Presentation Consistency
- **Autonomous page**: Tabs sit correctly at the top of the panel with no duplicate title — this is the reference pattern
- **Portfolio page**: Still has "Positions" title above the tabs — unnecessary, should be removed like Autonomous
- **Other pages**: Need to verify all pages follow the Autonomous pattern (tabs at top, no duplicate panel title)
- **Action needed**: Audit all pages with tabs in the main panel, remove any remaining PanelHeader wrappers or duplicate titles

### Priority 3: PanelHeader Title Font Mismatch
- The side panel PanelHeader titles ("Metrics", "Activity", "Equity Curve", "Cycle Intelligence", "Intelligence", "Risk Summary", etc.) use a font style that doesn't match the rest of the platform
- They look like they belong to a different design system — too bold, wrong weight, wrong color
- **Action needed**: Update PanelHeader title styling to match the QuantFury aesthetic — lighter weight, consistent with tab text

### Priority 4: Lazy Loading Flash
- Some pages briefly show the old layout/fonts before the new styles load
- This creates a jarring flash of unstyled content
- **Action needed**: Investigate and fix — likely related to CSS loading order or component lazy loading

### From Previous Sessions (Lower Priority)
- `/strategies/blacklisted-combos` returns 422 — endpoint may need `mode` query parameter
- `/strategies/template-rankings` returns 404 — endpoint may not be deployed
- `/strategies/idle-demotions` returns 422 — same mode parameter issue
- "Never synced" shows in MetricsBar — should show actual last sync time after first sync
- Phase 3 (TradingView charts, real-time streaming, workspace presets) — ready to start after polish is complete

---

## Key Files Modified in Session 8

### New Components
- `frontend/src/components/ui/SectionLabel.tsx` — flat section label
- `frontend/src/components/ui/MetricGrid.tsx` — dense metric grid
- `frontend/src/components/ui/FilterBar.tsx` — inline filter bar

### Modified Components
- `frontend/src/components/layout/PanelHeader.tsx` — title font 13px gray-200
- `frontend/src/components/ui/DataFreshnessIndicator.tsx` — compact dot + relative time
- `frontend/src/components/ui/tabs.tsx` — 13px font-semibold
- `frontend/src/components/pdf/TearSheetGenerator.tsx` — icon-only button
- `frontend/src/components/PageTemplate.tsx` — compact mode = 0px header
- `frontend/src/components/charts/EquityCurveChart.tsx` — height prop supports string
- `frontend/src/components/charts/InteractiveChart.tsx` — height prop supports string
- `frontend/src/components/trading/TradingCyclePipeline.tsx` — flat design, no Card wrappers

### Modified Pages (ALL)
- `frontend/src/pages/OverviewNew.tsx`
- `frontend/src/pages/PortfolioNew.tsx`
- `frontend/src/pages/OrdersNew.tsx`
- `frontend/src/pages/StrategiesNew.tsx`
- `frontend/src/pages/AutonomousNew.tsx`
- `frontend/src/pages/RiskNew.tsx`
- `frontend/src/pages/AnalyticsNew.tsx`
- `frontend/src/pages/DataManagementNew.tsx`
- `frontend/src/pages/SystemHealthPage.tsx`
- `frontend/src/pages/SettingsNew.tsx`
- `frontend/src/pages/AuditLogPage.tsx`
- `frontend/src/pages/WatchlistPage.tsx`
- `frontend/src/pages/PositionDetailView.tsx`
- `frontend/src/pages/analytics/RollingStatisticsTab.tsx`
- `frontend/src/pages/analytics/TCATab.tsx`
- `frontend/src/pages/analytics/TearSheetTab.tsx`
- `frontend/src/pages/analytics/PerformanceAttributionTab.tsx`


### Session Improvements (April 12, 2026 — Session 9: Typography Audit, Phase 3 Charting, UI Polish)

#### 110. Font Size & Typography Audit ✅
- **Full frontend-wide pass** establishing consistent font scale:
  - Minimum readable size: `text-xs` (12px) — no more `text-[9px]`, `text-[10px]`, or `text-[11px]` anywhere
  - MetricGrid labels: 12px, values: `text-base` (16px)
  - CompactMetricRow labels: 12px, values: `text-sm` (14px)
  - PanelHeader titles: 13px, font-medium, gray-400
  - SectionLabel: 12px (text-xs), font-medium, gray-500
  - Tab buttons: `text-[13px]` with `px-3` padding
  - Table cells (DenseTable): `text-xs` (12px) matching DSL Templates reference
  - MetricsBar labels: 12px, PositionTickerStrip: 12px
  - Side panel key-value labels: 12px, values: `text-sm` (14px)
- Removed all uppercase from PanelHeader titles, SectionLabels, and inline section labels — didn't match platform aesthetic
- **Files**: All page components, all shared UI components

#### 111. Tab Presentation Standardization ✅
- All 6 tabbed pages now use identical Strategies-style custom button tabs:
  - 32px header bar, `text-[13px]` font, `bg-gray-700/60` active state, rounded corners
  - Portfolio: converted from green underline tabs
  - Autonomous: converted from Radix TabsList/TabsTrigger
  - Risk: converted from Radix tabs, moved tabs ABOVE correlation heatmap
  - Orders: converted from Radix tabs, tabs in 32px header above timeline
  - Analytics: converted from Radix TabsList with icons to plain text buttons
- Removed duplicate titles: "Positions" from Portfolio, "Strategies" from Strategies main panels
- **Files**: `PortfolioNew.tsx`, `StrategiesNew.tsx`, `AutonomousNew.tsx`, `RiskNew.tsx`, `OrdersNew.tsx`, `AnalyticsNew.tsx`

#### 112. Table Format Standardization ✅
- DataTable base font changed from `text-sm` (14px) to `text-xs` (12px) matching DSL Templates
- DenseTable variant: `px-3 py-2` cells, `px-3 py-2` headers, `text-xs` — matches DSL Templates exactly
- Active/Backtested/Retired strategy tables now match DSL Templates format
- **Files**: `frontend/src/components/trading/DataTable.tsx`, `frontend/src/components/ui/Table.tsx`

#### 113. Portfolio Invested Amount Bug Fix ✅ (CRITICAL)
- **Problem**: BTC showing $176M, ETH showing $5.2M invested — was multiplying eToro dollar-quantity by unit price
- **Root cause**: `PositionResponse` Pydantic model was missing `invested_amount` field — DB had it, ORM serialized it, but API response stripped it
- **Fix**: Added `invested_amount` and `pending_closure` to `PositionResponse` model
- Frontend: `getInvested()` helper prefers `invested_amount`, falls back to `quantity * entry_price`
- Applied to: Invested column, %Port column, pie chart, sector exposure, closed positions, confirm dialog
- **Files**: `src/api/routers/account.py`, `frontend/src/pages/PortfolioNew.tsx`

#### 114. Orders Side Panel Overlap Fix ✅
- Status Breakdown was overlapping Recent Fills in the Orders side panel
- Removed `flex-1` from Recent Fills, made parent scrollable
- **Files**: `frontend/src/pages/OrdersNew.tsx`

#### 115. Phase 3: TradingView Lightweight Charts Migration ✅
- **Installed** `lightweight-charts` v5.1.0
- **TvChart wrapper** (`frontend/src/components/charts/TvChart.tsx`): reusable component supporting area, line, candlestick, histogram, baseline series. AlphaCent dark theme, auto-resize via ResizeObserver, crosshair, zoom/pan.
- **TvPeriodSelector** (`frontend/src/components/charts/TvPeriodSelector.tsx`): period buttons for TvChart
- **EquityCurveChart migrated**: portfolio as blue area, SPY as gray dashed line, alpha baseline (green/red), drawdown sub-chart, legend showing what each line represents
- **AssetPlot migrated**: line series with buy/sell order markers (green ↑ / red ↓)
- **UnderwaterPlot migrated**: red area series via TvChart
- **OrderFlowTimeline**: rewritten as custom inline SVG (not a standard time-series)
- **Strategy sparklines**: inline SVG polyline (60x24px)
- **All inline time-series charts** across Analytics, Risk, Orders, TCA, PerformanceAttribution migrated to TvChart
- **Non-time-series charts** replaced with custom SVG components:
  - `SVGBarChart.tsx` — vertical + horizontal bar charts
  - `SVGPieChart.tsx` — pie/donut charts with arc paths
  - `SVGStackedBarChart.tsx` — stacked bar charts
  - `ReturnDistribution.tsx` — histogram with normal curve overlay (custom SVG)
- **InteractiveChart.tsx** rewritten as pure SVG (no Recharts)
- **chart-utils.ts** extracted: `filterDataByPeriod`, `periodStartDate` utilities
- **Recharts fully removed** from `package.json` — zero imports remaining
- **TradingView watermark removed** via `attributionLogo: false`
- **Files**: All chart components, all page files, `package.json`

#### 116. Phase 3: Real-Time Price Streaming ✅
- **Backend**: Monitoring service broadcasts price ticks via WebSocket after `_quick_price_update` (every 10min) and position sync (every 60s)
- Added `_sync_broadcast_market_data()` helper for fire-and-forget async broadcasting from sync context
- **Frontend**: PositionDetailView subscribes to `market_data` WebSocket events for viewed symbol, appends live ticks to AssetPlot chart
- Live/Paused indicator badge on price chart (green pulsing "Live" when WS connected, gray "Paused" when disconnected)
- **Files**: `src/core/monitoring_service.py`, `src/core/order_monitor.py`, `frontend/src/pages/PositionDetailView.tsx`

#### 117. Phase 3: Workspace Presets ✅
- **workspace-presets.ts**: manages saving/loading/switching presets in localStorage
  - Snapshots: `react-resizable-panels` layout sizes, `PanelHeader` collapsed states, `BottomWidgetZone` widget visibility
  - 3 default presets: Trading (chart-dominant, Top Movers + Recent Signals), Monitoring (Strategy Alerts + Market Regime), Analysis (Macro Pulse + Market Regime)
  - Up to 5 user presets, stored under `alphacent_workspace_presets`
- **WorkspaceSwitcher** dropdown in TopNavBar: current preset name, grouped defaults + user presets, save/delete/reset
- Switching presets applies snapshot and reloads page
- **Files**: `frontend/src/lib/workspace-presets.ts`, `frontend/src/components/TopNavBar.tsx`

#### 118. UI Polish Fixes ✅
- **Chart overflow**: TvChart containers get `overflow: hidden`, fixed height constraints in side panels
- **SVG chart stretching**: Changed `preserveAspectRatio` to `"none"` for data charts — grid lines now align edge-to-edge
- **Side panel spacing**: Reduced `gap-2 p-2` to `gap-1 p-1.5` across all side panels, PanelHeader padding reduced to `px-2 py-1`
- **Analytics Performance tab**: Reduced spacing from `space-y-3` to `space-y-2`
- **Analytics page flash**: Added `compact={true}` to loading/error states — no more old layout flash
- **Equity curve legend**: Added legend showing Portfolio (blue), SPY (gray dashed), Drawdown (red)
- **Files**: All page components, chart components, PanelHeader

---

## Current System State (April 12, 2026 — Updated Session 9)

- **Database:** PostgreSQL 16 on EC2, 32 tables, 780K+ rows
- **Account:** eToro DEMO, balance ~$162K, equity ~$463K
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto)
- **Active strategies:** ~97 DEMO + backtested
- **Open positions:** ~127
- **Monitoring:** 24/7 + CloudWatch alerting + EXIT signal processing + WebSocket price streaming
- **Market regime:** Equity: ranging_low_vol
- **UI:** Phase 3 complete — TradingView Lightweight Charts (Recharts removed), real-time price streaming, workspace presets, full typography audit, standardized tabs and tables
- **Charting:** lightweight-charts v5.1.0 for all time-series, custom SVG for bar/pie/histogram
- **Bundle:** Recharts chunk (417KB gzipped) eliminated

---

## New Dependencies (Session 9)
- `lightweight-charts` ^5.1.0 — TradingView charting library (~50KB)
- Removed: `recharts`, `@types/recharts`

## New Files (Session 9)
- `frontend/src/components/charts/TvChart.tsx` — TradingView wrapper
- `frontend/src/components/charts/TvPeriodSelector.tsx` — Period selector for TvChart
- `frontend/src/components/charts/SVGBarChart.tsx` — Custom SVG bar chart
- `frontend/src/components/charts/SVGPieChart.tsx` — Custom SVG pie/donut chart
- `frontend/src/components/charts/SVGStackedBarChart.tsx` — Custom SVG stacked bar chart
- `frontend/src/lib/chart-utils.ts` — Chart utility functions (filterDataByPeriod, periodStartDate)
- `frontend/src/lib/workspace-presets.ts` — Workspace preset management

## Modified Backend Files (Session 9)
- `src/api/routers/account.py` — Added `invested_amount`, `pending_closure` to PositionResponse
- `src/core/monitoring_service.py` — WebSocket price tick broadcasting
- `src/core/order_monitor.py` — WebSocket price tick broadcasting on position sync

---

## Open Items (Updated Session 9)

### UI/UX — Remaining Polish
- Some charts may still overlap in narrow viewports — monitor at different screen sizes
- Analytics Trade Analytics tab: Win/Loss Distribution and Holding Periods charts may need height tuning
- Bottom widget zone widgets could use more data density
- Settings page still has old-style form layout

### Performance Monitoring
- Monitor win rate impact of wider SL/TP and EXIT signal processing (target: >45%)
- Track EXIT signal vs SL/TP vs trailing stop close ratios
- Monitor multi-strategy confluence correlation
- Check $2K minimum rejection frequency

### Infrastructure
- Consider t3.small downgrade — waiting on CloudWatch memory data
- FMP API rate limit (300/min) — monitor with corrected per-call counting
- Deploy workflow: SCP'ing `autonomous_trading.yaml` overwrites API keys — need automated Secrets Manager patch

### From Previous Sessions
- Risk controls — Portfolio-level VaR check before new positions (still open)
- `/strategies/blacklisted-combos` returns 422 — endpoint may need `mode` query parameter
- `/strategies/template-rankings` returns 404 — endpoint may not be deployed
- `/strategies/idle-demotions` returns 422 — same mode parameter issue

---

## Session Improvements (April 13-15, 2026 — Session 10: Trading System Audit & Bug Fixes)

### Critical Bug Fixes

#### 102. Trailing Stop Activation Fix ✅ (CRITICAL)
- **Bug**: Config `activation_pct: 0.12` was overriding per-asset-class thresholds (3% stocks, 6% crypto, 2% forex) because the override check `!= 0.05` always fired when config had 0.12
- **Fix**: Removed the config override entirely — per-asset-class thresholds always used
- **Impact**: 7 positions immediately got tightened trailing stops (SLV, MRVL, QQQ, VTI, XLY, IWM, NSDQ100)
- **Files**: `src/execution/position_manager.py`, `config/autonomous_trading.yaml`

#### 103. Phantom Position Prevention ✅ (CRITICAL)
- **Bug**: Position sync was creating SHORT positions for long-only strategies when eToro interpreted a close SELL order as opening a new SHORT. HD SHORT ($23K, -$198) was a ghost from this race condition.
- **Fix 1**: Position sync now validates new positions against strategy direction — rejects positions where side contradicts strategy's `direction` field
- **Fix 2**: Close orders are now excluded from the order-matching logic (skip `order_action='close'` when matching new positions to strategies)
- **Fix 3**: Exit signal handler no longer creates a duplicate close order record — only sets `pending_closure=True`, letting `_process_pending_closures` handle the actual API call and order tracking
- **DB cleanup**: Closed phantom HD SHORT; reassigned 19 mismatched positions to `etoro_position`
- **Files**: `src/core/order_monitor.py`, `src/core/trading_scheduler.py`

#### 104. Partial Exit API Fix ✅ (CRITICAL)
- **Bug**: Partial exits called `place_order()` (market-open-orders endpoint) with opposite side, which opens a NEW position on eToro instead of reducing the existing one
- **Fix**: Added `partial_close_position()` to EToroAPIClient using `market-close-orders` endpoint with `Amount` parameter; partial exit code now uses this
- **Files**: `src/api/etoro_client.py`, `src/core/monitoring_service.py`

#### 105. Position Sizing Fix ✅ (CRITICAL)
- **Bug 1**: Strategy allocation used `cash_balance * allocation_pct` — with $81K cash and $461K equity, strategies got $400 allocations producing $95-170 position sizes that all failed the $2K minimum
- **Fix**: Strategy allocation now uses `equity * allocation_pct` (correct target sizing); hard cap uses `account.balance` (actual cash) and `account.margin_used` (actual eToro margin)
- **Bug 2**: `available_capital = equity - DB_exposure` was out of sync with eToro's actual margin ($377K DB vs $459K eToro), causing the system to think it had $85K available when it had $0.01
- **Files**: `src/risk/risk_manager.py`

#### 106. ATR Floor Fix for Commodities/Forex/Indices ✅
- **Bug**: ATR floor at order execution used `yf.download(symbol)` which silently fails for OIL, GOLD, SILVER, COPPER, ZINC, forex pairs — their eToro symbols don't match Yahoo Finance tickers
- **Impact**: OIL had 8.9% ATR but positions were placed with 3.1% SL — all 3 OIL longs on Apr 13 stopped out within hours
- **Fix**: Now uses MarketDataManager (handles symbol mapping across all data sources); added 12% SL clamp for extremely volatile instruments
- **Files**: `src/execution/order_executor.py`

#### 107. Etoro Closed Mislabeling Fix ✅
- **Bug**: When eToro executes a SL, the position disappears. By the time we detect it and fetch the live price, the market has bounced back — so we mislabeled SL hits as "Etoro Closed"
- **Fix**: Three-layer detection: (1) live price past SL/TP, (2) loss ≥ 50% of SL distance → SL hit, (3) gain ≥ 50% of TP distance → TP hit. Also fetches live price at detection time for accurate P&L
- **Retroactive fix**: 14 positions relabeled from "Etoro Closed" to "Stop Loss Hit", 1 to "Take Profit Hit"
- **Files**: `src/core/order_monitor.py`

#### 108. Mass Closure Safety Guard ✅
- **Fix**: If >20% of positions disappear from eToro in a single sync cycle, skip the closure check entirely (possible DEMO reset or API glitch). Miss counters not incremented during mass events.
- **Files**: `src/core/order_monitor.py`

#### 109. Orders Page WebSocket Crash Fix ✅
- **Bug**: `order_update` WebSocket messages with undefined `status` or `symbol` caused `Cannot read properties of undefined (reading 'toLowerCase')` crash
- **Fix**: Null-safe fallbacks on toast notification and search filter
- **Files**: `frontend/src/pages/OrdersNew.tsx`

#### 110. API Keys Fix ✅
- **Bug**: SCP-based deploys overwrite `autonomous_trading.yaml`, losing Secrets Manager patches. FRED key was missing (causing `Bad Request` errors). FMP and Alpha Vantage had the FRED key patched into all three slots.
- **Fix**: Patched all three keys correctly on EC2 (FMP: `uisdNGDM...`, AV: `GF5H4ZM8...`, FRED: `d6a8d937...`)
- **Note**: Any SCP of `autonomous_trading.yaml` requires re-patching keys from Secrets Manager

---

### Performance Analysis (April 2026)

#### What the data shows
- **156 closed trades in April**: 70 winners (45%), 86 losers (55%), net **+$2,078**
- **LONGs**: 59 wins / 50 losses, net **+$4,210** ✅
- **SHORTs**: 17 wins / 39 losses, net **-$1,397** ❌ — fighting a recovering market
- **SPY performance Apr 1-15**: +5.4% ($654 → $690) — clear recovery rally
- **Losers hit SL in median 33h** vs winners held median 121h — classic "cut winners short, let losers run" anti-pattern from tight SLs

#### Root causes identified
1. **Shorts fighting the trend**: 39 SHORT losers in a 5.4% rally. Shorting individual stocks in a rising market is a losing game.
2. **ATR floor broken for commodities** (fixed in #106): OIL, SILVER, NATGAS all stopped out on normal intraday noise
3. **Trailing stops not activating** (fixed in #102): 12% threshold meant no trailing stops on 3-8% winners
4. **Position sizing too small** (fixed in #105): Most signals were generating $95-170 sizes, all rejected

#### Open trading improvements
- **Market regime gate for shorts**: In `trending_up` or `trending_up_weak` regime, suppress equity SHORT signals — only short when market is clearly trending down
- **ATR-based dynamic SL**: Per-position SL based on current ATR rather than fixed percentage
- **Short suppression**: `min_short_pct` should be 0% in trending_up regimes (currently 15%)

---

## Current System State (April 15, 2026)

- **Database:** PostgreSQL 16 on EC2, 32 tables, 780K+ rows
- **Account:** eToro DEMO, balance ~$0 (fully deployed), equity ~$462K
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto)
- **Active strategies:** ~98 DEMO
- **Open positions:** 203 across 118 symbols (DB matches eToro exactly ✅)
- **Market regime:** Equity: trending_up_weak (changed Apr 15), Crypto: trending_up
- **Monitoring:** 24/7 + CloudWatch + EXIT signals + WebSocket streaming
- **API keys:** FMP, Alpha Vantage, FRED all correctly patched on EC2
- **Key fixes deployed:** Trailing stops, phantom positions, partial exits, position sizing, ATR floor, Etoro Closed labeling

---

## Open Items (Updated Session 10)

### Trading Strategy (HIGH PRIORITY)
- **Short suppression in uptrend**: Add regime gate — no new equity SHORTs when SPY > 20-day SMA or regime is trending_up/trending_up_weak
- **ATR-based dynamic SL**: Replace fixed % SL with ATR-based floor per position at entry time
- **Performance feedback**: Monitor win rate after all fixes (target: >50% from current 45%)
- **Unconfirmed closure handling**: Implement "pending confirmation" state for positions that disappear — don't immediately book P&L, wait N hours before finalizing

### Infrastructure
- **API key patching**: SCP of `autonomous_trading.yaml` overwrites keys — need a post-SCP hook or separate key file
- Consider t3.small downgrade — waiting on CloudWatch memory data
- FMP API rate limit (300/min) — monitor

### From Previous Sessions
- Risk controls — Portfolio-level VaR check before new positions
- `/strategies/blacklisted-combos`, `/strategies/template-rankings`, `/strategies/idle-demotions` — 422/404 errors


---

### Session Improvements (April 17, 2026 — Session 11: Quant Trading Audit + System Fixes)

#### 111. Quant Trading Improvements (from April 1-17 trade review) ✅
- **Trailing stops**: Activation thresholds widened (stocks 3%→5%, crypto 6%→8%). ATR-based minimum trail distance added: `max(distance_pct * price, 1.5x daily ATR)` — eliminates penny-stop whipsaws
- **ATR floor at order time**: Raised from 2x to 2.5x ATR. Min R:R raised from 1.5 to 2.0
- **Bull market short closure**: `_close_shorts_in_bull_market()` runs every ~30s — flags all open equity shorts for closure when regime is `trending_up*`
- **Fundamental exits**: Sector rotation exits now require 3-day regime stability + position must be profitable. Earnings miss exits only fire if profitable OR SL >50% consumed
- **Strategy retirement**: Requires minimum 5 closed trades before health evaluation. Intraday losers cut at 50% of hold limit (requires ≥1% loss to trigger)
- **Regime gate**: Short concentration limit (max 3 equity shorts in non-bearish regimes). Exit signal confidence guard (0.40 threshold on losing positions). Trending_up long sizing 1.25x
- **Config**: `trending_up*` directional quotas `min_short_pct: 0.0`, adaptive_risk ATR multiplier 1.5→2.5
- **Files**: `src/execution/position_manager.py`, `src/execution/order_executor.py`, `src/core/monitoring_service.py`, `src/core/trading_scheduler.py`, `config/autonomous_trading.yaml`

#### 112. Strategy Retirement → BACKTESTED with TTL ✅ (CRITICAL)
- Active strategies (health=0 or decay=0) now demote to BACKTESTED (activation_approved=False, 14d TTL) instead of setting RETIRED status
- `pending_retirement` finalizer demotes to BACKTESTED instead of RETIRED
- RETIRED status is now terminal — deleted immediately at cycle start (no 14d wait)
- Demoted strategies re-run walk-forward in next cycle; if they pass, they reactivate
- **Files**: `src/core/monitoring_service.py`, `src/strategy/autonomous_strategy_manager.py`

#### 113. Strategy Identity Overhaul ✅
- **Meaningful names**: `SMA Trend Momentum TQQQ LONG RSI(14/75)` instead of `SMA Trend Momentum Multi V38`
- **Watchlist dedup**: `_build_watchlists` now excludes symbols already covered by another active strategy of the same template
- **Supersession**: When a better-calibrated proposal (>15% Sharpe improvement) is found for same template×symbol, old strategy gets `superseded=True` (stops new signals, open position runs to close), new strategy activates immediately
- **Signal generation**: Superseded strategies excluded from signal loop
- **UI**: Superseded/Retiring/Re-eval badges on strategy name cell with tooltip
- **Files**: `src/strategy/strategy_proposer.py`, `src/strategy/autonomous_strategy_manager.py`, `src/core/trading_scheduler.py`, `frontend/src/pages/StrategiesNew.tsx`

#### 114. FMP Cache Warmer Fixes ✅
- **Token bucket rate limiter**: Added to `RateLimiter` class — enforces 5 calls/sec (300/min) across all workers. `wait_for_token()` blocks workers until slot available instead of dropping calls. 8 workers now fully utilize 300/min without 429s
- **FMP cache trigger button**: Added to Data Management page with live coverage % bar, progress counter, elapsed time
- **FMP cache warmer**: Uses dedicated `FundamentalDataProvider` instance (not singleton) so it has its own rate limiter and doesn't compete with signal generation
- **Force TTL**: Manual trigger uses 24h TTL (re-fetches anything older than 24h) instead of 7-day default
- **Files**: `src/data/fundamental_data_provider.py`, `src/data/fmp_cache_warmer.py`, `src/api/routers/data_management.py`, `frontend/src/pages/DataManagementNew.tsx`

#### 115. FundamentalDataProvider Singleton ✅ (CRITICAL)
- **Root cause**: 10+ call sites each created their own `FundamentalDataProvider` instance. Each had its own in-memory earnings_calendar_cache (empty on creation) and its own RateLimiter (each thinking it had 300 calls). Combined they were making 10x the API calls.
- **Fix**: Module-level `_singleton_instance` + `_singleton_lock`. `__init__` auto-registers as singleton on first creation. `get_fundamental_data_provider()` returns singleton.
- **`get_earnings_calendar`**: Now checks memory cache first (was bypassing it). Fixed double-counting bug (old code called `can_make_call()` + `record_call()` separately alongside `_fmp_request()` which uses `wait_for_token()`).
- **All 10 instantiation sites patched**: `strategy_engine.py`, `strategy_proposer.py`, `fundamental_ranker.py`, `fmp_cache_warmer.py`, `account.py`, `config.py`, `database.py`
- **Result**: 0 "FMP unavailable for earnings calendar" warnings (was flooding every cycle)
- **Files**: `src/data/fundamental_data_provider.py`, `src/strategy/strategy_engine.py`, `src/strategy/strategy_proposer.py`, `src/strategy/fundamental_ranker.py`, `src/data/fmp_cache_warmer.py`, `src/api/routers/account.py`, `src/api/routers/config.py`, `src/models/database.py`

#### 116. ZNC=F / DAILY_ONLY_SYMBOLS ✅
- ZINC, ALUMINUM, PLATINUM added to `DAILY_ONLY_SYMBOLS` set in `symbol_mapper.py`
- Monitoring service hourly batch download now skips these symbols (CME futures have no reliable 1h data on Yahoo Finance)
- **Files**: `src/utils/symbol_mapper.py`, `src/core/monitoring_service.py`

#### 117. Session / Auth Fixes ✅
- Session TTL extended from 30min to 8h — backend restarts no longer log users out
- Cookie `max_age` extended to match (8h)
- SQL GROUP BY error fixed in data quality endpoint (`source` column removed from query)
- **Files**: `src/core/auth.py`, `src/api/routers/auth.py`, `src/api/routers/data_management.py`

#### 118. Orders Page Layout ✅
- Orders table moved above OrderFlowTimeline (table is primary, chart is secondary)
- TvChart fill rate trend fixed to use Unix timestamps (was using string labels)
- **Files**: `frontend/src/pages/OrdersNew.tsx`

#### 119. FMP Cache Warmer — Autonomous Cycle ✅
- Coverage check before skipping: if cache coverage <80%, warm even if timestamp is recent (handles partial warm from rate limit interruption)
- Partial timestamp saved every 20 symbols so interrupted runs don't restart from scratch
- **Files**: `src/strategy/autonomous_strategy_manager.py`

---

### Session Improvements (April 17, 2026 — Session 12: FMP Cache & Data Fetching Overhaul)

#### 120. FundamentalDataProvider Singleton Race Condition Fix ✅ (CRITICAL)
- **Root cause**: `__init__` self-registration was racy — 4 parallel signal gen workers all called `FundamentalDataProvider(config)` simultaneously. Python creates all 4 objects before any `__init__` runs, so all 4 passed the `if _singleton_instance is None` check and each got their own `RateLimiter` with 300/min budget. Effective rate = 1200 calls/min against FMP → service crashing every ~10 minutes.
- **Fix**: Removed self-registration from `__init__`. `get_fundamental_data_provider()` now atomically creates + assigns singleton inside the lock before returning.
- `monitoring_service._get_fundamental_provider()` was also creating a fresh instance on every call — now uses `get_fundamental_data_provider()`.
- **Files**: `src/data/fundamental_data_provider.py`, `src/core/monitoring_service.py`

#### 121. FMP Insider Trading Endpoint Disabled ✅
- `/api/v4/insider-trading` is a legacy endpoint (deprecated Aug 2025), 403 for all non-legacy accounts
- Stable API (`/stable/search-insider-trades`, `/stable/latest-insider-trade` etc.) returns 404 — plan-gated (returns `[]` + 404 for free tier)
- `get_insider_trading()` now returns `[]` immediately — no rate limit tokens wasted
- Dead code removed from method body
- **Files**: `src/data/fundamental_data_provider.py`

#### 122. FMP Cache Warm Rate Exhaustion Fix ✅
- **Root cause**: 8 concurrent workers × 5 calls/symbol = 40 calls/burst. Exhausted 300/min budget after ~60 symbols, circuit breaker fired, remaining ~140 symbols failed (39 errors per run).
- **Fix**: Reduced `ThreadPoolExecutor` workers 8 → 3. Keeps burst at 15 calls max, ~60 symbols/min with headroom for concurrent signal generation.
- **Files**: `src/data/fmp_cache_warmer.py`

#### 123. `_is_data_complete` False Positives Fixed ✅
- Was requiring 2/3 of `[eps, revenue_growth, pe_ratio]` but `revenue_growth` is structurally `None` from a single-period FMP fetch (requires 2 periods to compute).
- Was causing ~30+ symbols (INTC, CRWD, ZS, NET, MDB, TEAM, SOUN, AI, etc.) to be flagged as incomplete → unnecessary Alpha Vantage fallback → stale data warnings.
- **Fix**: Now only requires `eps OR pe_ratio` (1 of 2 instead of 2 of 3).
- **Files**: `src/data/fundamental_data_provider.py`

#### 124. FMP Cache Warm TTL Aligned to Coverage Display ✅
- Manual trigger was using `force_ttl_hours=24` — re-fetching anything older than 24h even if coverage showed it as fresh (< 7 days). Running twice would re-fetch the same symbols.
- **Fix**: Changed to `force_ttl_hours=168` (7 days) — matches the coverage % display. Re-running 2-3 times now progressively fills only the symbols that failed, without re-fetching symbols successfully cached this week.
- **Files**: `src/api/routers/data_management.py`

#### 125. MarketDataManager Singleton ✅
- 15+ places were creating fresh `MarketDataManager` instances with empty `_raw_fetch_cache` and `_historical_memory_cache`. Signal gen workers each had their own empty cache — zero sharing between strategies.
- **Fix**: Added `get_market_data_manager()` / `set_market_data_manager()` singleton pattern. Monitoring service registers its instance on startup. Trading scheduler uses the shared instance instead of creating a new one.
- **Files**: `src/data/market_data_manager.py`, `src/core/monitoring_service.py`, `src/core/trading_scheduler.py`

#### 126. Intraday DB Cache Staleness False Positives Fixed ✅
- `_get_historical_from_db` was rejecting 1h/4h data if the latest bar was > 2h old — triggering 208 individual Yahoo calls on every restart just because it was morning (overnight gap).
- **Fix**: Only reject intraday DB cache if the market was actually open during the gap. Checks US/Eastern timezone: if it's pre-market, after-hours, or weekend → gap is expected → use DB data as-is. Crypto (24/7) still uses the 2h staleness check.
- **Files**: `src/data/market_data_manager.py`

#### 127. Double Yahoo Calls in `_sync_price_data` Eliminated ✅
- Phase 1 of the hourly sync was calling `get_historical_data()` (which has Yahoo fallback) to check DB cache. Symbols missing DB cache got fetched individually in Phase 1, then again in the batch in Phase 2 → double Yahoo call per symbol.
- **Fix**: Phase 1 now calls `_get_historical_from_db()` directly. If DB misses, just adds to batch list. All Yahoo fetches happen in Phase 2 as a single `yf.download()` batch call.
- **Files**: `src/core/monitoring_service.py`

---

### Session Improvements (April 17, 2026 — Session 13: Data Page + Sentiment-Aware Short Gate)

#### 128. Data Management Page — Fundamentals + News Columns ✅
- Data quality table: replaced Score+Staleness with **Price** (quality score), **Fundamentals** (FMP score + age), **News** (sentiment -1 to +1 with bullish/bearish/neutral color)
- FMP Fundamentals column: shows score 0-100 (decays over 30 days), age in days, "n/a" for ETFs/crypto/forex, "missing" if no data
- News column: shows sentiment score with color (green=bullish, red=bearish, gray=neutral) + age in hours
- BTC/ETH score=0 fix: quality reports stored as BTCUSD/ETHUSD but asset_class_map uses BTC/ETH — now tries both forms; also fixed quality_score=0 from empty-data reports (use staleness fallback instead)
- **Files**: `frontend/src/pages/DataManagementNew.tsx`, `src/api/routers/data_management.py`

#### 129. Data Source Health — Marketaux Added ✅
- Data Source Health grid now shows 5 cards: eToro, Yahoo, FMP, FRED, **Marketaux**
- Marketaux card shows: status (healthy/degraded/rate_limited), coverage %, requests remaining
- Status derived from `newsSentimentStatus.requests_remaining`: >10 = healthy, >0 = degraded, 0 = rate_limited
- **Files**: `frontend/src/pages/DataManagementNew.tsx`

#### 130. News Sentiment Cache Panel ✅
- New "News Sentiment (Marketaux)" section in Data Health side panel
- Coverage bar (same pattern as FMP Fundamental Cache)
- Shows: coverage %, fresh_24h, fresh_7d, requests remaining
- "Refresh Sentiment" button (purple) triggers manual sync
- Rate limit guard: button disabled when requests_remaining < 5
- New backend endpoints: `GET /data/news-sentiment/status`, `POST /data/news-sentiment/trigger`
- **Files**: `frontend/src/pages/DataManagementNew.tsx`, `src/api/routers/data_management.py`

#### 131. Sentiment-Aware Short Gate ✅ (CRITICAL — Alpha Generation)
- **Problem**: Regime gate was blocking ALL equity shorts in non-bearish markets, even when a specific symbol had strongly bearish news (earnings miss, scandal, guidance cut)
- **Fix**: Added sentiment override — if `news_sentiment_score < -0.5` (strongly bearish), the regime gate is bypassed and the short is allowed
- **Rationale**: Market regime is a macro signal; individual stock news is a micro signal. A stock with -0.9 sentiment in a rising market is a legitimate short — it's decoupling from the market. This is exactly how quants use news sentiment: to identify idiosyncratic shorts.
- **Threshold**: -0.5 (moderately bearish not enough — requires strongly bearish to override macro regime)
- **Log**: "Regime gate override: allowing {sym} SHORT despite {regime} — news sentiment={score} (strongly bearish)"
- **Files**: `src/core/trading_scheduler.py`

---

## Current System State (April 17, 2026 — Updated Session 13)

- **Database:** PostgreSQL 16 on EC2, 33 tables (added symbol_news_sentiment), 780K+ rows
- **Account:** eToro DEMO, balance ~$14K, equity ~$470K
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto)
- **Active strategies:** ~114 DEMO
- **Open positions:** ~190
- **Market regime:** Equity: trending_up_weak, Crypto: trending_up
- **News sentiment**: 40 symbols populated (DIS=-1.0, SCHW=-1.0, HD=-0.99, GOOGL=+0.45, GE=+0.43)
- **Short gate**: Regime gate now has sentiment override — strongly bearish news (< -0.5) allows shorts even in non-bearish regimes
- **Data page**: Fundamentals + News columns in quality table, Marketaux in Data Source Health, News Sentiment Cache panel

---

## Open Items (Updated Session 13)

### News Sentiment
- 40/~232 stock symbols populated (hit 100 req/day limit on first run)
- Will fill remaining ~192 symbols over next 2-3 days (100 req/day)
- Insider trading data still unavailable (FMP plan-gated) — `insider_net_buying` always 0 in conviction scorer

### Trading Performance
- Monitor win rate after all quant improvements (target: >50%)
- Monitor sentiment-aware short gate: are strongly bearish news shorts profitable?
- Track how many shorts are being closed by bull market gate vs allowed by sentiment override

### Infrastructure
- API key patching: SCP of `autonomous_trading.yaml` overwrites keys — need post-SCP hook
- Consider t3.small downgrade — waiting on CloudWatch memory data

### From Previous Sessions
- Risk controls — Portfolio-level VaR check before new positions
- `/strategies/blacklisted-combos`, `/strategies/template-rankings`, `/strategies/idle-demotions` — 422/404 errors

- **Database:** PostgreSQL 16 on EC2, 32 tables, 780K+ rows
- **Account:** eToro DEMO, balance ~$162K, equity ~$463K
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto)
- **Active strategies:** ~114 DEMO
- **Open positions:** ~185 (158 LONG, 27 SHORT)
- **Market regime:** Equity: trending_up_weak, Crypto: trending_up
- **FMP cache**: ~210 symbols fresh within 7 days (~91% coverage), 39 failures fixed
- **Data fetching**: Singleton pattern for both FundamentalDataProvider and MarketDataManager — zero redundant instances, shared caches across all components
- **Insider trading**: Disabled (FMP plan-gated) — no more 403 spam on startup
- **Intraday cache**: No longer rejected on overnight/weekend gaps — 208 Yahoo calls eliminated from every restart

---

## Open Items (Updated Session 12)

### Trading Performance
- Monitor win rate after all quant improvements (target: >50%)
- Track how many shorts are being closed by bull market gate
- Monitor supersession: are better-calibrated strategies replacing old ones?

### FMP Cache
- Run cache warm 2-3 times to fill remaining ~9% failures (rate limit recovery between runs)
- Insider trading data unavailable on current FMP plan — conviction scorer `_score_fundamental_quality()` uses `insider_net_buying` field which will always be 0

### Strategy Identity
- Existing strategies still have old names (V38, V174, etc.) — new naming only applies to newly proposed strategies

### Infrastructure
- API key patching: SCP of `autonomous_trading.yaml` overwrites keys — need post-SCP hook
- Consider t3.small downgrade — waiting on CloudWatch memory data

### From Previous Sessions
- Risk controls — Portfolio-level VaR check before new positions
- `/strategies/blacklisted-combos`, `/strategies/template-rankings`, `/strategies/idle-demotions` — 422/404 errors

---

### Session Improvements (April 17, 2026 — Session 13: News Sentiment + Data Page + Short Gate)

#### 128. Marketaux News Sentiment System ✅ (New Alpha Signal)
- **New**: `src/data/news_sentiment_provider.py` — Marketaux API client with DB-backed rolling cache
- **DB table**: `symbol_news_sentiment` (symbol, sentiment_score -1 to +1, article_count, last_article_at, fetched_at, ttl_hours)
- **TTL logic**: 6h (high news volume/earnings week), 24h (normal), 48h (weekend), 72h (quiet/no articles)
- **Change detection**: if no new articles since last fetch, extends TTL without API call
- **Returns 0.0 when no data** — never blocks a trade
- **Priority queue sync**: open positions first → active strategy symbols → stale symbols
- **100 req/day free tier**: caps at 80/run, leaves 20 buffer. Full universe in 3 days.
- **First run**: 40 symbols populated (DIS=-1.0, SCHW=-1.0, HD=-0.99, RTX=-0.96, GOOGL=+0.45, GE=+0.43)
- **Files**: `src/data/news_sentiment_provider.py`, `src/api/app.py`, `src/core/monitoring_service.py`

#### 129. Conviction Scorer — News Sentiment Component ✅
- `_score_news_sentiment()`: ±8 point adjustment, direction-aware
- LONG + bullish news → +8, LONG + bearish news → -8
- SHORT + bearish news → +8 (bad news = good short), SHORT + bullish news → -8
- Pure DB lookup at signal time — zero API calls, zero latency
- Only applies to stocks (ETFs/forex/crypto/indices/commodities return 0)
- **Files**: `src/strategy/conviction_scorer.py`

#### 130. Alpha Vantage Disabled ✅
- Free tier: 25 req/day — exhausted in minutes, returns rate-limit message for every call after the first 25
- All AV fallbacks removed from `get_fundamental_data()` and `get_earnings_calendar()`
- All 42 ETFs added to `NON_FUNDAMENTAL_SYMBOLS` (were triggering FMP→AV fallback chain)
- `enabled: false` in `config/autonomous_trading.yaml`
- **Files**: `src/data/fundamental_data_provider.py`, `config/autonomous_trading.yaml`

#### 131. Data Management Page — Fundamentals + News Columns ✅
- Data quality table: replaced Score+Staleness with **Price** (quality score), **Fundamentals** (FMP score + age in days), **News** (sentiment -1 to +1 with color)
- FMP column: score 0-100 (decays over 30 days), "n/a" for ETFs/crypto/forex, "missing" if no data
- News column: +0.45 green (bullish), -0.99 red (bearish), age in hours
- **BTC/ETH score=0 fix**: quality reports stored as BTCUSD/ETHUSD but asset_class_map uses BTC/ETH — now tries both forms; also fixed quality_score=0 from empty-data reports
- **Files**: `frontend/src/pages/DataManagementNew.tsx`, `src/api/routers/data_management.py`

#### 132. Data Source Health — Marketaux Card ✅
- Data Source Health grid: 5th card added for Marketaux
- Shows: status (healthy/degraded/rate_limited), coverage %, requests remaining today
- **Files**: `frontend/src/pages/DataManagementNew.tsx`

#### 133. News Sentiment Cache Panel ✅
- New "News Sentiment (Marketaux)" section in Data Health side panel (same pattern as FMP Fundamental Cache)
- Coverage bar, fresh_24h/7d stats, requests remaining, "Refresh Sentiment" button (purple)
- Rate limit guard: button disabled when requests_remaining < 5
- New backend endpoints: `GET /data/news-sentiment/status`, `POST /data/news-sentiment/trigger`
- **Files**: `frontend/src/pages/DataManagementNew.tsx`, `src/api/routers/data_management.py`

#### 134. Sentiment-Aware Short Gate ✅ (CRITICAL — Alpha Generation)
- **Problem**: Regime gate was blocking ALL equity shorts in non-bearish markets, even when a specific symbol had strongly bearish news (earnings miss, scandal, guidance cut)
- **Fix**: If `news_sentiment_score < -0.5` (strongly bearish), regime gate is bypassed and the short is allowed
- **Rationale**: Market regime is macro; individual stock news is micro. A stock with -0.9 sentiment in a rising market is decoupling from the market — legitimate idiosyncratic short.
- **Threshold**: -0.5 requires strongly bearish news. Mildly negative (-0.3) doesn't override macro regime.
- **Log**: "Regime gate override: allowing {sym} SHORT despite {regime} — news sentiment={score} (strongly bearish)"
- **Files**: `src/core/trading_scheduler.py`

---

## Current System State (April 17, 2026 — Updated Session 13)

- **Database:** PostgreSQL 16 on EC2, 33 tables (added `symbol_news_sentiment`), 780K+ rows
- **Account:** eToro DEMO, balance ~$14K, equity ~$470K
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto)
- **Active strategies:** ~114 DEMO
- **Open positions:** ~190
- **Market regime:** Equity: trending_up_weak, Crypto: trending_up
- **News sentiment**: 40 symbols populated (DIS=-1.0, SCHW=-1.0, HD=-0.99, GOOGL=+0.45, GE=+0.43). Full coverage in ~3 days.
- **Short gate**: Sentiment override active — strongly bearish news (< -0.5) allows shorts in non-bearish regimes
- **Data page**: Price + Fundamentals + News columns, Marketaux health card, News Sentiment Cache panel
- **Alpha Vantage**: Disabled (25 req/day useless)
- **Conviction scorer**: 6 components — WF edge (40) + signal quality (25) + regime fit (20) + asset tradability (15) + fundamental quality (±15) + news sentiment (±8) + carry bias (±5) + crypto cycle (±5)

---

## Open Items (Updated Session 13)

### News Sentiment
- 40/~232 stock symbols populated (hit 100 req/day limit on first run)
- Will fill remaining ~192 symbols over next 2-3 days (100 req/day free tier)
- Insider trading data still unavailable (FMP plan-gated) — `insider_net_buying` always 0

### Trading Performance
- Monitor win rate after all quant improvements (target: >50%)
- Monitor sentiment-aware short gate: are strongly bearish news shorts profitable?
- Track how many shorts are allowed by sentiment override vs blocked by regime gate

### Infrastructure
- API key patching: SCP of `autonomous_trading.yaml` overwrites keys — need post-SCP hook
- Consider t3.small downgrade — waiting on CloudWatch memory data

### From Previous Sessions
- Risk controls — Portfolio-level VaR check before new positions
- `/strategies/blacklisted-combos`, `/strategies/template-rankings`, `/strategies/idle-demotions` — 422/404 errors
