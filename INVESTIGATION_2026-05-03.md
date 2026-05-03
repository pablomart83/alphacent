# AlphaCent — Crypto-Activation Investigation

**Session:** 2026-05-03 (Sunday)
**Mode:** READ-ONLY on src/ and config/. No code or config changes until verdict accepted.
**Mission:** Determine whether the persistent 0-crypto-activation outcome across 30+ autonomous cycles is:
- (a) honest output given eToro costs + current regime
- (b) a structural bug in the activation gate math
- (c) a library calibrated for the wrong cost environment
- (d) a regime-detector mismatch

Context going in: Sprints 1-5 shipped. Library = 139 strategies (76+ crypto, 20+ equity, 20+ Alpha Edge). 67 active trading strategies (63 DEMO + 4 BACKTESTED/approved crypto). Every recent cycle proposes 8-9, passes 8/8 at WF, rejects all at activation.

---

## Phase 1 — Funnel quantification

### 1.1 — 10-cycle history (from cycle_history.log)

Cycles ordered most-recent-first. Activations in the 4 May-1 cycles were non-crypto (equity/AE); all crypto candidates that reached activation since the May-2 S3.0d deploy (18:30 UTC) have been rejected.

| Cycle ID | Time (UTC) | Proposals (DSL/AE) | WF passed | Activated | Rejected @ activation |
|---|---|---|---|---|---|
| `cycle_1777803232` | 2026-05-03 10:19 | 8 (7/1) | 8/8 (100%) | **0** | 8 |
| `cycle_1777801989` | 2026-05-03 10:00 | 8 (7/1) | 8/8 (100%) | **0** | 8 |
| `cycle_1777758033` | 2026-05-02 21:46 | 9 (8/1) | 9/9 (100%) | **0** | 9 |
| `cycle_1777752044` | 2026-05-02 20:04 | 8 (7/1) | 8/8 (100%) | **0** | 8 |
| `cycle_1777744588` | 2026-05-02 17:59 | 7 (5/2) | 6/7 (85.7%) | **0** | 6 |
| `cycle_1777743964` | 2026-05-02 17:49 | 6 (4/2) | 5/6 (83.3%) | **0** | 5 |
| `cycle_1777742566` | 2026-05-02 17:26 | 9 (7/2) | 8/9 (88.9%) | **0** | 8 |
| `cycle_1777742013` | 2026-05-02 17:14 | 9 (7/2) | 8/9 (88.9%) | **0** | 8 |
| `cycle_1777741379` | 2026-05-02 17:06 | 9 (7/2) | 8/9 (88.9%) | **0** | 8 |
| `cycle_1777740049` | 2026-05-02 16:41 | 11 (9/2) | 10/11 (90.9%) | **0** | 10 |

**Key observation:** 10 cycles, 84 proposals, 78 WF-validated (93%), **0 activations.** Proposal-and-WF engine is producing 8-9 candidates every cycle consistently; the bottleneck is entirely at the activation gate.

*(Prior to May 2 late afternoon, the cycles that activated — 3-4 per cycle on May 1 — were predominantly equity/AE, not crypto. The only crypto activations in the signal_decisions table are the 4 BTC Follower Daily strategies from `cycle_1777736694` via the F2 family-cross-validation bypass on May 2 15:48 UTC.)*

### 1.2 — Current active crypto book

Four strategies, all crypto BACKTESTED (= DEMO-approved, awaiting first signal):

| Strategy | Status | Created | live_trade_count | Family CV score |
|---|---|---|---|---|
| Crypto BTC Follower Daily ETH LONG | BACKTESTED | 2026-05-02 | 0 | 0.667 |
| Crypto BTC Follower Daily SOL LONG | BACKTESTED | 2026-05-02 | 0 | 0.667 |
| Crypto BTC Follower Daily LINK LONG | BACKTESTED | 2026-05-02 | 0 | 0.667 |
| Crypto BTC Follower Daily AVAX LONG | BACKTESTED | 2026-05-02 | 0 | 0.667 |

**Non-crypto active book:** 62 DEMO + 1 DEMO ETF + 82 BACKTESTED stock/etf/forex = 148 non-crypto. Of the 304 distinct strategies that closed a trade in the last 30 days, **28 are crypto positions** closed by earlier (since-retired) crypto strategies; zero are from the 4 currently-active BTC Follower Daily strategies (they haven't fired — entry gate `LAG_RETURN("BTC", 2, "1d") > 0.05` hasn't triggered since activation).

### 1.3 — 14-day signal_decisions funnel, split by asset class

Signal_decisions table only has data from 2026-05-02 onward (table was created mid-session May 2).

| Class | proposed | wf_rejected | wf_validated | cross_validation | activated | rejected_act |
|---|---|---|---|---|---|---|
| Crypto | 2,327 | 1,879 | 69 | 35 | **4** | 134 |
| Non-crypto | 845 | 659 | 37 | 0 | **5** | 60 |
| **Total** | **3,172** | **2,538** | **106** | **35** | **9** | **194** |

**Conversion rates (crypto vs non-crypto):**

| Stage transition | Crypto | Non-crypto |
|---|---|---|
| proposed → wf_validated | 69/2327 = **3.0%** | 37/845 = **4.4%** |
| wf_validated → activated (normal path) | 4/69 = **5.8%** (all via F2 bypass) | 5/37 = **13.5%** |
| wf_validated → rejected_act | 134/69* = 194% (multi-cycle retries on same strategies) | 60/37* = 162% |

*\*Ratio >100% because the same candidate is re-proposed and re-rejected across cycles; each rejection is counted fresh.*

**The bottleneck for crypto is unambiguously wf_validated → activation.** WF is not over-filtering (3% vs 4.4% is in the same order of magnitude). The normal-path activation rate on crypto is effectively **zero**; the 4 crypto activations we do see are all via the F2 family-cross-validation bypass, not the normal path.

### 1.4 — Per-template activation rate (14 days)

Top-proposed crypto templates with their outcomes:

| Template | proposed | wf_validated | rejected_act | activated |
|---|---|---|---|---|
| Crypto Volume Spike Entry | 119 | 0 | 1 | 0 |
| Crypto Weekly Trend Follow | 110 | 4 | 39 | 0 |
| Crypto EMA Ribbon | 104 | 0 | 7 | 0 |
| Crypto Quiet EMA Hug Long | 99 | 9 | 11 | 0 |
| Crypto Cross-Sectional Momentum | 96 | 26 | 27 | 0 |
| Crypto Trend Breakout | 94 | 0 | 0 | 0 |
| Crypto 4H RSI Dip Buy | 93 | 1 | 1 | 0 |
| Crypto 4H MACD Trend | 93 | 0 | 0 | 0 |
| Crypto Quiet MACD Momentum | 92 | 0 | 0 | 0 |
| Crypto RSI Dip Buy | 93 | 0 | 0 | 0 |
| Crypto SMA Reversion | 87 | 14 | 23 | 0 |
| Crypto BB Mean Reversion | 84 | 0 | 0 | 0 |
| Crypto Stochastic Recovery | 86 | 0 | 0 | 0 |
| 4H Crypto Consolidation Break | 83 | 0 | 0 | 0 |
| Crypto 4H BB Squeeze Breakout | 81 | 0 | 0 | 0 |
| Crypto OBV Accumulation Daily | 74 | 2 | 2 | 0 |
| Crypto 1H RSI Extreme Bounce | 79 | 13 | 15 | 0 |
| Crypto Keltner Range Trade | 73 | 0 | 3 | 0 |
| Crypto BTC Follower 4H | 76 | 0 | 3 | 0 |
| **Crypto BTC Follower Daily** | **32** | **0*** | **1** | **4** |

*\*BTC Follower Daily's WF outcomes are recorded as `cross_validation` (35 rows), not `wf_validated`, because its activations go through the F2 family-level path.*

Rejection-reason buckets (last 3 days, rejected_act stage):

| Reason | Count |
|---|---|
| Net return < 0 after costs | 14+15+3+3+3+3 = **41** (26% of rejections) |
| Sharpe < gate | 12+12+11+9+6+3+3 = **56** (36%) |
| Return/trade < min (RPT gate) | 10+7+3+3+3 = **26** (17%) |
| WinRate < 25-45% floor | 3 (2%) |
| Ex-post 730d Sharpe < -0.5 | ~3 (2%) |

The three dominant rejection categories are Sharpe, Net-return-negative, and RPT. None of these can be attributed to an over-tight gate — each rejects strategies whose test-window metrics show **the strategy would have lost money on this symbol in the test window.**

---

## Phase 2 — Walk-through of one rejected strategy (`Crypto BTC Follower 4H ETH LONG`)

Using the exact log line from `cycle_1777803232` at 2026-05-03 10:19:31 UTC.

### 2.1 — Which backtest window produced `total_return = 5.0%`?

From the proposer log (same cycle):

```
10:19:24  MC bypass (heavy-tail, n=12<20): Crypto BTC Follower 4H ETH LONG
          train=1.48 test=0.88 — consistency OK, passed
10:19:25  Edge-ratio thin: Crypto BTC Follower 4H ETH LONG —
          gross/trade=0.189%, cost/trade=2.200%, edge_ratio=0.09
          (below break-even, not filtered — recorded for Data Page)
10:19:27  [3/8] Backtesting: Crypto BTC Follower 4H ETH LONG (730 days)...
10:19:27  Backtesting strategy from 2024-05-03 to 2026-05-03
10:19:27  Backtest complete: return=4.99%, sharpe=1.44, trades=6
10:19:31  Edge-ratio thin at activation: ... gross/trade=1.185%,
          cost/trade=2.200%, edge_ratio=0.54
10:19:31  Strategy failed activation:
          Return/trade 0.831% < 1.800% min (crypto_4h+template_override,
          6 trades, gross 5.0%)
```

**The `5.0%` number** that the activation gate sees comes from the **730-day ex-post backtest** (2024-05-03 → 2026-05-03), not from the 180-day WF test window (which saw train_sharpe=1.48, test_sharpe=0.88, ~12 test trades).

This is Sprint 5 F2 ex-post sanity behaviour working as designed: re-backtest on 730d to catch strategies that fit only the recent quarter.

### 2.2 — Cost-model arithmetic sanity check

From `config/autonomous_trading.yaml::backtest.transaction_costs.per_symbol.ETH`:
- commission: 1.0% per side
- spread: 0.05% per side
- slippage: 0.05% per side
- round trip = 2 × (1.0 + 0.05 + 0.05) = **2.20%**

The `cost/trade=2.200%` log line matches exactly.

At init_cash=$100,000 and avg_trade_value ≈ 10% of init (≈ $10,000), a 6-trade backtest generates cost = 6 × 2 × $10,000 × (1%+0.05%+0.05%) = 6 × 2 × $10,000 × 1.1% = **$1,320** which is 1.32% of init_cash. That's the per-trade attributed cost for a 6-trade strategy — materially less than the 2.20% round-trip cost-per-trade used in edge_ratio.

**Arithmetic is internally consistent but the two numbers measure different things:**
- `edge_ratio` uses `round_trip_cost_pct` (2.20% = cost-per-trade assuming 100% capital allocation per trade)
- the backtest engine deducts the actual dollar cost using average position size (≈ 10% allocation)

Both numbers are correct for their respective purposes. This is not a double-count — they're computed in different code paths for different consumers.

### 2.3 — RPT gate: is NET being compared to a GROSS floor?

This is the question the user flagged as possibly unit-mismatched. Walking through `portfolio_manager.evaluate_for_activation`:

File `src/strategy/portfolio_manager.py` lines 1137-1170:

```python
# The backtest engine (_run_vectorbt_backtest) already deducts transaction
# costs from total_return using actual position sizes. The total_return in
# BacktestResults is NET of costs. Do NOT deduct costs again here.
net_return = backtest_results.total_return          # line 1137

if net_return < 0:
    reason = f"Net return {net_return:.1%} < 0 ..."
    return False, reason

...

if backtest_results.total_trades > 0:
    return_per_trade = backtest_results.total_return / backtest_results.total_trades   # line 1307
    if return_per_trade < min_return_per_trade:
        reason = f"Return/trade {return_per_trade:.3%} < {min_return_per_trade:.3%} min ..."
```

