# AlphaCent — Autonomous Trading Platform

## What Is It

AlphaCent is a fully autonomous trading system running on eToro. It generates its own strategies, validates them against historical data, executes trades, manages risk, and learns from results — all without human intervention.

Currently running on a ~$475K eToro DEMO account to prove consistent profitability across multiple market regimes before deploying real capital.

## The 30-Second Version

```
Market Data → Strategy Ideas → Backtest & Validate → Activate Winners → Trade Signals → Execute on eToro → Monitor & Manage → Learn & Repeat
```

The system covers 297 instruments: stocks, ETFs, crypto, forex, indices, and commodities.

---

## End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│              AUTONOMOUS CYCLE (scheduled or manual)                 │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌────────────┐   ┌───────────┐ │
│  │ Strategy  │──▶│  Walk-Forward │──▶│  Monte     │──▶│ Conviction│ │
│  │ Proposals │   │  Validation  │   │  Carlo     │   │  Scoring  │ │
│  └──────────┘   └──────────────┘   │  Bootstrap │   └─────┬─────┘ │
│   200 proposals   Train/test split  └────────────┘         │       │
│   185 templates   Direction-aware   1000 iterations         │       │
│   297 symbols     thresholds        p5 Sharpe ≥ 0.0         │       │
│                                                             ▼       │
│                                                    ┌────────────┐  │
│                                                    │  Activate  │  │
│                                                    │  Winners   │  │
│                                                    └────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                                             │
                                                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    SIGNAL → ORDER → POSITION                        │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌────────────┐   ┌───────────┐ │
│  │  Signal   │──▶│    Risk      │──▶│  Execute   │──▶│  Position │ │
│  │Validation │   │  Management  │   │  on eToro  │   │  Created  │ │
│  └──────────┘   └──────────────┘   └────────────┘   └───────────┘ │
│   Duplicate       Live balance       Market order     DB + eToro   │
│   filter          check (DB-fresh)   SL/TP attached   tracked      │
│   Regime gate     Vol-scaled sizing  ATR-adjusted                  │
│   VIX filter      Portfolio heat     Spread-adjusted               │
│   Yield curve     Drawdown sizing                                  │
└─────────────────────────────────────────────────────────────────────┘
                                                             │
                                                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   24/7 MONITORING SERVICE                           │
│                                                                     │
│  Every 30s:  Trailing stops + partial exits                         │
│  Every 60s:  Position sync from eToro                               │
│  Every 60s:  Process pending closures                               │
│  Every 10m:  Quick price update                                     │
│  Every 55m:  Full price sync (297 symbols)                          │
│  Daily:      Fundamental exits, time-based exits, zombie exits,     │
│              stale order cleanup, data retention, performance       │
│              feedback, decay scoring                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                                             │
                                                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FEEDBACK LOOP                                  │
│                                                                     │
│  Trade Journal ──▶ Performance Feedback ──▶ Strategy Proposer       │
│                                                                     │
│  • Winning templates get higher proposal weights                    │
│  • Losing templates get lower weights                               │
│  • Slippage analytics inform execution timing                       │
│  • Regime performance guides future activations                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Strategy Library

The system runs 185+ strategy templates across three timeframes and five strategy families, covering all market regimes for both equities and crypto.

### Strategy Families

| Family | Concept | Key Indicators | Best Regime |
|--------|---------|---------------|-------------|
| **Trend Following** | Ride sustained directional moves | EMA crossover, ADX > 25, MACD signal cross, VWAP trend | Trending up/down |
| **Mean Reversion** | Fade overextensions back to equilibrium | RSI extremes, BB band touch, Stochastic, Z-score | Ranging / sideways |
| **Breakout** | Catch the start of new moves after compression | Donchian channel, BB squeeze, volume expansion, ATR contraction | Transition / low-vol |
| **Momentum** | Buy strength, sell weakness | Price > N-bar high + volume, MACD histogram, EMA ribbon expansion | Trending (strong) |
| **Volatility** | Trade volatility expansion/contraction | ATR breakout, BB bandwidth, Keltner channel | Any (adapts) |

