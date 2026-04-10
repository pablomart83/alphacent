# AlphaCent — Autonomous Trading Platform

## What Is It

AlphaCent is a fully autonomous trading system that runs on eToro. It generates its own strategies, validates them against historical data, executes trades, manages risk, and learns from results — all without human intervention.

Currently running on a ~$415K eToro DEMO account to prove profitability before deploying real capital.

## The 30-Second Version

```
Market Data → Strategy Ideas → Backtest & Validate → Activate Winners → Trade Signals → Execute on eToro → Monitor & Manage → Learn & Repeat
```

The system covers 117 instruments: stocks, ETFs, crypto, forex, indices, and commodities.

---

## End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                     AUTONOMOUS CYCLE (weekly)                       │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌────────────┐   ┌───────────┐ │
│  │ Strategy  │──▶│  Walk-Forward │──▶│  Activate  │──▶│  Signal   │ │
│  │ Proposals │   │  Validation  │   │  Winners   │   │Generation │ │
│  └──────────┘   └──────────────┘   └────────────┘   └─────┬─────┘ │
│   100 ideas       No overfitting     Tiered system         │       │
│   76 templates     train/test split   Sharpe-based         │       │
│   117 symbols                                              │       │
└────────────────────────────────────────────────────────────┼───────┘
                                                             │
                                                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    SIGNAL → ORDER → POSITION                        │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌────────────┐   ┌───────────┐ │
│  │  Signal   │──▶│    Risk      │──▶│  Execute   │──▶│  Position │ │
│  │Validation │   │  Management  │   │  on eToro  │   │  Created  │ │
│  └──────────┘   └──────────────┘   └────────────┘   └───────────┘ │
│   Duplicate       Position sizing    Market order     DB + eToro   │
│   filter          Portfolio balance  SL/TP attached   tracked      │
│   Correlation     Sector limits      Spread-adjusted               │
│   check           Direction caps                                   │
└─────────────────────────────────────────────────────────────────────┘
                                                             │
                                                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   24/7 MONITORING SERVICE                            │
│                                                                     │
│  MAIN LOOP (never blocked):                                         │
│  Every 30s: Process pending orders (~instant)                       │
│  Every 30s: Check order status on eToro (~instant, cached 30s)      │
│  Every 30s: Check trailing stops + partial exits (DB only, ~instant)│
│  Every 60s: Sync positions from eToro (1 API call, all positions)    │
│  Every 60s: Process pending closures (~instant)                     │
│  Every 60s: Evaluate alert thresholds (~instant)                    │
│                                                                     │
│  BACKGROUND THREADS (non-blocking):                                 │
│  Every 10m: Quick price update (8-12s typical, 50s+ under load)     │
│             + signal generation for all active/backtested strategies │
│  Every 55m: Full price sync — 117 symbols × 1h (180d) + 1d (15-30s)  │
│                                                                     │
│  DAILY:                                                             │
│  Fundamental exits, time-based exits, stale order cleanup,          │
│  data retention cleanup, performance feedback update                │
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

The system runs 190+ strategy templates across three timeframes and five strategy families, covering all 9 market regimes for both crypto and equities.

### Strategy Families

| Family | Concept | Key Indicators | Best Regime |
|--------|---------|---------------|-------------|
| **Trend Following** | Ride sustained directional moves | EMA crossover, ADX > 25, MACD signal cross, VWAP trend | Trending up/down |
| **Mean Reversion** | Fade overextensions back to equilibrium | RSI extremes, BB band touch, VWAP deviation, Stochastic, Z-score | Ranging / sideways |
| **Breakout** | Catch the start of new moves after compression | Donchian channel (HIGH_N), BB squeeze, volume expansion, ATR contraction | Transition / low-vol |
| **Momentum** | Buy strength, sell weakness | Price > N-bar high + volume, MACD histogram, EMA ribbon expansion | Trending (strong) |
| **Volatility** | Trade volatility expansion/contraction | ATR breakout, BB bandwidth, Keltner channel | Any (adapts) |

