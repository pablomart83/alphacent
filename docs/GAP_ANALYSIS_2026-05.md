# AlphaCent — Gap Analysis vs Industry Best Practice
**As of 2026-05-17 · companion to ALPHACENT_SYSTEM_AUDIT_2026-05.md**

> Benchmark: systematic retail/prop trading firm at $500K AUM, 50–100 positions, daily/4H/1H strategies, eToro CFD execution. Compared against AQR/Man Group/Winton public methodology, Carver, Ernie Chan, Rishi Narang, López de Prado, and standard quant practitioner convention.

> Excluded by design: HPC/co-location/microsecond latency, institutional prime brokerage features, regulatory compliance beyond basic risk controls, features requiring data we don't have access to.

---

## 0. How to read this

Every gap has:
- **ID** (G-01 …)
- **Component** affected
- **Current state** — what AlphaCent does today, with file:line refs
- **Industry standard** — what best practice looks like at this scale
- **Impact** — High / Medium / Low (on P&L, risk, or data quality)
- **Effort** — High / Medium / Low
- **Priority** — P1 (close now) / P2 (next sprint) / P3 (future)
- **Proposed fix** — specific, implementable, no hand-waving

Priority is set by impact × effort. P1 = high impact and ≤ medium effort. P3 = lower impact or research-heavy work.

The gaps are grouped by component cluster. The end of this document has a **prioritised P1/P2 fix list** for sprint planning.

---

## 1. Walk-Forward Robustness