**Line 1307 uses `backtest_results.total_return` — which the comment at line 1137 says is NET of costs.** The min_return_per_trade floor (config: `crypto_4h: 0.030`, overridden to `0.018` by template `min_rpt_override`) was derived in Session_Continuation as a gross-edge floor: "floor = round_trip_cost (2.96%) + 50bps edge = 3.5%" (Sprint 1 F3).

Let's cross-check against the observed numbers for BTC Follower 4H ETH:
- gross_return (from edge_ratio log at WF: `gross/trade=0.189%` × 12 WF trades ≈ 2.27%)
- net_return (from backtest: `return=4.99%` on 6 trades over 730d ex-post)
- cost/trade (edge_ratio): 2.20%

So within a single cycle we see **two different edge-ratio calculations for the same strategy**:
- WF path (12 trades, 180d): `gross/trade=0.189%`, `edge_ratio=0.09` — this is on the **180d test window WF backtest** where cost-per-trade is correctly subtracted inside the engine.
- Activation path (6 trades, 730d): `gross/trade=1.185%`, `edge_ratio=0.54` — this is on the **730d ex-post backtest.** 1.185% × 6 = 7.1% gross, minus ~2.20% × 6 × 10% = 1.32% cost attribution ≈ 5.8% net ≈ matches the logged `return=4.99%` within rounding.

So `total_return = 5.0%` IS net of costs (comment is accurate). `total_return / total_trades = 5.0%/6 = 0.83%` is **net return per trade**.

The gate then compares `0.831% (NET/trade)` against `min_return_per_trade = 1.8%` (the template override of the 3.0% crypto_4h floor, clamped to 60% of 3.0% = 1.8%).

**Unit question:** was 1.8% intended as gross-or-net? Reading Sprint 1 F3 in Session_Continuation:

> "round_trip_cost (2.96%) + 50bps minimum edge = 3.5%. Anything below this is noise after costs."

"Anything below this [3.5%] is noise **after costs**" — ambiguous wording. The derivation `cost + edge = 3.5%` reads like a **gross** target (cost covered plus edge margin). But the description "after costs" reads like it's a **net** target.

Looking at the RPT gate consumers downstream (the log format says `gross 5.0%` as the friendly display), the designer clearly understood `total_return` is gross-display but *uses it as the net comparand.* That's a latent inconsistency in naming — `total_return` is labeled "gross 5.0%" in the log but it's actually net-of-cost per the comment.

**But the mathematical gate is:**

```
return_per_trade = total_return / total_trades       # 0.0499 / 6 = 0.00831 = 0.831%
compare to 0.018 (1.8% min_rpt_override)
```

And the *reality* for this strategy is:
- 730d backtest produced 5.0% NET after the vectorbt engine deducted `total_cost_pct = 1.32%` of init_cash for 6 trades at ≈10% position sizing.
- Gross-before-cost on the 730d backtest = 5.0% + 1.32% = 6.32%, i.e. 1.05%/trade gross.
- Edge ratio 0.54 = 1.185% gross-per-trade / 2.20% round-trip-cost-per-trade. *(Slight discrepancy — edge_ratio uses `gross_return / n_trades / round_trip_cost` from the backtest's gross metric; since the code recomputes `_gross_act = net + transaction_costs_pct`, it's using the attribution divided by total trades.)*

**So: the RPT gate is comparing a NET metric (0.831%/trade) against a floor that was derived as GROSS (1.8% is clamped from 3.0%, which was 2.96% cost + 50bps edge). The floor is effectively demanding 1.8% NET per trade — which is 1.8% + 2.2%(cost/trade) = **4.0% gross per trade** to pass.**

That's a structurally demanding ask for a 6-trade-in-2-years swing template. But *it is not a mathematical bug* — the gate is doing what the code says. It's a *semantic drift*: the threshold was labelled as a gross-edge floor in Session_Continuation but is applied as a net-return floor.

**Verdict on hypothesis (b):** No hard math bug, but there IS a semantic inconsistency: **`min_return_per_trade` is compared against a net metric but was derived from a gross-edge rationale.** The RPT gate as applied is stricter than the rationale suggests. This matters for templates in the 0.5-1.5%/trade NET range (BTC Follower 4H ETH at 0.831%/trade net is in this zone).

Citation: `src/strategy/portfolio_manager.py:1307` uses `backtest_results.total_return / backtest_results.total_trades` with the `total_return` comment at line 1137-1139 stating it is net of costs. The threshold is read from `config/autonomous_trading.yaml::activation_thresholds.min_return_per_trade.crypto_4h = 0.030`, overridden per-template to 0.018 via `min_rpt_override` (safety-clamped to 60% × 0.030).

### 2.4 — Family cross-validation bypass check

For BTC Follower 4H ETH cycle_1777803232:
- decision_metadata at rejected_act: `"family_cross_validated": false, "cross_validation_score": 0.0`

Why didn't F2 rescue it? From Session_Continuation Sprint 1 evidence: "BTC Follower 4H: no improvement (all 5 alts still negative). Confirms 4H BTC lead-lag is not a real edge in current data window 2024-2026." Family-level threshold is ≥4/6 symbols cleared; only ETH clears in this cycle. The F2 gate correctly declines to bypass per-pair RPT for this template — 4H BTC lead-lag doesn't have family-level evidence, so the per-pair gate is the right gate for this strategy.

BTC Follower **Daily** is a different story: 4/6 alts cleared → F2 PASSED → activated in `cycle_1777736694`. The family mechanism works when the evidence is there.

### 2.5 — edge_ratio numerator (gross vs net)?

Two edge_ratio log lines in the same cycle for the same strategy:
- WF path: `gross/trade=0.189%, cost/trade=2.200%, edge_ratio=0.09` — `0.189/2.20 = 0.086 ≈ 0.09` ✓
- Activation path: `gross/trade=1.185%, cost/trade=2.200%, edge_ratio=0.54` — `1.185/2.20 = 0.539 ≈ 0.54` ✓

Both use gross/trade. Gross is computed as `net + transaction_costs_pct`. The 730d activation path has materially higher gross/trade (1.185%) because the 730d window catches more of the structurally lower-frequency BTC Follower setups.

**But the RPT gate at line 1307 uses `net` (total_return / total_trades), not gross.** The edge_ratio is observability-only (commented explicitly). So yes — *edge_ratio reports 0.54 on gross/trade vs a 1.0 break-even, and the RPT gate is comparing 0.83% net/trade against 1.8%. Two different numerators, both below their respective thresholds, reported as 'failed' with the RPT message.*