### Template Coverage by Timeframe

| Timeframe | Templates | Strategy Types | Regime Coverage |
|-----------|-----------|---------------|-----------------|
| **Daily** | 109 | All 5 families + 14 Alpha Edge (fundamental) | All 9 regimes |
| **1H** | 63 | Mean reversion (37), Trend (12), Breakout (6), Momentum (4), Volatility (4) | All 9 regimes |
| **4H** | 17 | Mean reversion (6), Trend (6), Breakout (4), Momentum (1) | All 9 regimes |

### Technical Indicators (13)

| Indicator | Type | Usage |
|-----------|------|-------|
| RSI | Oscillator | Oversold/overbought detection, momentum confirmation |
| MACD | Trend/Momentum | Signal crossovers, histogram direction, trend confirmation |
| Bollinger Bands | Volatility | Band touch reversion, squeeze breakout (std_dev-aware: 1.5, 1.8, 2.0, 2.5) |
| Stochastic | Oscillator | Fast (5) and standard (14) for oversold/overbought, crossover signals |
| SMA / EMA | Trend | Crossovers, pullback anchors, trend direction (8, 10, 20, 21, 30, 50 periods) |
| ATR | Volatility | Adaptive stop-loss, overextension detection, position sizing |
| ADX | Trend Strength | Trend confirmation (> 25 = active trend), regime filter |
| VWAP | Institutional | Daily-reset volume-weighted anchor, trend continuation, mean reversion |
| Volume MA | Volume | Volume spike detection, breakout confirmation |
| Support/Resistance | Price Structure | Range boundaries, breakout levels |
| Price Change % | Momentum | Gap detection, spike fade entries |
| Standard Deviation | Volatility | Z-score calculation, band width |
| Rolling High/Low | Breakout | Donchian channel, N-bar high/low breakout |

### Crypto-Specific Design

