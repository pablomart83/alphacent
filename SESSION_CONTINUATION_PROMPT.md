# AlphaCent — Session Continuation Prompt

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