Both measurements agree that the strategy cannot cover costs with enough margin — one says "gross doesn't cover cost by 46%" (edge_ratio), the other says "net/trade is only 46% of the 1.8% min" (RPT gate). Both point at the same economic reality.

### 2.6 — Phase 2 findings summary

- **No math bug.** `total_return` is consistently net, commented correctly, used consistently.
- **Semantic drift:** the RPT threshold `min_return_per_trade.crypto_4h = 0.030` was derived in Session_Continuation as `2.96% cost + 0.5% edge` (implying gross-edge floor) but is applied against a net-per-trade metric. Net + 2.2% cost gives an implicit 4%+ gross-per-trade demand, which is quite high for a low-frequency swing template. The template override knocks it from 3.0% → 1.8%, softening but not removing the mismatch.
- **F2 bypass** works when family-level evidence is present; correctly does not bypass for 4H follower (where family evidence is absent).
- **edge_ratio** correctly uses gross/trade and is observability-only (not a gate). No conflict with RPT gate — they're complementary views of the same economic failure.

---

## Phase 3 — Cost-structure ceiling analysis

### 3.1 — Minimum gross-per-trade to clear activation for top crypto templates

To pass the activation gate, a crypto strategy must clear:
1. `net_return > 0` (post-cost)
2. `return_per_trade > min_return_per_trade` (from yaml × template override × 60% safety floor)
3. `Sharpe > min_sharpe_crypto = 0.3` (DEMO-loosened from 0.5)
4. Win rate > 25% hard floor (if expectancy positive) or 30% (crypto config)
5. No ex-post 730d sharpe < -0.5
6. Drawdown < 25%

Per-symbol round-trip cost (from `config/autonomous_trading.yaml::per_symbol` and `per_asset_class`):
- BTC: 2.18%
- ETH: 2.20%
- SOL/LINK/AVAX/DOT: **2.96%** (alt-coin default, commission 1% + spread 0.38% + slippage 0.1% all per side)

For the RPT gate to pass: **`gross_per_trade ≥ round_trip_cost + min_rpt`**

Example math for BTC Follower 4H ETH with override=0.018 (clamped 60% of crypto_4h=0.030):
- min_rpt (net) = 1.8%
- round_trip_cost = 2.20%
- implied gross/trade floor = 2.20% + 1.8% = **4.00% gross per trade**
- strategy actually delivered: 1.185% gross/trade → edge_ratio 0.54, RPT 0.83% net
- gap to gate: need **3.4× higher gross/trade** than observed

Same math for the ALT-coin branches (2.96% round-trip):

| Template | Interval | min_rpt (DEMO) | Required gross/trade | Typical observed gross/trade |
|---|---|---|---|---|
| Crypto 1H RSI Extreme Bounce (alt) | 1h | 3.0% | 5.96% | 0.6-1.0% |
| Crypto Cross-Sectional Momentum (alt) | 1d | 3.0% | 5.96% | 2.8-0.9% |
| Crypto Quiet EMA Hug Long (alt) | 1d | 3.0% | 5.96% | 0.5-2.2% |
| Crypto SMA Reversion (alt) | 1d | 3.0% | 5.96% | 1.7-0.0% |
| Crypto Weekly Trend Follow (alt) | 1d | 3.0% | 5.96% | 0.005% |
| Crypto BTC Follower 4H (ETH) | 4h | 3.0% | 5.20% | 1.185% |
| Crypto BTC Follower Daily (ETH) | 1d | 3.0% | 5.20% | ~1.3% |

For BTC Follower Daily, the F2 bypass removes the RPT requirement, which is why it's the only template to activate.

### 3.2 — Historical regime test

From Phase 4 data (BTC 20d / 50d rolling returns):

| Period | BTC 20d return | BTC 50d return | Regime class |
|---|---|---|---|
| 2026-04-17 to 2026-04-26 | +10.5% to +16.9% | +10.2% to +17.3% | `TRENDING_UP_STRONG` / `TRENDING_UP_WEAK` |
| 2026-04-27 to 2026-05-03 | +5.1% to +10.9% | +8.3% to +11.6% | `TRENDING_UP_WEAK` |
| 2026-04-04 to 2026-04-12 | -7.8% to -0.2% | -2.3% to +4.1% | `RANGING` / `TRENDING_DOWN_WEAK` |
| 2026-03-25 to 2026-04-03 | -5.7% to +0.6% | -5.9% to -1.1% | `RANGING` / `TRENDING_DOWN_WEAK` |

**BTC has been objectively in weak-to-strong uptrend for most of the past 3 weeks.** BTC gained from ~$66,400 (Mar-27) to $78,200 (May-03) — a +18% move over 37 trading days. This is not a ranging market for BTC.

But the proposer's detect_crypto_regime averages BTC + ETH 20d/50d, and ETH has underperformed BTC. Let me check the current 20d/50d metrics from the proposer log:

```
2026-05-03 09:53:20  Crypto regime: ranging_low_vol (20d=+2.3%, 50d=+6.6%, ATR/price=1.7%, conf=0.65)
```

**20d=+2.3% is below the 3% TRENDING_UP_WEAK threshold.** The regime detector is structurally tight by 70bps — if BTC+ETH averaged the BTC-only number (5.1% today), the regime would classify as TRENDING_UP_WEAK. The 3% threshold was chosen deliberately (Session_Continuation: "Crypto-calibrated thresholds (roughly 2× equity thresholds)") and is academically reasonable, but in current market, BTC+ETH averaging misses the 3% cutoff even though BTC alone has been trending for weeks.

**Net observation for hypothesis (c):** The templates cannot ever produce 5-6% gross per trade on a low-frequency setup (Crypto Weekly Trend Follow with expected 1-2 trades/year). Mathematics of the round-trip cost alone:
- For BTC at 2.18% round-trip: min net edge of 1.8% requires 4% gross/trade — achievable only on 15%+ moves
- For alts at 2.96% round-trip: min net edge of 3% requires 5.96% gross/trade — requires consistent 25%+ moves per holding period

This is not "impossible" on crypto when the regime is trending (alts can rally 30-50% in a month in a bull phase), but it is **structurally demanding in a ranging regime with BTC averaging 5-10% 20d moves.** The templates WILL propose strategies; the gate WILL reject them; this is the pipeline doing its job.