- 31 crypto-optimized 1H templates with wider stops, 24/7 trading assumptions, and crypto-specific thresholds
- 7 crypto-optimized 4H templates including downtrend bounce and ATR snap strategies
- Regime detection uses BTC/ETH as benchmarks when filtering to crypto-only cycles
- SHORT crypto templates blocked at scoring time (eToro doesn't allow crypto shorting)
- 4H bars synthesized from 1H data (Yahoo doesn't provide native 4H candles)

### Market Regimes (9)

| Regime | Detection | Template Count (1H + 4H) |
|--------|-----------|--------------------------|
| Trending Up Strong | 20d > 5%, 50d > 10% | 6 + 2 |
| Trending Up Weak | 20d 2-5%, 50d 5-10% | 12 + 5 |
| Trending Down Strong | 20d < -5%, 50d < -10% | 7 + 4 |
| Trending Down Weak | 20d -5% to -2% | 14 + 5 |
| Ranging Low Vol | ATR/price < 2%, flat trend | 42 + 6 |
| Ranging High Vol | ATR/price > 3%, flat trend | 23 + 10 |

---

## Key Components

### 1. Strategy Proposals

The system generates ~100 strategy candidates per cycle from the template library:

- **DSL Templates (175+):** Technical indicator combinations across all 5 strategy families. Each template defines entry/exit rules using a domain-specific language. Covers daily, 1H, and 4H timeframes with regime-specific activation.
- **Alpha Edge Templates (14):** Fundamental-driven strategies using real FMP data:
  - **Earnings Momentum / Earnings Miss Short** — real analyst estimate surprise (actual vs consensus EPS)
  - **Revenue Acceleration** — quarterly revenue growth acceleration
  - **Insider Buying** — real FMP insider trading data (net purchases)
  - **Dividend Aristocrat** — dividend yield + ROE with 180-day entry spacing and technical confirmation
  - **Quality Mean Reversion / Quality Deterioration Short** — quarterly ROE and D/E with RSI oversold
  - **Sector Rotation / Sector Rotation Short** — real FMP sector ETF performance rankings
  - **Relative Value** — P/E ratio mean reversion
  - **Pairs Trading** — correlation-based spread trading (8 pairs)
  - **Analyst Revision Momentum** — consecutive upward EPS estimate revisions
  - **Share Buyback Momentum** — companies actively reducing share count
  - **End-of-Month Momentum** — disabled (FMP Starter lacks institutional flow data)

Each strategy gets a **watchlist of 5 symbols** ranked by suitability score (including fundamental fitness for AE templates), so a single strategy can fire on whichever symbol in its watchlist is actually showing the signal.

**Smart proposal management:**
- **Zero-trade blacklist** — template+symbol combos producing 0 trades in walk-forward are blocked for 7 days
- **Rejection blacklist** — combos rejected 3+ times at activation are blocked for 30 days
- **Fundamental scoring** — AE templates scored by revenue consistency, dividend history, insider activity, earnings recency, ROE availability

### 2. Walk-Forward Validation

Every strategy must pass walk-forward backtesting before activation:

```
Historical Data
├── Train Period → Optimize parameters
└── Test Period  → Validate out-of-sample
```

Window sizes are calibrated per interval for statistical significance:

| Interval | Train | Test | Min Bars (stocks) |
|----------|-------|------|--------------------|
| Daily | 365 days | 180 days | ~252 / ~126 |
| 4H | 240 days | 120 days | ~360 / ~180 |
| 1H | 180 days | 90 days | ~1,260 / ~630 |

This prevents overfitting. A strategy that looks great on training data but fails on unseen data gets rejected. The system clears all caches between train and test periods to ensure a clean evaluation. Crypto gets 3x more bars at the same calendar window (24/7 trading). Wider intraday windows ensure the test period captures multiple market regimes (not just a single crash or rally).

### 3. Activation & Retirement

Strategies are activated on a tiered system based on Sharpe ratio:

| Tier | Sharpe | Max Allocation |
|------|--------|----------------|
| 1 — High Confidence | > 1.0 | 30% |
| 2 — Medium | 0.5 – 1.0 | 15% |
| 3 — Low | 0.3 – 0.5 | 10% |
| Reject | < 0.3 | — |

Strategies are automatically retired when performance degrades below thresholds. Before activation, the system checks if a strategy would immediately fail retirement — preventing wasted activation slots.

### 4. Signal Generation & Execution

Active and approved-BACKTESTED strategies generate signals every hour. Before a signal becomes an order:

1. **Duplicate check** — no second position on the same symbol/direction (includes manual eToro positions)
2. **Correlation filter** — rejects signals correlated > 0.8 with existing positions
3. **Portfolio balance** — max 40% sector exposure, max 65% directional exposure
4. **Risk sizing** — regime-based position sizing (2% base allocation), includes ALL positions (manual + autonomous) in exposure calculations
5. **Conviction scoring** — combines signal strength + fundamentals + regime fit
6. **In-run dedup** — prevents duplicate orders within a single signal generation run

Orders are submitted to eToro as market orders with spread-adjusted stop-loss and take-profit levels. Market regime is attached to signal metadata for trade journal tracking.

### 5. Position Management

The monitoring service runs 24/7 and handles:

- **Trailing stops** — dynamically tightens stop-loss as price moves favorably, pushes updates to eToro
- **Partial exits** — takes profit at configurable levels (e.g., close 50% at +5%)
- **Fundamental exits** — checks earnings surprises, revenue growth, sector rotation daily
- **Time-based exits** — closes positions exceeding max holding period (60 days for daily, 24h for hourly, 48h for 4H strategies)
- **Pending closures** — auto-closes positions flagged by any exit mechanism
- **Idle strategy demotion** — DEMO strategies with no open positions or pending orders are demoted to BACKTESTED (keeps `activation_approved=True` so they continue scanning and get re-promoted on next signal)

### Strategy Lifecycle

```
PROPOSED → BACKTESTED (walk-forward passed, activation_approved=True)
    → scanning for signals
    → signal fires → promoted to DEMO (position opened)
    → position closes → no more positions? → back to BACKTESTED (keeps scanning)
    → poor performance over 60 days → RETIRED
```

### 6. The Feedback Loop

Every trade is logged to the Trade Journal with full context: entry/exit prices, slippage, market regime, conviction score, strategy metadata. This data feeds back into the strategy proposer:

- Templates that produce winners get higher proposal weights next cycle
- Templates that consistently lose get deprioritized
- Slippage data by symbol and time-of-day informs execution decisions
- Regime-specific performance guides which strategies to activate in which market conditions

---

## Architecture

```
Frontend (React/TypeScript)          Backend (FastAPI/Python)
┌─────────────────────┐              ┌──────────────────────────────┐
│ Dashboard           │◀── REST ───▶│ API Layer (FastAPI)          │
│ Portfolio           │   + WS      │   ├── account.py             │
│ Orders              │              │   ├── orders.py              │
│ Strategies          │              │   ├── strategies.py          │
│ Analytics           │              │   ├── analytics.py           │
│ Autonomous Control  │              │   ├── signals.py             │
│ Risk Management     │              │   └── alerts.py              │
│ Settings            │              ├──────────────────────────────┤
└─────────────────────┘              │ Core Services                │
                                     │   ├── TradingScheduler       │
                                     │   ├── MonitoringService      │
                                     │   └── OrderMonitor           │
                                     ├──────────────────────────────┤
                                     │ Strategy Engine              │
                                     │   ├── StrategyProposer       │
                                     │   ├── StrategyEngine         │
                                     │   ├── PortfolioManager       │
                                     │   └── AutonomousManager      │
                                     ├──────────────────────────────┤
                                     │ Data Layer                   │
                                     │   ├── MarketDataManager      │
                                     │   ├── FMP Cache Warmer       │
                                     │   └── FundamentalProvider    │
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
                                     │ SQLite DB    │ eToro API     │
                                     │ (positions,  │ (orders,      │
                                     │  orders,     │  positions,   │
                                     │  strategies, │  market data) │
                                     │  journal,    │               │
                                     │  prices)     │               │
                                     └──────────────┴───────────────┘
```

## Data Sources

| Source | What It Provides | Usage |
|--------|-----------------|-------|
| **eToro API** | Live prices, order execution, position management | Primary execution venue |
| **Yahoo Finance** | Historical OHLCV data for stocks/ETFs/crypto | Backtesting, signal generation |
| **FMP (Financial Modeling Prep)** | Fundamentals, analyst estimates, insider trading, sector ETF performance, forex data | Alpha Edge strategies, fundamental exits, symbol scoring (Starter plan: 300 calls/min, annual data only) |
| **FRED (Federal Reserve)** | VIX, treasury yields, Fed funds rate, CPI, unemployment | Macro regime detection, risk-on/risk-off context |
| **SQLite** | Local persistence for everything | DB-first caching, survives restarts |

## Risk Controls

- **Portfolio stop-loss:** 10% drawdown from peak → pause all trading
- **Daily loss limit:** 3% daily loss → pause for the day
- **Per-symbol cap:** Max 20% exposure to any single symbol
- **Per-strategy cap:** Max 30% exposure to any single strategy
- **Sector cap:** Max 40% in any sector
- **Direction cap:** Max 60% long or short
- **Circuit breaker:** eToro API failures trigger automatic backoff (5 failures → 60s cooldown)
- **Stale order cleanup:** Pending orders > 24h auto-cancelled
- **Correlation-adjusted sizing:** Reduces position size when correlated positions exist