### Template Coverage

| Timeframe | Templates | Notes |
|-----------|-----------|-------|
| **Daily (1d)** | ~110 | All 5 families + Alpha Edge fundamental strategies |
| **4H** | ~50 | Trend, momentum, mean reversion (+ Crypto 4H MACD Trend, BB Squeeze, etc.) |
| **1H** | ~50 | Intraday momentum, EMA crossover, MACD, RSI bounce (equity + crypto intraday) |

Crypto 1H templates are regime-gated (ADX<25 for mean-reversion, ADX>15 for trend/momentum, auto-injected in StrategyTemplate.__post_init__) to avoid firing into downtrends. Crypto-specific SL/TP floors scale with timeframe: 1H uses 1.5% SL / 2% TP, 4H uses 2.5% SL / 4% TP, 1D+ uses 4% SL / 8% TP. BTC→altcoin lead-lag and cross-sectional momentum templates added 2026-05-02.

### Directional Coverage

The template library covers both directions with regime-aware filtering:

- **LONG templates** — the majority; sized up in trending_up regimes
- **SHORT templates (generic)** — ranging/trending_down regimes only (RSI Overbought Short, Moving Average Breakdown, etc.)
- **SHORT templates (uptrend-specific)** — explicitly designed for corrections within bull markets:
  - *Exhaustion Gap Short* — RSI > 75, price 5%+ above SMA(20)
  - *BB Squeeze Reversal Short* — price above BB upper(2.5σ) + RSI > 70
  - *MACD Divergence Short* — MACD crosses below signal with RSI > 65
  - *EMA Rejection Short* — failed breakout above EMA(20) in uptrend
  - *Parabolic Move Short* — price > 2×ATR above SMA + RSI > 70
  - *Volume Climax Short* — volume spike 2× average + RSI > 70
- **Market-neutral** — Pairs Trading (8 pairs, correlation-based spread)
- **Alpha Edge** — fundamental-driven, direction determined by signal type

### Alpha Edge Strategies (Fundamental)

| Strategy | Signal Source | Direction |
|----------|--------------|-----------|
| Earnings Momentum | FMP earnings surprise > 5% + revenue growth > 10% | LONG |
| Earnings Miss Short | FMP earnings miss < -5% | SHORT |
| Insider Buying | FMP net insider purchases (3+ in 90 days) | LONG |
| Dividend Aristocrat | Yield + ROE + RSI confirmation, 180d entry spacing | LONG |
| Quality Mean Reversion | ROE > 15%, D/E < 0.5, RSI < 30 | LONG |
| Quality Deterioration Short | Deteriorating fundamentals + RSI > 60 | SHORT |
| Sector Rotation | FMP sector ETF momentum rankings | LONG |
| Sector Rotation Short | Weakest sector ETF | SHORT |
| Relative Value | P/E mean reversion | LONG |
| Pairs Trading | Correlation-based spread (8 pairs) | Market-neutral |
| Analyst Revision Momentum | Consecutive upward EPS revisions | LONG |
| Share Buyback Momentum | Active buyback + RSI < 60 | LONG |
| Multi-Factor Composite | Value + quality + momentum + growth composite | LONG/SHORT |
| Accruals Quality Short | High accruals = earnings quality deterioration | SHORT |

### Market Regimes (9)

Detected independently per asset class (equity, crypto, forex, commodity):

| Regime | Directional Quota (min long / min short) |
|--------|------------------------------------------|
| trending_up_strong | 85% / 3% |
| trending_up | 80% / 5% |
| trending_up_weak | 75% / 8% |
| ranging_low_vol | 75% / 0% |
| ranging | 70% / 0% |
| trending_down_weak | 30% / 30% |
| trending_down | 20% / 50% |
| high_volatility | 30% / 10% |