### 3.3 — Historical backtest ceiling — inferred from S3.0d cache clear

The S3.0d deploy (Session_Continuation, 2026-05-02 18:30 UTC) cleared 132 crypto WF cache entries (25 validated + 107 failed). Since then, the proposer has re-run WF on every crypto template against fresh data. Funnel bucket distribution post-S3.0d (from logs around cycle_1777758033):
- WF 0-TRADE: 11-17 per cycle (templates with zero trades on some alts)
- WF OVERFITTED (train>>test): 57-64 per cycle
- WF LOW WINRATE: 5-7 per cycle
- WF LOW SHARPE: 46-53 per cycle
- WF PASSED: 1 strategy per cycle typically

**Of the strategies that ARE in the WF PASSED bucket + WF LOW WINRATE (25-33% WR) + WF LOW TRADES (≤3 trades, high Sharpe) across the 10-cycle window, we see a consistent pattern:**
- BTC Follower Daily (ETH/SOL/LINK/AVAX): WF passes via F2 in a ~6/month cycle-burst when the BTC trigger fires historically
- BTC Follower 4H ETH: WF passes at Sharpe 0.88 with 12 trades in cycle_1777801989 and later — but **activation rejects because gross/trade at 1.185% cannot clear the 2.20% cost floor, let alone the 4% implied floor**
- Cross-Sectional Momentum SOL/LINK: WF passes at Sharpe 2.12 / 0.46 on 3-6 trades — activation rejects on RPT (2.8% gross/3 trades = 0.94%) or negative net return
- Quiet EMA Hug Long BTC: WF passes at Sharpe 2.56 / 4 trades / 75% WR — rejects on RPT (gross 2.2% / 4 trades = 0.55%/trade)

### 3.4 — Theoretical ceiling

For the Weekly Trend Follow template (ETH LONG) with 10 trades on 730d ex-post:
- gross/trade = 0.005% → total gross = 0.05% (!)
- The template is running but generating effectively zero edge

For Crypto Cross-Sectional Momentum SOL (3 trades on 730d):
- gross/trade = 0.945% × 3 = 2.83% total gross
- After 2.96% round-trip × 3 = 8.88% cost at 100% sizing or ~0.89% at 10% allocation
- Net after cost: approximately 1.94% net
- Per-trade net: 0.65% which is below 3.0% floor by 5x

### 3.5 — Templates structurally uneconomic on eToro alts (2.96% round-trip)

On alts (SOL, LINK, AVAX, DOT), any template that holds <14 days and targets <5% gross moves is structurally uneconomic:
- 1h templates (Hourly * family) — holds measured in hours, targets sub-1% moves → edge_ratio will always be < 0.5
- 4h mean-reversion (Crypto 4H RSI Dip Buy, Crypto 4H BB Squeeze Breakout) — similar
- Most proposed-but-never-advanced templates in the 1.4 table (Trend Breakout, Deep Dip Accumulation, etc. that sit at 0 wf_validated / 0 rejected_act)

The library contains a lot of 1h/4h templates that were designed on low-commission venues (Binance typical 0.1% per side, 0.2% round-trip — **15× cheaper than eToro alts**). A template that works at Sharpe 1.2 on Binance cannot work at Sharpe 0 on eToro alts without structural changes (vol targeting, much tighter entry filters, or longer holds).

**Templates with a realistic chance on eToro alts:**
- Weekly Trend Follow (designed 1-2 trades/year, 40%+ moves)
- Golden Cross (1 trade every 2-3 years, 100%+ moves)
- 21W MA Trend Follow (1-3 trades/year)
- Deep Dip Accumulation (rare, 75% SMA threshold)
- BTC Follower Daily family (activated — F2 bypass)

**Templates structurally broken by eToro cost environment on alts:**
- Any 1h or 4h mean-reversion (28+ templates in the library)
- Any daily mean-reversion or short-hold template targeting <5% gross
- All the `Crypto Hourly *` templates (12+ templates)

---

## Phase 4 — Regime classification check

### 4.1 — Has detect_crypto_regime ever returned TRENDING_UP in the last 90d?

Searched `alphacent.log*` for crypto regime labels:

| Timestamp | Regime | 20d | 50d | Conf |
|---|---|---|---|---|
| 2026-05-03 09:53 | ranging_low_vol | +2.3% | +6.6% | 0.65 |
| 2026-05-02 21:40 | ranging_low_vol | +1.4% | +10.2% | 0.65 |
| 2026-05-02 17:26 | ranging_low_vol | +1.0% | +9.8% | 0.65 |
| 2026-05-02 16:40 | ranging_low_vol | +1.0% | +9.8% | 0.65 |
| 2026-05-02 11:19 | ranging | +0.98% | +9.75% | 0.50 |
| 2026-05-02 08:48 | ranging | +0.98% | +9.75% | 0.50 |

**Not a single TRENDING_UP classification in the visible log history.** The 20d threshold of 3% (for TRENDING_UP_WEAK) is missing by 70bps consistently; the 50d threshold of 5% is met.

### 4.2 — Thresholds vs institutional practice

From `src/strategy/market_analyzer.py:1516-1525`:

```python
# A strong crypto uptrend is 20d >= +10%, weak is +3 to +10%.
if avg_20d >= 0.10 and avg_50d >= 0.15:
    regime = MarketRegime.TRENDING_UP_STRONG
elif avg_20d >= 0.03 and avg_50d >= 0.05:
    regime = MarketRegime.TRENDING_UP_WEAK
```

Compare to institutional references (cited in Session_Continuation):
- Man Group "In Crypto We Trend": define "trend" as 6m positive return, no daily threshold
- AdaptiveTrend paper (arxiv 2602.11708): uses multi-timeframe TSMOM (20/60/120 day) OR-gate, no 20d minimum
- `detect_sub_regime` widget: reportedly classifies 2.3%/6.6% as "weak uptrend"

Our thresholds (3% / 5% AND-gate) are roughly 2× equity thresholds — designed by a reasonable principle. But in comparison to how hedge funds define trend in crypto, our detector is on the tight side of reasonable. It's not **wrong**; it's just conservative. A 20d threshold of 2% would flip current classification to TRENDING_UP_WEAK and widen the proposer template pool.