### G-01 — Walk-forward bypass paths still admit regime-luck for LONG
- **Component**: Strategy proposer / WF validation
- **Current state**: Three pass paths (`strategy_proposer.py:2400-2425`). Primary: both train and test ≥ min_sharpe. Test-dominant: `train_S ≥ −0.1 AND test_S ≥ min_sharpe`. Excellent-OOS: `train_S ≥ −0.3 AND test_S ≥ 2×min_sharpe AND test_trades ≥ 5 AND (test_S − train_S) ≤ 1.5`. The `≤ 1.5` consistency gate is on the excellent-OOS path only — test-dominant lets `train_S=−0.1, test_S=1.4` through unfiltered.
- **Industry standard**: Combinatorial Purged Cross-Validation (López de Prado 2018) with embargoed test windows AND a consistency check (`|train_S − test_S| / sqrt(min(train_S, test_S))` < 1) on every pass path. AQR's published methodology requires consistent edge across 4+ rolling windows.
- **Impact**: **High** — admits regime-lucky LONG strategies during trending markets. Audit shows 20 strategies with regime-luck flag in last 7 days (Intel A4).
- **Effort**: **Low** — extend the consistency gate to test-dominant path; one if-condition change.
- **Priority**: **P1**.
- **Proposed fix**: In `strategy_proposer.py:2406-2412`, add `AND (tes - ts) <= 1.5` to the test-dominant condition. For full CPCV, extend `walk_forward_validate_rolling` to support embargoed test windows (don't let train and test bars share an autocorrelation horizon — typically 5 days for daily bars). 1-day embargo at the train/test boundary is a 5-line change.

### G-02 — No deflated Sharpe ratio
- **Component**: WF validation, activation
- **Current state**: Sharpe is reported as-is. No correction for the number of trials. With 200 proposals/cycle × 3 schedules/day × 30 days = 18,000 strategies tested per month, the multiple-comparison problem is real — a 2-sigma Sharpe by chance happens >100× per month.
- **Industry standard**: Bailey & López de Prado (2014) Deflated Sharpe Ratio. Adjusts the observed Sharpe for sample length, skewness, kurtosis, AND number of trials. Standard at AQR, Two Sigma, Renaissance.
- **Impact**: **High** — without DSR, ~2-3% of activated strategies are statistically indistinguishable from chance, polluting the paper book.
- **Effort**: **Medium** — Bailey/López de Prado formula is ~30 lines of Python. Hardest part is tracking the trial count per (template, asset class).
- **Priority**: **P1**.
- **Proposed fix**: Add `compute_deflated_sharpe(returns, n_trials, sample_length)` to `bootstrap_service.py`. Apply at the activation gate (`portfolio_manager.evaluate_for_activation`) AFTER the existing tier check. Reject if `DSR < 0.95` (95% confidence the strategy beat the multiple-comparison-adjusted threshold). Track `n_trials` per (template, asset_class) in a new `trial_counts` table updated by `track_proposals`.

### G-03 — Monte Carlo bootstrap uses simple resampling, ignores serial correlation
- **Component**: WF / MC bootstrap
- **Current state**: `numpy.random.choice(arr, size=len(arr), replace=True)` (`strategy_proposer.py:2236`). Standard IID bootstrap.
- **Industry standard**: Block bootstrap (Politis & Romano 1994) for return series with autocorrelation. Standard at Winton, AHL, Aspect Capital. Block size = `1.5 × ⌊N^(1/3)⌋` for daily bars.
- **Impact**: **Medium** — IID bootstrap underestimates p5 variance for strategies with momentum/mean-reversion autocorrelation; the actual lower tail is wider than simulated. Trend-following strategies are most affected.
- **Effort**: **Low** — 20-line change in MC loop.
- **Priority**: **P2**.
- **Proposed fix**: Replace `np.random.choice` with circular block bootstrap. Block size 5 for daily, 10 for 4h, 24 for 1h.

### G-04 — Pass-2 relaxed admits anything when validated < 10
- **Component**: WF
- **Current state**: When `len(validated) < 10`, a relaxed path admits strategies with `train_S > 0.1 AND test_S > 0.1` (`strategy_proposer.py:2702-2727`). MC-bootstrap-rejected strategies are correctly excluded since the May 2 fix.
- **Industry standard**: Never relax statistical bars to hit a count target. If you can't find 10 valid strategies in this regime, propose fewer or wait.
- **Impact**: **Medium** — Pass-2 admits ~3-5 strategies per cycle when proposal pool is thin. These are the lowest-quality validated strategies, and they're reaching paper trading.
- **Effort**: **Low** — remove the path.
- **Priority**: **P2**.
- **Proposed fix**: Remove Pass-2 relaxed entirely. Acceptable downside: cycles with thin pools just produce fewer proposals — operator can lower conviction threshold or wait.

---

## 2. Position Sizing & Volatility Targeting

### G-05 — Vol scaling target is single global value (16%)
- **Component**: Position sizing
- **Current state**: `TARGET_VOL = 0.16` hardcoded (`risk_manager.py:802`). One target across all asset classes and strategy types.
- **Industry standard**: Carver (2015 *Systematic Trading*) recommends per-strategy-type vol targets — trend-followers run at 12-15% target vol, mean-reversion at 8-12%, options-replication strategies at 6-10%. Same target across types over-allocates to high-vol strategies.
- **Impact**: **Medium** — current portfolio is over-allocated to mean-reversion strategies (which have higher Sharpe but lower target vol in best practice). Realised portfolio vol is ~12% (lower than target), suggesting under-deployment.
- **Effort**: **Medium** — define per-strategy-type vol targets, plumb through `_detect_strategy_type` to the sizing function.
- **Priority**: **P2**.
- **Proposed fix**: Add `STRATEGY_VOL_TARGETS = {trend_following: 0.15, momentum: 0.14, mean_reversion: 0.10, breakout: 0.13, volatility: 0.12}` to `risk_manager.py`. Use strategy_type to select target. Document the rationale in the conviction scorer comment so the choice is auditable.

### G-06 — Paper flat sizing leaves alpha on the table
- **Component**: Position sizing
- **Current state**: Paper mode bypasses all 11 sizing steps and uses flat $5,000 (`risk_manager.py:776+`). Rationale: "every paper strategy gets equal data quality."
- **Industry standard**: Two camps. (a) Quant funds run identical sizing in paper and live (Carver, Chan). (b) Some firms run flat paper for backtesting + statistically-sized paper for the rolling Sharpe/WR estimation that drives live promotion.
- **Impact**: **Medium** — flat paper sizing means the paper Sharpe and live Sharpe are not directly comparable. The graduation gate's `qualification_ratio = paper_S / wf_S ≥ 0.6` is comparing a Sharpe computed on flat $5K positions to a WF Sharpe computed on a vol-scaled distribution, which is structurally biased.
- **Effort**: **Medium** — easy to remove the bypass. Hard part: deciding whether to do it.
- **Priority**: **P2** — needs research before implementation.
- **Proposed fix**: Run the full sizing pipeline in paper but cap symbol exposure at 1% (instead of 5%) to keep paper book diverse. Recompute the qualification_ratio threshold from historical paper-trade data after one full cycle.

### G-07 — Symbol concentration cap is per-symbol, not cumulative across correlated symbols
- **Component**: Position sizing
- **Current state**: 5% per symbol cap (`risk_manager.py` Step 6). NVDA and AMZN both at 7.43% of equity simultaneously is a known issue (Session_Continuation: "Batch 3 fix pending").
- **Industry standard**: Sector cap (already 30%) + correlation-aware cap. AQR uses `max_exposure = min(symbol_cap, sector_cap, sum_of_correlations × 1.5%)`.
- **Impact**: **High** — when SPY tanks, NVDA and AMZN move together. Two 7%-of-equity positions in correlated mega-caps is one 14% bet.
- **Effort**: **Medium** — pull `correlation_analyzer.get_correlation` into the sizing function, cap by correlation cluster.
- **Priority**: **P1**.
- **Proposed fix**: In `risk_manager.calculate_position_size` Step 6, group existing positions by correlation cluster (correlation > 0.7). Cap each cluster at 8% of equity (instead of 5% per symbol). Re-use the existing `correlation_analyzer` cache.

### G-08 — Conviction-tier sizing multipliers are conservative and untested at scale
- **Component**: Position sizing
- **Current state**: score ≥ 80 → ×1.30; ≥ 75 → ×1.15 (Step 10c). Sample size: 48 trades in upper buckets over 14 days (audit comment).
- **Industry standard**: Kelly criterion or fractional Kelly (5-25%) on the per-bucket expected P&L. With 48 trades the per-bucket Sharpe estimate has wide CI; current multipliers are likely too conservative.
- **Impact**: **Low** — not leaving large alpha on the table; conservative is correct early.
- **Effort**: **Low** — once data accumulates (3-4 weeks), recompute multipliers from per-bucket realised expectancy.
- **Priority**: **P3**.
- **Proposed fix**: Wait until 200+ trades per bucket, then refit multipliers using Kelly on the empirical bucket-level expectancy. Keep current values until then.

---

## 3. Correlation Management

### G-09 — Correlation is not consulted at proposal time
- **Component**: Proposer / correlation
- **Current state**: Correlation is checked at sizing time and activation time, never at proposal time. The `similarity_detection` block in YAML is gated off (`enabled: false`).
- **Industry standard**: Diversification at the proposal stage is cheaper than fixing it at sizing time. Standard practice (Narang, *Inside the Black Box*) is to maintain a per-strategy correlation matrix and reject new proposals whose backtest returns correlate > 0.6 with an active strategy.
- **Impact**: **High** — current portfolio has many "different rules, same bet" overlaps. Ranger Trader Trend on NVDA and 4H EMA Ribbon on NVDA are 0.85+ correlated despite being different templates.
- **Effort**: **Medium** — extend `_match_templates_to_symbols` to dedupe by simulated-returns correlation against active strategies.
- **Priority**: **P1**.
- **Proposed fix**: After WF validation, compute backtest-returns correlation between each new validated strategy and active strategies. Reject (or de-rank) any new strategy with `correlation > 0.65` to an existing active. Add a `signal_decisions` row with stage `correlation_dedup`.

### G-10 — `position_management.correlation_adjustment.*` is dead config
- **Component**: Risk / config integrity
- **Current state**: `position_management.correlation_adjustment.{enabled, threshold, reduction_factor}` exposed in Settings UI but **not consumed**. `risk_manager.py` hardcodes 0.7 / 0.5×.
- **Industry standard**: Config exposed in UI must be wired. Settings shouldn't lie.
- **Impact**: **Medium** — operator changes Settings, system doesn't honour them. Trust degradation.
- **Effort**: **Low** — 5-line change to read YAML in `calculate_correlation_adjusted_size`.
- **Priority**: **P1** (cheap, high trust impact).
- **Proposed fix**: In `risk_manager.calculate_correlation_adjusted_size`, read YAML `position_management.correlation_adjustment.{threshold, reduction_factor}` instead of hardcoding 0.7 / 0.5. Default to current values if YAML missing.

### G-11 — No correlation matrix maintained in real time
- **Component**: Risk
- **Current state**: Correlation is computed on demand (7-day cache in `src/utils/correlation_analyzer.py`). No portfolio-level correlation matrix.
- **Industry standard**: Daily-updated correlation matrix across all open positions. Used for risk dashboards (Carver Chapter 12), VaR computation, hedge selection.
- **Impact**: **Medium** — limits portfolio analytics; can't compute proper portfolio VaR; can't detect concentration in correlated clusters in real time.
- **Effort**: **Medium** — daily background job to update an `active_correlation_matrix` table; consume in `risk_manager.calculate_portfolio_metrics` and the Guard/Risk dashboard.
- **Priority**: **P2**.
- **Proposed fix**: Add a `daily_correlation_matrix` table updated by `MonitoringService` daily. Schema: `(symbol_a, symbol_b, correlation, lookback_days, computed_at)`. Surface in Guard tab with a heatmap.

### G-12 — Two `CorrelationAnalyzer` classes in the codebase
- **Component**: Code organisation
- **Current state**: `src/strategy/correlation_analyzer.py` (strategy-level multi-dim) and `src/utils/correlation_analyzer.py` (symbol-pair). Same class name. Different responsibilities.
- **Industry standard**: One canonical class with methods for both use cases.
- **Impact**: **Low** — but creates confusion.
- **Effort**: **Low**.
- **Priority**: **P3**.
- **Proposed fix**: Rename to `StrategyCorrelationAnalyzer` and `SymbolCorrelationAnalyzer`. No behaviour change.

---

## 4. Regime Detection

### G-13 — Regime detection is rule-based on simple thresholds
- **Component**: Market analyzer
- **Current state**: `detect_sub_regime` (`market_analyzer.py:1230+`) classifies regime by `trend_score`, `avg_change_20d`, `avg_change_50d`, `avg_atr_ratio`. Hardcoded thresholds (e.g. `trend_score > 0.04 AND avg_change_20d > 0.03 AND avg_change_50d > 0.05` → strong uptrend).
- **Industry standard**: Hidden Markov Models (HMM) on a small set of macro features (returns, vol, term structure, credit spreads). Standard at Two Sigma, AQR, Winton. Or, if simpler, a multi-factor regime classifier (Ang & Bekaert 2004) using vol + term + dividend yield + momentum.
- **Impact**: **Medium** — current rule-based regime flips noisily on the boundary cases (trend_score 0.04 ↔ 0.039). HMM regimes are more stable and account for uncertainty.
- **Effort**: **High** — train HMM offline, add `hmmlearn` dependency, integrate into the market_analyzer with a fall-back to rule-based.
- **Priority**: **P3** — current regime classification works, just noisier than necessary.
- **Proposed fix**: Add `MarketStatisticsAnalyzer.detect_regime_hmm()` using a 3-state HMM trained on (SPY 20d return, VIX level, ATR/price). Use as a tiebreaker for borderline rule-based classifications.

### G-14 — Regime detection inconsistency between market_analyzer and proposer
- **Component**: Regime
- **Current state**: `market_analyzer.detect_sub_regime` and the proposer's regime gate can disagree (steering file: "Regime classification two-tier inconsistency"). When proposer says ranging and market_analyzer says trending_up, the watchlist filter and the conviction scorer use different regime keys.
- **Industry standard**: One source of truth.
- **Impact**: **Medium** — strategies get scored with regime A but proposed against regime B's template pool.
- **Effort**: **Low** — collapse to a single call site; cache result for cycle duration.
- **Priority**: **P2**.
- **Proposed fix**: Compute regime once at cycle start, store on `cycle_run.metadata`, pass to all downstream callers.

### G-15 — Crypto regime is detected against BTC/ETH only
- **Component**: Regime
- **Current state**: `detect_crypto_regime` uses BTC and ETH (`market_analyzer.py:1433+`). Altcoin regimes can diverge significantly (e.g. SOL leading a rally while BTC consolidates).
- **Industry standard**: Per-coin regime, or at least a broader basket (top-10 altcoins).
- **Impact**: **Low** — altcoin trading is small fraction of book.
- **Effort**: **Medium**.
- **Priority**: **P3**.

---

## 5. Strategy Retirement

### G-16 — Decay score is sound but recovery rate is too slow
- **Component**: Decay
- **Current state**: Decay score 10→0, `+0.5` recovery per check when no penalties. With hourly cycle = 12 hours to recover 6 points.
- **Industry standard**: Decay should match the timeframe of the strategy. A 1d strategy losing in a 3-day regime shift shouldn't be retired before the regime can stabilise. 1d strategies should recover at +1.0/day, 4h at +0.5/day, 1h at +0.25/day.
- **Impact**: **Low**.
- **Effort**: **Low**.
- **Priority**: **P3**.

### G-17 — `pending_retirement` keeps positions alive too long
- **Component**: Retirement
- **Current state**: `pending_retirement=True` waits for SL/TP to close positions. Zombie exit catches flat ±2% / 5+ days but is operator-review only.
- **Industry standard**: Strict time-stop on retired strategies. After N days post-retirement, force-close at market (not via SL).
- **Impact**: **Medium** — capital tied up in retired strategies is dead capital.
- **Effort**: **Low**.
- **Priority**: **P2**.
- **Proposed fix**: Add `pending_retirement_force_close_days = 14` to YAML. After 14 days in pending_retirement, force-close all positions regardless of P&L.

### G-18 — Health and decay are independent scores, can disagree
- **Component**: Retirement
- **Current state**: Decay (10→0) and health (5→0) run separately, write different metadata fields. They can produce contradictory verdicts (decay=0 but health=4, or decay=8 and health=0).
- **Industry standard**: Single composite "kill score" with documented weights.
- **Impact**: **Low**.
- **Effort**: **Medium**.
- **Priority**: **P3**.

---

## 6. Execution Quality

### G-19 — No real slippage model for eToro CFDs
- **Component**: Execution / cost model
- **Current state**: Static `slippage_percent` per asset class (2-10 bps). No price-impact function, no time-of-day adjustment, no √volume scaling.
- **Industry standard**: Almgren-Chriss optimal execution, or at minimum a market-impact estimate based on (ADV, spread, time of day). Even at retail scale, eToro CFD fills around news show 5-10× the static slippage estimate.
- **Impact**: **High** — backtest Sharpes are inflated by ~0.1-0.3 for high-frequency strategies. Live performance lag is partly explained by this.
- **Effort**: **Medium-High** — fit a slippage model from `trade_journal.slippage` data. Model: `slippage = base + (size / ADV)^0.6 × spread × scaling`.
- **Priority**: **P1**.
- **Proposed fix**: Add `src/strategy/slippage_model.py` with `estimate_slippage(symbol, size, time_of_day) → bps`. Train monthly on `trade_journal.slippage`. Use in backtest cost deduction (replace static `slippage_percent`). Surface realised vs modelled slippage in Research → Execution tab.

### G-20 — No fill quality monitoring (TCA)
- **Component**: Execution
- **Current state**: `slippage` is captured per fill but not aggregated to a TCA report. Research → Execution → TCA tab exists but only shows raw slippage stats.
- **Industry standard**: Implementation Shortfall, VWAP slippage, arrival-price comparison. Standard at any prop firm > $10M AUM.
- **Impact**: **Medium** — without TCA we can't prove eToro fill quality is acceptable; can't detect adverse selection by execution venue.
- **Effort**: **Medium**.
- **Priority**: **P2**.
- **Proposed fix**: Extend `monitoring/execution_quality.py` to compute IS (decision price → fill price) per order. Add `realised_slippage_bps`, `model_slippage_bps`, `excess_bps` columns to a daily `execution_quality_daily` table.

### G-21 — Optimistic position write may produce ghost positions
- **Component**: Execution
- **Current state**: Order submission creates a position row with `etoro_position_id=pending_<order_id>` (`order_executor.py`). Fill detection updates to real ID. If eToro rejects after submit, the placeholder position lingers until the cleanup job sees `closed_at IS NULL AND etoro_position_id LIKE 'pending_%'` past 1h.
- **Industry standard**: State machine for orders: `submitting → submitted → fill_pending → filled` with explicit transitions. Position row only created on fill confirmation.
- **Impact**: **Medium** — has caused duplicate positions in race conditions.
- **Effort**: **Medium**.
- **Priority**: **P2**.
- **Proposed fix**: Add an explicit `OrderState` enum and transition rules in `OrderExecutor`. Don't create position row until fill confirmation arrives.

### G-22 — Entry order 82% FAILED rate (cosmetic, but loud)
- **Component**: Execution
- **Current state**: Market-closed deferrals are written as FAILED then re-fired each cycle (Session_Continuation: "Batch 2 fix pending"). Bloats the orders table and Intel B1 fires constantly.
- **Industry standard**: DEFERRED state (not FAILED) for market-closed.
- **Impact**: **Low** — purely cosmetic, but pollutes signal_decisions analytics.
- **Effort**: **Low**.
- **Priority**: **P2**.
- **Proposed fix**: Add `OrderStatus.DEFERRED`. Write deferrals as DEFERRED (not FAILED). Re-fire cycle reads DEFERRED and submits when market opens.

---

## 7. Portfolio-Level Risk

### G-23 — No real-time portfolio VaR
- **Component**: Risk
- **Current state**: VaR check disabled (`portfolio_var.enabled: false`). Computed VaR was 97.97% — model artefact from young equity curve.
- **Industry standard**: Daily portfolio VaR using historical simulation or Monte Carlo on 252-day return history. Limit at 5-10% 1-day 95% VaR.
- **Impact**: **High** — without VaR, no portfolio-level risk control beyond heat cap (which is a stop-loss-based proxy).
- **Effort**: **Medium** — historical simulation on the equity curve plus Cornish-Fisher correction for skewness/kurtosis. Re-enable once 90+ days of equity history exist.
- **Priority**: **P2** (90-day history needed first).
- **Proposed fix**: After 90 days, re-enable VaR with historical simulation method. Limit: 5% 1-day 95% VaR. Compute on equity curve from `equity_snapshots`. Surface in Guard → Risk tab. As an interim, use 30-day Parkinson estimator on closing prices to bootstrap VaR until equity curve is long enough.

### G-24 — Heat cap uses 6% SL proxy for all positions
- **Component**: Risk
- **Current state**: Heat = `Σ(position_value × 0.06)` (`risk_manager.py:858`). Crypto positions have 8% SL but counted as 6%; forex 2% but counted as 6%.
- **Industry standard**: Per-position actual SL distance.
- **Impact**: **Medium** — heat is overestimated for stocks/forex (no harm), underestimated for crypto (potential overexposure).
- **Effort**: **Low**.
- **Priority**: **P2**.
- **Proposed fix**: Change to `Σ(position_value × actual_sl_pct)` where `actual_sl_pct = abs(entry_price − stop_loss) / entry_price`.

### G-25 — Drawdown sizing kicks in at 5%/10% — too generous
- **Component**: Risk
- **Current state**: 30-day drawdown > 5% → ×0.5; > 10% → ×0.25.
- **Industry standard**: Carver Chapter 12 — 3% ⇒ ×0.7, 5% ⇒ ×0.5, 7% ⇒ ×0.25, 10% ⇒ stop. Tighter ladder.
- **Impact**: **Medium** — at 6% drawdown we're still sizing at 50%, while best practice would have us at ~30%.
- **Effort**: **Low**.
- **Priority**: **P3**.

### G-26 — Margin / leverage tracking absent
- **Component**: Risk
- **Current state**: eToro's CFD margin requirements are not tracked in real time. The `equity` field is just `balance + unrealized_pnl` — doesn't account for posted margin.
- **Industry standard**: Available margin tracked separately from equity. Pre-trade check: `(used_margin + new_margin) / equity ≤ 0.8`.
- **Impact**: **Medium** — CFD margin call risk not surfaced.
- **Effort**: **Medium** — eToro public API exposes margin via `account/info`.
- **Priority**: **P2**.

---

## 8. SHORT Pipeline

### G-27 — SHORT side WF tightening is correct, but conviction floor is not directionally re-tested
- **Component**: Conviction / SHORT
- **Current state**: SHORT min_sharpe +0.3 in WF (`strategy_proposer.py:2371`). Conviction fairness fixes May 15 (low-freq trade denominator, asset class denominator, regime fit exemption). All sound.
- **Industry standard**: After every fairness fix, re-test the activation threshold against historical SHORT-only data. The current `alpha_edge.min_conviction_score = 70` is calibrated for LONG-heavy data.
- **Impact**: **Medium** — there's some risk the May 15 fairness fixes pushed marginal SHORTs over 70 that wouldn't have made it pre-fix; need to monitor first paper-trade outcomes.
- **Effort**: **Low** — re-bin SHORT strategies by post-fix conviction score over 30 days, compare to live PnL.
- **Priority**: **P2**.
- **Proposed fix**: Build a post-fix SHORT-only Sharpe distribution from the next 30-day paper window and recalibrate `alpha_edge.min_conviction_score` per direction (e.g. SHORT 72, LONG 70).

### G-28 — Generic SHORT suppression in trending_up has no exemption mechanism documented in code
- **Component**: SHORT
- **Current state**: Generic shorts are suppressed in trending_up by the proposer's regime gate; uptrend-specific SHORTs (Exhaustion Gap, BB Squeeze Reversal, MACD Divergence, Parabolic Move, Volume Climax, EMA Rejection) are exempted because their `market_regimes` metadata explicitly includes a `trending_up*` variant. The exemption is implicit in the regime-filter logic — there's no `is_uptrend_short_template()` helper, just a metadata check.
- **Industry standard**: Explicit, named, tested helper.
- **Impact**: **Low** — works correctly, just hard to audit.
- **Effort**: **Low**.
- **Priority**: **P3**.

---

## 9. Graduation Criteria

### G-29 — Qualification ratio (paper_S / wf_S) is the right metric but caps are arbitrary
- **Component**: Graduation
- **Current state**: 0.6 ≤ ratio ≤ 2.0. Above 2.0 = "regime-luck" (paper period unusually favourable). Below 0.6 = "edge degraded".
- **Industry standard**: There is no industry standard for this specific ratio. Most firms use ex-post forward-test Sharpe ≥ 50% of in-sample for promotion (which is what 0.6 captures). The 2.0 cap is unusual but defensible (else you're graduating regime-lucky paper outcomes).
- **Impact**: **Low** — current values are reasonable.
- **Effort**: **Medium** — recalibrate after 6 months of graduations.
- **Priority**: **P3**.

### G-30 — Min trades aggregation crosses strategy_id versions
- **Component**: Graduation
- **Current state**: Stats aggregated across all strategy_ids for `(template_name, symbol)`. A retired strategy's trades count toward graduation of a new strategy with the same template+symbol.
- **Industry standard**: Industry varies. AQR uses fresh OOS only. Carver allows historical context.
- **Impact**: **Medium** — current aggregation can let a marginal new strategy "ride" on the retired predecessor's trade count. Counterargument: if the underlying edge is real, the trades are valid evidence.
- **Effort**: **Low** — toggle behind a config flag.
- **Priority**: **P3**.

### G-31 — `paper_trading.graduation_gate.min_trades_*` and root `graduation_gate.min_trades` interact unclearly
- **Component**: Graduation / config integrity
- **Current state**: SQL HAVING uses root `graduation_gate.min_trades = 15`. Per-interval (`min_trades_1d=10, 4h=15, 1h=25`) only applies in post-SQL `is_qualified`. So 1d pairs with 10-14 trades are filtered OUT by SQL and never reach `is_qualified`.
- **Industry standard**: Interval-aware gate at all stages.
- **Impact**: **Medium** — 1d strategies need 15 trades effectively, not the documented 10.
- **Effort**: **Low** — change SQL HAVING to dynamic min based on interval (subquery on strategy_id → metadata.interval).
- **Priority**: **P2**.
- **Proposed fix**: Compute `min_trades_per_pair` per row in the SQL CTE using a CASE on metadata.interval. Or: keep SQL HAVING at 10 (lowest), enforce per-interval thresholds in `is_qualified` only.

---

## 10. Data Quality

### G-32 — No automated bar-gap detection on critical symbols
- **Component**: Data pipeline
- **Current state**: Intel D1/D2 detect stale 1d/4h bars. Gap detection is operator-pull, not push.
- **Industry standard**: Real-time gap monitoring with auto-fetch on detection. Pager Duty for prolonged gaps.
- **Impact**: **Medium** — a stale bar causes wrong indicator values and wrong signals. No symbol has shown this in practice but the failure mode is silent.
- **Effort**: **Medium**.
- **Priority**: **P2**.
- **Proposed fix**: Add a `MonitoringService._check_bar_freshness` method running every 15 min. Enqueue Yahoo/FMP refresh on staleness. Surface in Guard → Sync Log.

### G-33 — FMP insider endpoint 403/404 silently degrades AE quality
- **Component**: Data
- **Current state**: `calculate_insider_net_buying` uses momentum proxy fallback when FMP returns 403/404.
- **Industry standard**: Either pay for the FMP plan that has insider data, or use a different provider (Tipranks, Simply Wall St, SEC EDGAR direct).
- **Impact**: **Medium** — the AE Insider Buying Long template loses its core signal.
- **Effort**: **Low** — pricing decision.
- **Priority**: **P2**.

### G-34 — MQS persistence path was silent-failing (resolved May 12)
- **Component**: Data
- **Current state**: MQS now persisted to `equity_snapshots.market_quality_score` correctly (recent run shows 84). Previous bug: wrapped in `except: pass`.
- **Industry standard**: No silent failures. Log + alert + degrade.
- **Impact**: Resolved, but left a 2-week gap in MQS history.
- **Effort**: Done.
- **Priority**: **Closed**.

---

## 11. Analytics & Observability

### G-35 — Cycle stage failures don't write `signal_decisions` rows
- **Component**: Observability
- **Current state**: When a cycle stage throws, only logs `Error proposing strategies:` and continues silently. No `signal_decisions cycle_error` row.
- **Industry standard**: Every cycle stage has a tagged error event.
- **Impact**: **Medium** — funnel counts are inaccurate; failures are invisible to the dashboard.
- **Effort**: **Low**.
- **Priority**: **P1** (cheap, high observability win).
- **Proposed fix**: Add a `cycle_error` stage to `decision_log`. Write on every cycle-stage exception with `metadata={stage_name, error_type, traceback_summary}`.

### G-36 — No factor attribution
- **Component**: Analytics
- **Current state**: P&L is decomposed into realised vs unrealised, % vs $, alpha vs SPY, daily returns. No factor decomposition.
- **Industry standard**: Carhart 4-factor (market, SMB, HML, momentum) regression on daily strategy returns. Alternatively, AQR Style Premia (value, momentum, carry, defensive).
- **Impact**: **Medium** — without factor attribution, can't tell whether returns come from genuine alpha vs factor exposure.
- **Effort**: **Medium** — pull factor returns from Ken French data library.
- **Priority**: **P2**.
- **Proposed fix**: Add `analytics/factor_attribution.py` with daily regression. Surface in Research → Attribution tab. Show alpha (intercept) and factor loadings.

### G-37 — No Sharpe decomposition by source
- **Component**: Analytics
- **Current state**: One reported Sharpe per strategy.
- **Industry standard**: Decomposition: Sharpe from market timing, factor exposure, idiosyncratic alpha, residual.
- **Impact**: **Low**.
- **Effort**: **Medium**.
- **Priority**: **P3**.

---

## 12. Templates & DSL

### G-38 — Triple EMA Alignment generates 0 trades (regex param substitution bug)
- **Component**: DSL / templates
- **Current state**: The regex-based positional substitution in `strategy_proposer._apply_parameters_to_condition` collapses to `EMA(10) > EMA(10)` when fast/mid/slow params don't match the literal template values (Session_Continuation: "Batch 4 fix pending").
- **Industry standard**: Templates use named placeholders, not positional regex.
- **Impact**: **Medium** — a real template producing 0 trades is dead capital allocation in proposals.
- **Effort**: **Medium** — refactor to named-placeholder substitution.
- **Priority**: **P2**.
- **Proposed fix**: Introduce `EMA(${fast_period})` placeholder syntax in templates. Substitute by name. Backwards-compatible: keep old positional substitution as fallback.

### G-39 — Sector Rotation + Pairs Trading templates structurally broken
- **Component**: Templates
- **Current state**: Sector Rotation `fixed_symbols` covers only 5 of 11 SPDR sectors. Pairs Trading Market Neutral DSL conditions are momentum-long signals, not pairs.
- **Industry standard**: Either fix or remove.
- **Impact**: **Medium** — wasted proposal slots.
- **Effort**: **Medium-High** — needs a design session.
- **Priority**: **P2**.
- **Proposed fix**: Add all 11 SPDR sectors to Sector Rotation. Rewrite Pairs Trading as a true pairs strategy using `LAG_RETURN("XLK", 5, "1d") - LAG_RETURN("XLF", 5, "1d") > 0.02` style cross-asset DSL.

### G-40 — DSL grammar doesn't support method calls (`.shift(1)`)
- **Component**: DSL
- **Current state**: `MACD() > MACD_SIGNAL() AND MACD() > MACD().shift(1)` is unparseable. Templates that need shift have to express it as a separate indicator (`MACD_PREV` etc.).
- **Industry standard**: DSL should support member access for time-shifted comparisons.
- **Impact**: **Low** — workaround exists.
- **Effort**: **Medium** — extend Lark grammar.
- **Priority**: **P3**.

---

## 13. Live Trading

### G-41 — LIVE conviction threshold default in code is 74, YAML is 73
- **Component**: Live trading / config integrity
- **Current state**: `trading_scheduler.py:1401` defaults to `74` if YAML key missing; YAML carries 73. YAML wins, but the in-code fallback is inconsistent.
- **Industry standard**: One canonical value; either YAML or code, not both.
- **Impact**: **Low**.
- **Effort**: **Low**.
- **Proposed fix**: Change in-code default to 73 to match YAML.

### G-43 — `paper_trading.conviction_threshold` separation needs to reach the signal-time gate
- **Component**: Conviction / config wiring
- **Current state**: The YAML `paper_trading.conviction_threshold` (60) and `paper_trading.conviction_threshold_crypto` (55) keys exist and the Settings → Paper Trading page round-trips them correctly (`src/api/routers/config.py:1815-1885`). Other `paper_trading.*` blocks (`activation_thresholds`, `graduation_gate`, `flat_position_size`) ARE consumed by their gates. But the runtime signal-time conviction filter in `strategy_engine.generate_signals` (lines 5573-5576) reads only `alpha_edge.min_conviction_score` / `alpha_edge.min_conviction_score_crypto`. So paper strategies today are gated at 70/62 (the alpha_edge values, written by the Risk Limits Settings page), not at 60/55. Intel H4 (`intel_analyst.py:2009-2040`) flags this divergence as a known config-integrity issue.
- **Industry standard**: Paper-trading thresholds independent from live thresholds is correct practice — paper is for data collection (lower bar), live is for capital allocation (higher bar). This is also documented in Carver's *Systematic Trading* Chapter 11 ("you want false positives in your sandbox so you can find true positives faster").
- **Impact**: **Medium** — paper book is currently smaller than it should be at the intended threshold (60), and the 60-69 conviction band that would generate the most data-collection trades is being blocked. ~73 strategies in the 65-69 band per Intel A7.
- **Effort**: **Low** — ~10 lines.
- **Priority**: **P1** (the YAML separation has been done; closing this is the last 10% of work).
- **Proposed fix**: In `strategy_engine.generate_signals` (line 5025), branch the threshold:
  ```python
  is_paper_account = (account_type == 'demo')
  if is_paper_account and conviction_override is None:
      _paper = config.get('paper_trading', {})
      min_conviction = _paper.get('conviction_threshold', _ae_config.get('min_conviction_score', 70))
      min_conviction_crypto = _paper.get('conviction_threshold_crypto', _ae_config.get('min_conviction_score_crypto', 62))
  else:
      min_conviction = _ae_config.get('min_conviction_score', 70)
      min_conviction_crypto = _ae_config.get('min_conviction_score_crypto', 62)
  ```
  The LIVE pass already sets `conviction_override`, so it bypasses this branch. After the fix, also relabel the Risk Limits Settings page so it doesn't write to `alpha_edge.min_conviction_score` under a paper-looking label — it should write to `live_trading.conviction_threshold` (or be removed if the per-LIVE-pair `live_strategies.conviction_min` is the true lever).

### G-42 — 4h cooldown on live orders may be too long
- **Component**: Live
- **Current state**: 4h cooldown on live entry orders (Session_Continuation: "belt-and-suspenders").
- **Industry standard**: 1-2h is sufficient; 4h delays re-entry after legitimate position close.
- **Impact**: **Low** — only one live strategy currently.
- **Effort**: **Low**.
- **Priority**: **P3**.

---

## 14. Prioritised Fix List

### P1 — Close in current sprint (high impact, low/medium effort)

| ID | Component | Fix |
|---|---|---|
| **G-01** | WF | Add `(test_S − train_S) ≤ 1.5` consistency gate to test-dominant path |
| **G-02** | WF | Implement Deflated Sharpe Ratio at activation gate |
| **G-07** | Sizing | Cumulative correlation cap (group by correlation cluster, 8% per cluster) |
| **G-09** | Proposer | Reject proposals correlated > 0.65 with active strategies (post-WF dedup) |
| **G-10** | Risk config | Wire `position_management.correlation_adjustment.{threshold, reduction_factor}` from YAML |
| **G-19** | Execution | Real slippage model (`slippage = base + (size/ADV)^0.6 × spread`) trained from `trade_journal.slippage` |
| **G-35** | Observability | Write `cycle_error` stage to `signal_decisions` on every cycle-stage exception |
| **G-43** | Conviction wiring | Branch signal-time conviction threshold by `account_type` to honour `paper_trading.conviction_threshold` |

### P2 — Next sprint (medium impact, medium effort)

| ID | Component | Fix |
|---|---|---|
| **G-03** | WF | Block bootstrap (replace IID resampling) |
| **G-04** | WF | Remove Pass-2 relaxed admit path |
| **G-05** | Sizing | Per-strategy-type vol target (15/14/10/13/12) |
| **G-06** | Sizing | Recompute paper sizing strategy after research |
| **G-11** | Risk | Daily-updated correlation matrix table |
| **G-14** | Regime | Cache regime once per cycle in `cycle_run.metadata` |
| **G-17** | Retirement | `pending_retirement_force_close_days = 14` |
| **G-20** | Execution | Implementation Shortfall TCA in `execution_quality_daily` |
| **G-21** | Execution | Order state machine (no position row until fill confirmed) |
| **G-22** | Execution | `OrderStatus.DEFERRED` instead of FAILED for market-closed |
| **G-23** | Risk | Re-enable VaR with historical simulation (after 90 days history) |
| **G-24** | Risk | Heat cap uses actual SL distance, not 6% proxy |
| **G-26** | Risk | Track CFD margin separately from equity |
| **G-27** | SHORT | Recalibrate SHORT conviction threshold post-May 15 fixes |
| **G-31** | Graduation | Interval-aware SQL HAVING in graduation queue |
| **G-32** | Data | Real-time bar gap detection with auto-refetch |
| **G-33** | Data | Decide on FMP plan upgrade for insider data |
| **G-36** | Analytics | Carhart 4-factor attribution daily |
| **G-38** | Templates | Named-placeholder DSL substitution (Triple EMA fix) |
| **G-39** | Templates | Fix Sector Rotation (11 sectors) + rewrite Pairs Trading |

### P3 — Future / nice-to-have

| ID | Component | Fix |
|---|---|---|
| G-08 | Sizing | Conviction-tier multipliers refit after 200+ trades per bucket |
| G-12 | Code | Rename two `CorrelationAnalyzer` classes |
| G-13 | Regime | HMM regime detection as tiebreaker |
| G-15 | Regime | Per-coin crypto regime |
| G-16 | Decay | Timeframe-aware recovery rate |
| G-18 | Retirement | Composite kill score |
| G-25 | Risk | Tighter drawdown sizing ladder |
| G-28 | SHORT | Explicit `is_uptrend_short_template()` helper |
| G-29 | Graduation | Recalibrate qualification ratio caps after 6 months |
| G-30 | Graduation | Toggle for cross-strategy_id min_trades aggregation |
| G-37 | Analytics | Sharpe decomposition by source |
| G-40 | DSL | Support `.shift(N)` in grammar |
| G-41 | Live | In-code conviction threshold default 73 |
| G-42 | Live | Reduce live-order cooldown 4h → 1h |

---

## 15. What is NOT a gap

For completeness, several things commonly flagged are not gaps at AlphaCent's scale or pose more risk to fix than to leave:

- **No HPC / co-location** — at retail CFD scale, the 100-200 ms eToro round-trip dominates; sub-ms infrastructure adds nothing.
- **No prime brokerage features** — single eToro account is the right shape for the AUM.
- **No cross-venue execution** — eToro is the only execution venue and there's no edge in routing.
- **No FIX protocol** — eToro REST API is fine.
- **No GPU model training** — current models are simple rule-based + regression; GPU would be over-engineering.
- **No proprietary alternative data** — at $500K AUM, the cost of alt-data subscriptions exceeds the alpha they'd generate.

---

## 16. Closing notes for the new senior quant

Six things to know in your first week:

1. **The system runs.** Live capital is deployed (GOOGL LONG, +$16). Demo equity $479K is up from $250K seed. The architecture is honest.
2. **The biggest immediate risks are statistical, not infrastructural.** Walk-forward bypass (G-01), DSR (G-02), and correlation-aware sizing (G-07/G-09) are the three things that most affect P&L in the next 90 days.
3. **Several "dead config" gaps are cheap wins.** G-10 alone (5-line change) restores Settings UI trust. G-43 closes a deliberate paper/live separation that's wired everywhere except the signal-time conviction gate.
4. **Slippage modelling (G-19) is the single highest-impact P1 unlock.** Backtest Sharpes are inflated; closing this gap recalibrates the whole activation chain.
5. **Be careful with the `paper_trading.*` keys in YAML.** Most ARE wired (`activation_thresholds`, `graduation_gate`, `flat_position_size`). The signal-time conviction gate is the one that isn't yet (G-43). Don't change one without grepping for its consumer.
6. **Read `Session_Continuation.md` weekly.** It's the running log of what changed and what's pending. The audit you're holding is a snapshot; that file is the diary.

The platform is a serious systematic trading system at the right scale for $500K AUM. The gaps above are real and worth fixing, but none invalidate the architecture. Pick P1s, ship them clean, validate against `signal_decisions` funnel data, move to P2.


---

## 17. RESEARCH → PAPER → LIVE Lifecycle Adaptation

The system has three lifecycle stages with different objectives:

- **RESEARCH**: WF/MC validation. Already correctly differentiated (`paper_trading.activation_thresholds` overlay).
- **PAPER**: data collection on demo capital. Should be permissive (more trades = more graduation evidence).
- **LIVE**: alpha generation on real capital. Should be strict (capital preservation + risk discipline).

The system originated as research→paper and inherited paper-irrelevant risk machinery. LIVE was added later as a separate signal pass that bypasses the risk framework entirely. This produces the wrong adaptations on both sides — PAPER over-restricts data collection, LIVE under-restricts capital deployment.

This section catalogues the lifecycle adaptation gaps. Many of these supersede or reframe the P1s in earlier sections.

### G-44 — LIVE pass bypasses `RiskManager.validate_signal` entirely
- **Component**: Live trading / risk
- **Current state**: `trading_scheduler._run_trading_cycle:2148+` calls `_live_order_executor.execute_signal` directly with CIO-set size. **No call to `RiskManager.validate_signal`.** Heat cap, sector cap, directional balance, VaR, correlation, circuit breaker — none apply to LIVE.
- **Industry standard**: Portfolio-level risk gates apply to all real-capital trades. Trivially obvious; this is the foundational risk framework.
- **Impact**: **Critical** — once there are 5+ LIVE strategies, no concentration limits apply. Breaks at scale. Currently masked by having only 1 LIVE strategy.
- **Effort**: **Low** — call `validate_signal` in the LIVE pass before submitting. Reuse the same function.
- **Priority**: **P1**.
- **Proposed fix**: In `trading_scheduler.py:2138` (just before `_live_order_executor.execute_signal`), call:
  ```python
  validation_result = self._risk_manager.validate_signal(
      signal=_lsig,
      account=_live_account_info,
      positions=_live_positions,
      strategy_allocation_pct=2.0,  # LIVE strategies are ~2% per CIO approval
      is_paper=False,  # LIVE — full risk framework applies
  )
  if not validation_result.is_valid:
      logger.info(f"Live pass: validate_signal rejected {_live_sym}: {validation_result.reason}")
      continue
  ```
  Where `_live_positions` is queried with `account_type='live'` filter. **This is the single most important LIVE adaptation gap.**

### G-45 — LIVE pass bypasses `RiskManager.calculate_position_size` (the 11-step pipeline)
- **Component**: Live trading / sizing
- **Current state**: LIVE sizes positions with `_live_size = max(min_order_size, min(max_order_size, _appr.position_size))` (line 2138). The CIO sets a fixed size at graduation; vol scaling, conviction-tier, drawdown sizing, MQS multiplier, sector cap, heat cap, loser penalty all bypassed.
- **Industry standard**: Vol-scaled position sizing (Carver) and correlation-aware caps (AQR) apply to all real-capital trades. CIO can set a target/cap, but the 11-step pipeline shapes the actual size.
- **Impact**: **Critical** — LIVE positions are not vol-scaled. A strategy graduated when target vol was 16% but BTC is now at 80% annualised vol gets the same dollar size — 5× the intended risk.
- **Effort**: **Medium** — branch the sizing pipeline so LIVE applies it but uses CIO `position_size` as the cap (not as the absolute size).
- **Priority**: **P1**.
- **Proposed fix**: Add `is_live=True` parameter (analogous to `is_paper=True`). When `is_live`:
  - Run the 11-step pipeline using LIVE risk parameters (`live_trading.base_risk_pct`, `live_trading.symbol_cap_pct`, `live_trading.portfolio_heat_cap`).
  - Cap final size at CIO `position_size` (the CIO sets a max, the pipeline can size lower).
  - Use `live_trading.min_order_size` as the floor instead of $2,000.
  - Vol scaling and conviction-tier sizing both apply.

### G-46 — `MAX_PER_SYMBOL_PER_TIMEFRAME = 4` applies to PAPER (limits data breadth)
- **Component**: Paper / coordination
- **Current state**: `trading_scheduler._coordinate_signals:323` — 4 strategies max per (symbol, timeframe) bucket. Applied uniformly to PAPER and LIVE.
- **Industry standard**: This is a capital-concentration limit. For PAPER (demo), there's no capital concentration concern. PAPER should allow 8-12 per (symbol, timeframe) so the graduation gate has more independent template/symbol pairs to choose from.
- **Impact**: **Medium** — currently 47 active strategies × 1 of 4 per (symbol, TF) bucket means many templates can't co-exist on the same symbol.
- **Effort**: **Low**.
- **Priority**: **P1**.
- **Proposed fix**: Branch the constant by stage. PAPER → 8; LIVE → 4 (existing). Read from `paper_trading.max_per_symbol_per_timeframe` (default 8) and `live_trading.max_per_symbol_per_timeframe` (default 4).

### G-47 — Symbol cap, sector cap, heat cap, drawdown sizing all run on PAPER
- **Component**: Paper / sizing
- **Current state**: `risk_manager.calculate_position_size` Steps 6-10 (symbol cap 5%, sector cap 30%, heat cap 30%, drawdown sizing) run on PAPER. PAPER mode has its own short-circuit (Step 0a) for flat sizing — but only when `is_paper=True` is passed; otherwise the full pipeline runs. **The flat-sizing short-circuit IS used currently** (`trading_scheduler.py:1117 is_paper=True`), so these caps don't actually run for PAPER signals — but they do run inside the short-circuit's symbol-cap check (the only hard limit kept).
- **Industry standard**: PAPER should keep only execution-feasibility limits (symbol cap to avoid eToro position-merge limits), not capital-preservation limits.
- **Impact**: **Low** — the existing short-circuit already keeps PAPER simple. But the symbol cap is set to LIVE's preservation level (5% of equity = $24K) which is too conservative for paper data collection; a higher cap (10-15%) would give 2-3× more concurrent positions per symbol.
- **Effort**: **Low**.
- **Priority**: **P2**.
- **Proposed fix**: In the PAPER short-circuit, raise symbol cap from `0.05 × equity` to `0.10 × equity` (still execution-safe, allows more diverse paper data per symbol).

### G-48 — Avg-loss gate has no PAPER disable
- **Component**: Activation / paper
- **Current state**: `autonomous_strategy_manager.py:2258` rejects strategies with `avg_loss > N×SL` and 20+ trades. Has no `is_paper` short-circuit. PAPER strategies hit this gate the same as LIVE candidates.
- **Industry standard**: Activation gates that reject based on bad trade outcomes prevent data collection on those exact strategies. PAPER should pass through.
- **Impact**: **Medium** — strategies that would have been valuable data points get killed before reaching PAPER.
- **Effort**: **Low**.
- **Priority**: **P1**.
- **Proposed fix**: Add a check at line 2258: `if config_thresholds.get('disable_avg_loss_gate', False): skip`. The flag is already in `paper_trading.activation_thresholds.disable_avg_loss_gate=true`.

### G-49 — Trade frequency limiter caps AE strategies at 4 trades/month uniformly
- **Component**: Paper / frequency limiter
- **Current state**: `TradeFrequencyLimiter` (`trade_frequency_limiter.py:96-118`) blocks AE signals when `trades_this_month >= 4` AND `days_since_last < 3`. Applied uniformly. `alpha_edge.max_trades_per_strategy_per_month=4` and `min_holding_period_days=3` are LIVE-grade discipline.
- **Industry standard**: PAPER should let AE strategies fire as often as their signals allow — graduation requires statistical sample size. LIVE should cap to control turnover costs.
- **Impact**: **Medium** — AE strategies in PAPER take 5+ months to accumulate 20 trades (the graduation min). With the cap, the lower bound is `max_trades × 5 = 20 trades / 5 months`.
- **Effort**: **Low**.
- **Priority**: **P2**.
- **Proposed fix**: Branch by `account_type`. PAPER: bypass the AE limiter entirely (DSL strategies already bypass it). LIVE: keep the current cap.

### G-50 — C1 VIX gate and C3 trend-consistency gate apply to PAPER
- **Component**: Paper / runtime gates
- **Current state**: Both gates run inside `OrderExecutor.execute_signal`, which is called for both DEMO and LIVE order paths.
- **Industry standard**: Runtime gates are capital-preservation tools. In PAPER, blocking a signal during VIX spike or counter-trend setup means we don't collect the data point that would let us learn. Worse: it biases the paper Sharpe/WR upward (no losses on these blocked setups), which then misleads the graduation gate.
- **Impact**: **Medium** — paper Sharpe is upward-biased relative to what live Sharpe will be. The graduation `qualification_ratio = paper_S / wf_S ≥ 0.6` is currently fed an inflated paper_S.
- **Effort**: **Low**.
- **Priority**: **P1**.
- **Proposed fix**: In `OrderExecutor.execute_signal`, gate the C1 and C3 checks on `account_type == 'live'`. PAPER orders skip C1 and C3, LIVE applies them. Add `signal_decisions` rows for C1/C3 application as `gate_blocked` only on LIVE so the funnel reflects the right counts.

### G-51 — Circuit breaker applies to PAPER
- **Component**: Paper / risk
- **Current state**: `RiskManager.check_circuit_breaker` trips on daily P&L loss. Applies to all signals.
- **Industry standard**: PAPER tripping the circuit breaker halts data collection. PAPER drawdowns are observation events, not capital events.
- **Impact**: **Low** — circuit breaker has not tripped in months on demo equity.
- **Effort**: **Low**.
- **Priority**: **P3**.
- **Proposed fix**: Branch by account_type — PAPER doesn't trip; LIVE does.

### G-52 — Per-pair loser penalty (Step 10b) applies to PAPER
- **Component**: Paper / sizing
- **Current state**: `risk_manager.py:1351-1370` halves position size when (template, symbol) has 3+ closed losing trades. Applies to all paper sizing — except actually, the PAPER short-circuit (`is_paper=True`) bypasses Step 10b entirely. So this gap doesn't exist for PAPER signals on the current `is_paper=True` path.
- **Industry standard**: LIVE should keep this; PAPER bypasses correctly.
- **Impact**: **None — already correct via the PAPER short-circuit.**
- **Effort**: 0.
- **Priority**: **Closed (already correct)**.

### G-53 — Conviction-tier sizing multipliers (Step 10c) apply to PAPER but the path is bypassed
- **Component**: Paper / sizing
- **Current state**: Same as G-52. Step 10c is bypassed by the PAPER flat-sizing short-circuit.
- **Impact**: None.
- **Priority**: **Closed (already correct)**.

### G-54 — Volatility scaling target (16%) is shared between PAPER (irrelevant) and LIVE (applied via what path?)
- **Component**: Sizing / vol target
- **Current state**: `TARGET_VOL = 0.16` hardcoded in `risk_manager.calculate_position_size:802`. PAPER bypasses sizing entirely (flat $5,000). LIVE bypasses `calculate_position_size` entirely (CIO size).
- **Industry standard**: LIVE positions should be vol-scaled. With the current architecture, vol scaling is applied to **nothing**. CIO sets a single position_size at graduation that doesn't adjust to changing market vol.
- **Impact**: **High for LIVE** — covered by G-45. **Zero for PAPER** by design.
- **Effort**: covered by G-45.
- **Priority**: covered by **G-45**.

### G-55 — `live_strategies.position_size` is fixed at graduation; doesn't follow regime
- **Component**: Live trading / sizing
- **Current state**: CIO approves `position_size, sl_pct, tp_pct, conviction_min` once at graduation (`graduation_gate.approve_graduation:495-496`). These are fixed for the lifetime of the LIVE strategy.
- **Industry standard**: A LIVE strategy graduated when target vol was 16% should automatically scale down when realised vol doubles. AQR / Man Group / Winton all use rolling vol re-scaling, not fixed at graduation.
- **Impact**: **High** — covered by G-45. The CIO size becomes the *cap*, not the *target*, after fix.
- **Effort**: covered by G-45.
- **Priority**: covered by **G-45**.

### G-56 — `paper_trading.flat_position_size = $5,000` is single-symbol uniform; doesn't account for paper book size
- **Component**: Paper / sizing
- **Current state**: Every paper position is exactly $5,000 (flat sizing). With 70 demo positions and equity $479K, that's $350K (73%) of demo equity deployed.
- **Industry standard**: Flat sizing is correct for PAPER; the $5,000 number is reasonable. The only issue is whether the paper book scales with equity (e.g. should `flat_position_size` be `0.01 × demo_equity` instead of fixed)?
- **Impact**: **Low**.
- **Effort**: **Low**.
- **Priority**: **P3**.
- **Proposed fix**: Optional — change `flat_position_size` to a percentage of demo equity (`paper_trading.flat_position_pct: 0.01`). Skip for now; current behaviour is fine.

---

## 18. Updated Prioritised Fix List (lifecycle-aware)

Re-prioritised with the lifecycle lens. The structural realisation in §17 reorders the P1 list. **G-44 and G-45 are now the highest-impact P1s** because they affect real capital. Several earlier P1s remain.

### P1 — Close in current sprint (highest impact)

| ID | Stage focus | Component | Fix |
|---|---|---|---|
| **G-44** | LIVE | Risk validation | Call `RiskManager.validate_signal` in LIVE pass — no real-capital trades without portfolio risk gates |
| **G-45** | LIVE | Sizing | Run `RiskManager.calculate_position_size` in LIVE pass with `is_live=True`; CIO size becomes the cap, not the absolute |
| **G-43** | PAPER | Conviction wiring | Branch signal-time conviction threshold by `account_type` to honour `paper_trading.conviction_threshold = 60` |
| **G-46** | PAPER | Coordination | `MAX_PER_SYMBOL_PER_TIMEFRAME` 4→8 for PAPER (broader data collection) |
| **G-48** | PAPER | Activation | Honour `disable_avg_loss_gate` in `autonomous_strategy_manager.py:2258` |
| **G-50** | PAPER | Runtime gates | Skip C1 VIX gate and C3 trend gate on PAPER orders (don't bias paper Sharpe) |
| **G-01** | RESEARCH | WF | Add `(test_S − train_S) ≤ 1.5` consistency gate to test-dominant path |
| **G-02** | RESEARCH | WF | Implement Deflated Sharpe Ratio at activation gate |
| **G-09** | RESEARCH | Proposer | Reject proposals correlated > 0.65 with active strategies (post-WF dedup) |
| **G-10** | LIVE+PAPER | Risk config | Wire `position_management.correlation_adjustment.{threshold, reduction_factor}` from YAML |
| **G-19** | RESEARCH+LIVE | Execution | Real slippage model trained from `trade_journal.slippage` |
| **G-35** | All | Observability | Write `cycle_error` stage to `signal_decisions` |

### P2 — Next sprint (medium impact)

The P2 list from §14 still applies, plus:

| ID | Stage focus | Component | Fix |
|---|---|---|---|
| **G-49** | PAPER | Frequency limiter | Bypass AE trade-frequency cap on PAPER; keep on LIVE |
| **G-47** | PAPER | Sizing | Raise PAPER symbol cap 5%→10% of equity |

### P3 — Future / nice-to-have

The P3 list from §14 still applies. Plus:

| ID | Stage focus | Component | Fix |
|---|---|---|---|
| **G-51** | PAPER | Risk | Skip circuit breaker on PAPER |
| **G-56** | PAPER | Sizing | `flat_position_size` as percentage of demo equity |

---

## 19. The structural recommendation

Make **stage-awareness a first-class concept** in the risk framework. Two concrete options:

**Option A: pass `account_type` everywhere.**
- Add `account_type` parameter to `validate_signal`, `calculate_position_size`, `OrderExecutor.execute_signal`.
- Each gate decides whether to run based on `account_type`.
- Pros: explicit, easy to audit per gate.
- Cons: parameter pollution, every gate has its own branch.

**Option B: stage-specific risk profiles.**
- Define `RiskProfile.PAPER` and `RiskProfile.LIVE` as classes encapsulating which gates run with what parameters.
- `RiskManager` selects profile by strategy status at signal time.
- Pros: clean separation, config-driven, easy to add a third stage if needed.
- Cons: bigger refactor.

**Recommendation: Option A as a P1 patch (closes G-44/G-45/G-46/G-48/G-50 quickly), then Option B as a P3 cleanup once the patch stabilises.**