The system always maintains a minimum short book — never 0% short in any regime.

---

## Key Components

### 1. Strategy Proposals

Each autonomous cycle generates up to 200 strategy candidates:

- **DSL Templates:** Technical indicator combinations. Each template defines entry/exit rules in a domain-specific language. Regime-directional filter suppresses generic shorts in uptrends but preserves uptrend-specific exhaustion shorts.
- **Alpha Edge Templates:** Fundamental-driven strategies using real FMP data. Always included regardless of regime (they self-filter via factor validation).
- **Watchlist:** Each strategy gets up to 3 symbols ranked by suitability (tiered WF thresholds: same asset class S>0.2/t≥3, adjacent S>0.3/t≥4, cross-asset S>0.5/t≥6).

**Smart proposal management:**
- **Zero-trade blacklist** — template+symbol combos producing 0 trades blocked for 7 days
- **Rejection blacklist** — combos rejected 3+ times at activation blocked for 30 days
- **WF validated cache** — passing combos cached to avoid re-running identical backtests
- **DAILY_ONLY guard** — LME metals (ZINC, ALUMINUM, NICKEL, PLATINUM) blocked from 1h/4h templates

### 2. Walk-Forward Validation

Every strategy must pass walk-forward backtesting before activation:

```
Historical Data (365d train + 180d test for daily strategies)
├── Train Period → Fit parameters
└── Test Period  → Validate out-of-sample (unseen data)
```