**BTC alone** has delivered +18% over 30d and is above SMA(50). BTC+ETH averaging obscures this because ETH has lagged. 

### 4.3 — Templates blocked by ranging-regime gate that would otherwise pass

The proposer filters templates by `template.market_regimes` whitelist against the detected regime. Templates whose whitelist includes `TRENDING_UP_WEAK` but NOT `RANGING_LOW_VOL` will be excluded today.

I don't have the direct list of these without reading strategy_templates.py, but representative TREND templates that would likely unlock under TRENDING_UP_WEAK classification include:
- Crypto Trend Breakout (94 proposed in 14d — so it IS proposing under ranging)
- Crypto BTC Follower 4H (76 proposed)
- Crypto BTC Follower Daily (32 proposed)
- Crypto Donchian Breakout Daily (15 proposed)

Since these are already proposing under ranging_low_vol, regime gating is NOT the dominant blocker. The dominant blocker is the activation gate on NET RPT / Sharpe.

---

## Phase 5 — Honest-output assessment

### 5.1 — Active crypto strategies

4 active strategies (all BTC Follower Daily), created 2026-05-02, live_trade_count=0 on all. Entry gate `LAG_RETURN("BTC", 2, "1d") > 0.05`. BTC 2-bar return history from Phase 4 data:

| Date | BTC close | 2-bar return |
|---|---|---|
| 2026-05-03 | $78,221 | +0.49% |
| 2026-05-02 | $78,447 | +0.28% |
| 2026-04-30 | $76,346 | +0.74% |
| ... | | |

BTC 2-bar return peaked around April 17-22 at ~4-6% but has since settled in the 0-2% range. The strategies are correctly armed; the entry gate hasn't fired since activation because the market hasn't produced the setup they need. Session_Continuation documents "Gate fires ~2x/month historically (last trigger: 2026-03-16)." This matches the armed-but-waiting story.

### 5.2 — Non-crypto book health

Last 30 days: **804 closed trades, +$141,471 P&L, +$175.96 avg/trade, 49.0% WR.**

Unrealized P&L on 84 open positions: +$6,163. Non-crypto book is healthy and growing. The live performance validates the equity/ETF side of the pipeline.

### 5.3 — Counterfactual: what if we loosened gates and activated 10 crypto strategies?

From Phase 2 data, strategies currently being rejected at activation:
- 15 at net return -0.6% to -0.9%
- 12 at Sharpe 0.46, would enter at -1.1% net return in test
- 11 at Sharpe 0.23 (well below even the DEMO floor of 0.3)
- 10 at RPT 0.945% on 3-trade samples (tiny N, small gross)

If these 10 strategies were activated in their current form, the WF test window predicts **net-negative P&L across every one of them in the 2024-2026 window.** Even on DEMO, the 30-day projection would be an unrealised drawdown, not capital gain. More importantly — every one of those failed WF tests was scored honestly (MC bootstrap OK, heavy-tail calibrated, consistency-checked) and still landed at net-negative. Loosening the activation gate further accepts strategies that the downstream WF path has already said lose money.

The only honest path to more crypto activation is to **run templates that generate more gross/trade** — not to lower the bar.

---

## Phase 6 — Verdict

**(a) HONEST OUTPUT: dominant explanation for this specific market/cost environment.**
The 4 active + 0 new activation pattern is what you get when:
1. Binance-style trend templates run on eToro cost reality (2.2-3% round trip)
2. BTC is above SMA(50) but 20d momentum is only 2-5% (ranging_low_vol by our thresholds)
3. The pipeline honestly reports "edge doesn't cover cost" in a regime where it structurally can't

**(c) LIBRARY DESIGN: meaningful secondary driver.**
The 76-template crypto library contains ≥ 28 templates (all `Crypto Hourly *` + many 4h/mean-reversion) whose economic ceiling on eToro alts cannot produce the gross/trade required to clear even a bypass-adjusted cost floor. These templates propose, burn WF compute, fail, and re-propose. Every cycle. They are **library-design artefacts** calibrated implicitly against cheap-venue costs (Binance ≈ 0.2% round-trip).

**(d) REGIME MISMATCH: minor third driver.**
`detect_crypto_regime`'s 3% 20d threshold is hit by a tiny margin consistently. Would a 2% threshold change things? Marginally — it would widen the template pool by ~5 trend templates per cycle, but those would still have to clear the activation gate where the RPT and net-return floors remain. Regime-gate relaxation alone would not produce activations without addressing (c).

**(b) STRUCTURAL BUG: no hard bug, one semantic drift found.**
- `total_return` in `BacktestResults` IS correctly net of costs (comment at `strategy_engine.py:3306` is accurate).
- The RPT gate at `portfolio_manager.py:1307` uses this net value consistently.
- **Semantic drift:** `min_return_per_trade` was derived in Session_Continuation as a **gross-edge floor** ("round_trip_cost + 50bps edge") but is applied against a **net-per-trade metric**. Net + cost-per-trade produces an implicit 4%+ gross-per-trade demand, which is 2× the original design intent.
- This is not a crash bug or a cost-double-count. It's a mis-calibration between the threshold's derivation rationale and its applied units.

**Ranking: (a) > (c) > (d) >> (b).**

Is there a math bug anywhere in the pipeline? — **No crash or double-count.** One semantic drift on RPT unit (src/strategy/portfolio_manager.py:1307 vs Session_Continuation Sprint 1 F3 derivation).

Is the crypto template library fundamentally mis-calibrated for eToro costs? — **Yes, for a ≥28-template subset** (all Hourly/4H short-hold/mean-reversion). These cannot produce enough gross/trade to cover 2.20-2.96% round-trip.

Is the crypto regime detector gating too tightly? — **Slightly.** 3% / 5% AND-gate misses the BTC uptrend by 70bps. Not the dominant driver; secondary at best.

Is 0 crypto activations HONEST OUTPUT given our broker + regime? — **Yes.** The pipeline is working as designed: templates that cannot clear 2.20-2.96% cost in a 5-10% 20d BTC move regime will correctly fail. The 4 BTC Follower Daily activations via F2 are the honest "yes" case; everything else is honest "no".

---

## Single highest-leverage recommendation

**Prune the library of structurally uneconomic templates, don't loosen any gate.**

The 76-template crypto library contains at minimum 20-28 templates that are mathematically incapable of clearing eToro's cost floor on alts — all of the `Crypto Hourly *` family (12+ templates) plus 4H mean-reversion + short-hold daily mean-reversion. These templates:

- Consume proposer slots and WF compute every cycle
- Contribute to the "118/129 rejected" funnel noise
- Cannot produce a positive outcome regardless of regime, gate calibration, or market direction
- Were designed implicitly against Binance-style 0.1-0.2% per-side costs

Concretely: remove every 1h/4h crypto template whose `min_return_per_trade_design` < 2× per-symbol round-trip cost. That's somewhere between 20 and 30 templates — approximately 1/3 of the crypto library. The remaining ~50 templates are the ones with any realistic chance of activating under eToro cost reality.

This is higher leverage than any gate tune because:
- Gate tuning cannot fix templates whose backtest gross/trade is structurally sub-cost
- Every cycle those 28 templates WILL fail — they already do, we just haven't pruned them
- Fewer proposals per cycle → same cycle time → cleaner funnel → clearer signal when a new template has edge
- No risk of activating bad strategies (we're removing them, not loosening)

**Second-highest leverage** (follow-up, not first-choice): fix the RPT semantic drift by either (A) relabeling `min_return_per_trade` as `min_net_return_per_trade` and adjusting config values to reflect pure net-edge requirements (1.0% for BTC, 1.5% for alts), OR (B) comparing `(total_return + transaction_costs_pct) / total_trades` (gross-per-trade) against the existing 1.8-3.0% floors. Both are 30-min fixes but neither activates the templates already rejected under Ex-post 730d, Sharpe, or net-return-negative gates. So this is a *cleanliness* fix, not a throughput fix.

**Not recommended** (despite tempting): Sprint 4's Binance historical data adapter. Longer training windows don't change eToro cost reality at runtime. More data will produce better backtest Sharpe but will not produce higher gross/trade. The gate rejections are cost-bound, not data-bound.

---

*Presenting findings. Awaiting direction before any code change.*


---

## Follow-up investigation (2026-05-03, user prompt #2)

User asked: "Revisit cost calculations. Are we doing something wrong? Is MC bootstrap correct?"

Worked backwards from the live cycle log for BTC Follower 4H ETH. Three concrete bugs found — two in the activation path, one in config plumbing.

### Bug #1 — `per_symbol` cost override is never read by the backtest engine

**Code path:** `src/strategy/strategy_engine.py:1247-1249`

```python
commission = ac_costs.get('commission_percent', tx_costs.get('commission_percent', 0.0))
slippage_pct_raw = ac_costs.get('slippage_percent', tx_costs.get('slippage_percent', 0.0003))
```

`ac_costs` is `tx.get('per_asset_class', {}).get(asset_class, {})`. **`tx.get('per_symbol', ...)` is not consulted.** Only `cost_model.round_trip_cost_pct` (observability-only helper) reads `per_symbol`.

**Impact, verified via log numbers** (`cycle_1777803232` — Crypto BTC Follower 4H ETH LONG):

| Cost component | Config value (ETH per_symbol) | Config value (crypto per_asset_class) | What backtest used |
|---|---|---|---|
| Commission per side | 1.00% | 1.00% | 1.00% |
| Spread per side | 0.05% | 0.38% | **0.38%** ← wrong |
| Slippage per side | 0.05% | 0.10% | **0.10%** ← wrong |
| Round-trip total | 2.20% | 2.96% | **2.96%** |

Per-log math: 6 trades × 2 sides × $11,956 avg size × 0.38% spread = $545.18 spread cost. That matches the log exactly ("Spread cost: $545.18"). If the per_symbol override had been read, spread would have been $71.74 — an $473 dollar discrepancy on this single backtest alone.

BTC has the same issue — backtests BTC at 2.96% round-trip instead of the configured 2.18%.

**Consequence:** ETH and BTC strategies systematically over-estimate costs by ~0.76%/round-trip. A 6-trade strategy on BTC/ETH shows net return ~4.56% lower than it should.

### Bug #2 — RPT gate unit mismatch (THE dominant blocker)

**Code path:** `src/strategy/portfolio_manager.py:1307`

```python
return_per_trade = backtest_results.total_return / backtest_results.total_trades
if return_per_trade < min_return_per_trade:  # config: 0.030 for crypto_4h
    reason = "Return/trade X% < 1.8% min ..."
```

**`backtest_results.total_return`** is from vectorbt `portfolio.total_return()`, which is `(final_value - init_cash) / init_cash` — a fraction of init_cash, not a per-trade-position return.

**Position sizing in backtest** (from same log): volatility-based, avg $11,956 per trade — i.e. 12% of init_cash.

**Arithmetic walk-through** (all numbers from real log):

| Metric | Value | Derivation |
|---|---|---|
| Gross total_return | 7.11% | vectorbt on $100K init |
| Net total_return | 4.99% | after $2,123 cost deduction |
| `return_per_trade` (as gate reads it) | 0.832% | 4.99% / 6 — per-trade % of init_cash |
| Avg position size | $11,956 | log: "Mean size" |
| **Per-position net return per trade** | **6.96%** | 4.99% / 6 / 0.12 |
| Per-position gross return per trade | 9.91% | 7.11% / 6 / 0.12 |
| Round-trip cost per position (crypto AC) | 2.96% | 2 × (1% + 0.38% + 0.1%) |
| **Real edge_ratio (gross/cost, per position)** | **3.35** | 9.91% / 2.96% |

**The threshold (3.0%) was derived in Sprint 1 F3** as:

> "round_trip_cost (2.96%) + 50bps minimum edge = 3.5%. Anything below this is noise after costs."

The derivation is per-position: cost_per_position + edge_per_position = threshold_per_position. But the gate applies it against a per-init_cash-per-trade metric. Effective per-position demand becomes `threshold / position_size_pct` = 1.8% / 12% = **15.06% per position** — 5.1× the real round-trip cost.

A strategy with 9.91% gross/position and 6.96% net/position (both comfortably above cost) is rejected as if its per-position net were only 0.83%.

**Reproducibility:** `scripts/investigate_2026_05_03_cost_math.py` (at repo root) reproduces the entire calculation from the log numbers. No src/ imports; pure math against the observed production values.

### Bug #3 — `cost_model.edge_ratio` same unit mismatch (observability-only)

**Code path:** `src/strategy/cost_model.py:231-237`

```python
gross_per_trade = gross_return / n_trades  # fraction of init_cash
return gross_per_trade / rtc, gross_per_trade, rtc  # rtc = fraction of position
```

Same shape of bug as #2. The log line `edge_ratio=0.54` is wrong by the same factor. Real per-position edge_ratio is 3.35 for this strategy.

This is observability-only (no gate), but it's misleading operators looking at the Data Page "edge_ratio" number as a health signal. Every strategy with fractional position sizing under-reports edge by ~5-10×.

### Monte Carlo bootstrap — sanity check

**Code path:** `src/strategy/strategy_proposer.py:2002-2103`

MC bootstrap uses `test_results.trades` which is vectorbt's `records_readable` DataFrame. Its `Return` column is defined by vectorbt as `PnL / (size × entry_price)` — **per-position return**. ([vectorbt GitHub discussion #264](https://github.com/polakowo/vectorbt/discussions/264)). Extraction at line 2051-2055 reads `t.get('Return')`. 

Annualization factor (line 2078): `sqrt(n_trades / test_window_days × 252)` — correct.

Percentile thresholds (p5 ≥ 0 for equity, p10 ≥ −0.2 for crypto/commodity, post-S3.0c): defensible against Efron-Tibshirani 1993 heavy-tail guidance.

**MC bootstrap is mathematically correct.** It is not contributing to the mis-rejection.

### Reason-category breakdown revisited

With the RPT unit mismatch understood, the 3-day rejection reason counts break down as:

| Rejection reason | Count | Honest? |
|---|---|---|
| Net return < 0 (after costs) | 41 | **Mostly honest**, but inflated ~0.8% per strategy on BTC/ETH by Bug #1 |
| Sharpe below floor | 56 | Honest — Sharpe is unit-agnostic |
| Return/trade < RPT min | 26 | **Mostly Bug #2** — strategies with real per-position edge rejected |
| WinRate hard floor | 3 | Honest |
| Ex-post 730d Sharpe | 3 | Honest |

Roughly **30-40 of the last 3 days' rejections (~20-25% of total rejections)** are attributable to Bug #2 alone. Bug #1 additionally inflates Bug #2's effect on BTC/ETH by making net return ~0.8% lower than it should be.

### Verdict revision

The original Phase 6 verdict ranked (a) > (c) > (d) >> (b). **This is now wrong.**

After the deep dive, the correct ranking is:

**(b) STRUCTURAL BUG — dominant driver.** The RPT gate is mathematically broken for any strategy using fractional position sizing. The per_symbol cost override is silently ignored in the backtest engine. The edge_ratio observability metric is mis-calibrated. All three are in production right now.

**(a) HONEST OUTPUT — meaningful secondary.** Even after fixing (b), some strategies will still honestly fail because their per-position gross genuinely doesn't cover the per-position cost (Crypto Weekly Trend Follow at 0.005% gross/trade is not going anywhere regardless of unit fixes).

**(c) LIBRARY DESIGN — minor.** Some templates will still be structurally uneconomic on alts at 2.96% round-trip. But the number of rejected-but-actually-good strategies is larger than I originally thought.

**(d) REGIME MISMATCH — minor, unchanged.**

### Revised highest-leverage recommendation

Drop the template-pruning recommendation. **Fix the three bugs.** In order of importance:

**Fix #1 — RPT gate unit normalization** (highest leverage, affects activation count directly).

Two options of roughly equal merit:

- **Option A (recalibrate threshold in yaml):** Keep the gate math as-is. Update the yaml thresholds to reflect "per-init_cash-per-trade" semantics. New `crypto_1d / 4h / 1h` values would be ~0.2-0.5% (cost × avg_position_pct + edge margin × avg_position_pct). Header comment documents the derivation so it doesn't drift again. Smaller code change, harder to derive good values because position sizing varies per template.

- **Option B (change gate math):** Compute `per_position_return_per_trade` in `evaluate_for_activation` by dividing through by `avg_trade_value / init_cash`. Then compare against the existing 3% threshold which becomes a true per-position threshold matching Sprint 1 F3 derivation. Keeps thresholds human-readable ("per-position gross/trade floor of 3%"). Requires that `BacktestResults.avg_trade_value` or equivalent is available at activation (it's computed at strategy_engine.py:3343 but not persisted on BacktestResults; a small engine change to add the field).

Recommend Option B. It's the proper fix — keeps thresholds aligned with their original trading-meaning, single code change, no yaml recalibration.

**Fix #2 — per_symbol cost override honoured in backtest engine.**

In `src/strategy/strategy_engine.py:1247-1249`, consult `tx['per_symbol'][SYMBOL]` before falling back to `per_asset_class`. Match the precedence order documented in `cost_model.py:159-163` (per_symbol > per_asset_class > global). Small change, maybe 10 lines. Removes the 0.76% phantom cost on BTC and ETH strategies.

**Fix #3 — cost_model.edge_ratio same correction.**

Once Fix #1 lands, use the same gross-per-position approach in cost_model. Single-line change if BacktestResults carries avg_trade_value.

### Estimated impact

Re-running cycle_1777803232 after all three fixes:

- `Crypto BTC Follower 4H ETH LONG` (family_cross_validated=False in that cycle): per-position net 6.96% — passes RPT after fix → **activated**
- `Crypto Weekly Trend Follow ETH LONG` (gross 0.0%, 10 trades): still fails — genuinely no edge
- `Crypto SMA Reversion DOT`: ex-post 730d −9.6% over 19 trades — still fails, genuinely broken over 2y
- `Sector Rotation XLF`: Sharpe 0.17 — still fails, not crypto-related
- `Crypto EMA Ribbon BTC/ETH, Crypto SMA Reversion LINK, Crypto Keltner Range Trade LINK`: negative Sharpe — still fail honestly

**Expected: 1-2 additional activations per cycle (BTC Follower 4H ETH + any similar-profile strategy that's currently being rejected on RPT).** The other rejections are independent of the bugs and stay correct.

This is consistent with the user's instinct. Zero activations was NOT the right number for the regime + library we actually have. It was the buggy number.