Direction-aware thresholds — shorts get relaxed thresholds in trending_up (they're harder to trade):

| Regime | Direction | Min Sharpe | Min Win Rate |
|--------|-----------|-----------|--------------|
| trending_up | LONG | 0.30 | 45% |
| trending_up | SHORT | 0.15 | 40% |
| trending_down | SHORT | 0.30 | 45% |
| ranging | LONG/SHORT | 0.15 | 40% |

Followed by **Monte Carlo bootstrap** (1000 iterations, p5 Sharpe ≥ 0.0) for strategies with 15+ trades — filters strategies with wide return distributions even if test Sharpe looks positive.

### 3. Conviction Scoring

Before activation, each strategy is scored 0–100:

| Component | Max Points | What It Measures |
|-----------|-----------|-----------------|
| Walk-forward edge | 40 | OOS Sharpe, win rate, return/trade |
| Signal quality | 25 | Confidence, R:R ratio, indicator count |
| Regime fit | 20 | Strategy type vs current regime (direction-aware for shorts) |
| Asset tradability | 15 | Liquidity, spread, data quality |
| Fundamental quality | ±15 | FMP fundamentals (direction-aware: short the garbage) |
| Carry bias | ±5 | Forex carry direction |
| Crypto cycle | ±5 | Halving cycle phase |
| News sentiment | ±1 | Marketaux (tiebreaker only — free tier) |
| Factor exposure | ±6 | Regime-aware factor tilt |

**Threshold: 60/100.** Uptrend-specific SHORT strategies score 20/20 on regime fit (they are the hedge, not fighting the regime).

### 4. Activation & Retirement

**Activation thresholds:**
- `min_trades_dsl`: 8 (daily), 8 (4h), 15 (1h)
- `min_trades_alpha_edge`: 8
- `min_trades_commodity`: 6
- **Sharpe exception:** test_sharpe ≥ 2.0 + ≥ 3 trades bypasses min_trades

**Retirement:** Strategies are automatically retired when live performance degrades below thresholds over a 60-day rolling window (3 consecutive failures required). Decay scorer runs daily.

**Strategy lifecycle:**
```
PROPOSED → BACKTESTED (WF passed, activation_approved=True)
    → scanning for signals every 30 min
    → signal fires → promoted to DEMO (position opened on eToro)
    → position closes → no more positions? → back to BACKTESTED (keeps scanning)
    → poor live performance over 60 days → RETIRED
```

### 5. Signal Generation & Execution

Active and approved-BACKTESTED strategies generate signals every 30 minutes. Before a signal becomes an order:

1. **Duplicate check** — no second position on same symbol/direction for same strategy
2. **Cross-cycle dedup** — blocks same template opening same symbol across multiple strategies
3. **Regime gate** — equity shorts blocked in non-bearish regimes (unless strongly bearish news sentiment)
4. **Short concentration limit** — max 3 open equity shorts in non-bearish regimes
5. **VIX panic filter** — blocks new equity LONGs when VIX > 30 and spiking > 20% above 10d avg
6. **Yield curve gate** — blocks equity LONGs when 2s10s spread < -0.25% (sustained inversion)
7. **Risk sizing** — live balance read from DB (not stale account object), vol-scaled, drawdown-adjusted
8. **Portfolio heat cap** — total open risk-dollars ≤ 8% of equity
9. **Conviction scoring** — combined score must exceed 60/100

Orders are submitted to eToro as market orders with ATR-floored, spread-adjusted stop-loss and take-profit levels.

### 6. Position Management

The monitoring service runs 24/7:

- **Trailing stops** — dynamically tightens stop-loss as price moves favorably, pushes updates to eToro
- **Partial exits** — takes 33% profit at +18% gain
- **Fundamental exits** — checks earnings surprises, revenue growth, sector rotation daily
- **Time-based exits** — closes positions exceeding max holding period (60 days daily, 48h 4H, 2h 1H)
- **Zombie exits** — closes positions flat (±1%) for 14+ days (capital redeployment)
- **Pending closures** — auto-closes positions flagged by any exit mechanism
- **Decay scoring** — daily health score; strategies with persistent losses set to pending_retirement

### 7. The Feedback Loop

Every trade is logged to the Trade Journal with full context: entry/exit prices, slippage, market regime, conviction score, strategy metadata. This feeds back into the strategy proposer:

- Templates that produce winners get higher proposal weights next cycle
- Templates that consistently lose get deprioritized
- Slippage data by symbol and time-of-day informs execution decisions

---

## Architecture

```
Frontend (React/TypeScript/Vite)     Backend (FastAPI/Python/uvicorn)
┌─────────────────────┐              ┌──────────────────────────────┐
│ Overview Dashboard  │◀── REST ───▶│ API Layer (FastAPI)          │
│ Portfolio           │   + WS      │   ├── account.py             │
│ Orders              │              │   ├── orders.py              │
│ Strategies          │              │   ├── strategies.py          │
│ Analytics           │              │   ├── analytics.py           │
│ Autonomous Control  │              │   ├── signals.py             │
│ Risk Management     │              │   ├── control.py             │
│ Data Management     │              │   └── alerts.py              │
│ Settings            │              ├──────────────────────────────┤
└─────────────────────┘              │ Core Services                │
                                     │   ├── TradingScheduler       │
                                     │   ├── MonitoringService      │
                                     │   └── OrderMonitor           │
                                     ├──────────────────────────────┤
                                     │ Strategy Engine              │
                                     │   ├── StrategyProposer       │
                                     │   ├── StrategyEngine (DSL)   │
                                     │   ├── PortfolioManager       │
                                     │   ├── ConvictionScorer       │
                                     │   └── AutonomousManager      │
                                     ├──────────────────────────────┤
                                     │ Data Layer                   │
                                     │   ├── MarketDataManager      │
                                     │   ├── FundamentalProvider    │
                                     │   └── NewsSentimentProvider  │
                                     ├──────────────────────────────┤
                                     │ Execution                    │
                                     │   ├── OrderExecutor          │
                                     │   ├── PositionManager        │
                                     │   └── RiskManager            │
                                     ├──────────────────────────────┤
                                     │ eToro API Client             │
                                     │   └── Circuit Breaker        │
                                     └──────────────┬───────────────┘
                                                    │
                                     ┌──────────────▼───────────────┐
                                     │ PostgreSQL 16 │ eToro API    │
                                     │ (32+ tables,  │ (orders,     │
                                     │  780K+ rows,  │  positions,  │
                                     │  EC2-hosted)  │  market data)│
                                     └──────────────┴───────────────┘
```

**Infrastructure:** AWS EC2 t3.medium (eu-west-1), Nginx SSL termination, systemd service management, CloudWatch alerting. Dashboard at https://alphacent.co.uk.

---

## Data Sources

| Source | What It Provides | Usage |
|--------|-----------------|-------|
| **eToro API** | Live prices, order execution, position management | Primary execution venue |
| **Yahoo Finance** | Historical OHLCV for stocks/ETFs/crypto/forex | Backtesting, signal generation |
| **FMP (Financial Modeling Prep)** | Fundamentals, analyst estimates, insider trading, sector ETF performance, earnings calendar | Alpha Edge strategies, fundamental exits, conviction scoring |
| **FRED (Federal Reserve)** | VIX, treasury yields, Fed funds rate, CPI | Macro regime detection, yield curve gate |
| **Marketaux** | News sentiment (free tier, 100 req/day) | Tiebreaker in conviction scoring (±1pt) |
| **PostgreSQL 16** | All persistence — prices, strategies, positions, orders, equity snapshots | DB-first caching, survives restarts |

---

## Risk Controls

### Position Sizing
- **Base risk:** 0.2% of equity per trade (risk-dollar sizing, not capital allocation)
- **Confidence scalar:** 0.5×–1.0× based on signal confidence
- **Volatility scalar:** TARGET_VOL(16%) / realized_vol, capped 0.10×–1.50×
- **Live balance check:** Re-reads DB balance before every order — never sizes against stale account state
- **Symbol cap:** Max 5% of equity per symbol
- **Sector soft cap:** Halve size if sector > 30% of equity
- **Portfolio heat cap:** Total open risk-dollars ≤ 8% of equity
- **Drawdown sizing:** 50% reduction at >5% drawdown, 75% at >10% (30d rolling peak)
- **Minimum order:** $2,000

### Portfolio Guards
- **Directional quotas:** Regime-specific min long/short percentages (never 0% short)
- **Sector cap:** Max 40% in any sector
- **Short concentration:** Max 3 open equity shorts in non-bearish regimes
- **VaR check:** 1-day 95% historical VaR ≤ 2% of equity (fail-open)

### Execution Guards
- **ATR floor:** SL must be ≥ 2.5× ATR(14) — prevents stops too tight for instrument volatility
- **Spread adjustment:** SL/TP widened by bid-ask spread to prevent immediate stop-outs
- **Market hours gate:** Stocks/ETFs blocked outside market hours (crypto 24/7)
- **Circuit breaker:** eToro API failures → automatic backoff (5 failures → 60s cooldown)
- **Stale order cleanup:** Pending orders > 24h auto-cancelled

### System Guards
- **Max orders per run:** 15 orders per signal generation cycle
- **Max batch exposure:** 40% of equity per signal generation run
- **Regime gate:** Equity shorts blocked in non-bearish regimes (unless strongly bearish news)
- **VIX panic filter:** New equity LONGs blocked when VIX > 30 and spiking
- **Yield curve gate:** New equity LONGs blocked when 2s10s spread < -0.25%

---

## Current State (April 2026)

| Metric | Value |
|--------|-------|
| Account equity | ~$475K (eToro DEMO) |
| Open positions | ~147 |
| Active DEMO strategies | ~96 |
| BACKTESTED strategies | ~109 |
| Symbol universe | 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto) |
| Strategy templates | 185 |
| Market regime | trending_up_weak (equity), equity correction in progress |
| Directional split | ~97% LONG, ~3% SHORT (SHORT equity pipeline recently unblocked) |
| Scheduled cycles | Daily 15:15 UTC + weekdays 19:00 UTC |
| Uptime | 24/7 on EC2, CloudWatch alerting |
