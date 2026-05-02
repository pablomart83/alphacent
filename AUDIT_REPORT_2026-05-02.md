# AlphaCent — End-to-End Audit Report

**Session:** 2026-05-02 (Saturday, markets closed)
**System state at audit start:** equity $479,830, 85 open positions, 64 DEMO strategies, regime `trending_up_strong` (93% confidence), VIX 16.89

> This audit followed strict ground-truth rules: read current code, query the live DB, grep wide log windows. Did not trust Session_Continuation.md, AUDIT_FIX_TRACKER.md, or steering claims — verified each independently. Findings below are ranked by P&L impact and reversibility.

---

## Things I investigated and confirmed are actually OK

Prevents re-litigation next session.

### TSL (trailing stop) architecture
- Breach enforcement correctly runs for ALL open positions regardless of market hours or historical-bar freshness (only needs `current_price` + `stop_loss`).
- SL recalculation is correctly gated on market-open AND freshness-SLA; stale bars preserve existing SL (ratchet never moves backward, so preservation is safe).
- Per-cycle INFO summary line is emitting every 30s as expected. Verified on live logs: `TSL cycle: total=85 recalc_eligible=1 skipped_market=84 skipped_stale=0 breakeven=0 lock=0 trail=0 db_updated=0 breach=0 errors=0`.

### Risk manager position sizing
- Symbol concentration cap (now 5% after this session's change) IS enforced cumulatively across all strategies. Verified with live log at 11:05:12 yesterday: "Symbol cap exhausted: CAT existing=$17684 >= cap=$14346".
- Portfolio heat cap (30% of equity, assumes 6% SL per position) is enforced.
- Drawdown sizing multiplier reads from equity_snapshots daily history and scales down 50% at >5% DD, 75% at >10% DD.

### Data pipeline
- yfinance tz-aware UTC fix is deployed; no AmbiguousTimeError since Batch 1.
- Interval-aware freshness SLA correctly blocks signal generation on stale bars.
- Price cache has 302 daily symbols, 299 hourly, 299 4h, all reasonably fresh where actively used.
- Stale 4h bars (GS 17 days, NFLX/XLY/TM 14 days) are stale because no active 4h strategy uses them — correct on-demand refresh behavior.

### FRED retry wrapper
- No FRED errors in errors.log since Batch-1 deploy (F20 working correctly).

### Observability endpoints
- `/health/trading-gates` returns auth-gated 401 which is correct.
- `signal_decisions` table has proper schema + 5 indexes, active writes post-GRANT fix.

---

## P0 findings — observability-blocking or P&L-impacting

### P0-1 — Retirement system marks strategies for retirement but never actually retires them **[pending auto-execute]**

**Ground truth:**
- `strategies` table: 0 ever had `status=RETIRED`, 0 with `retired_at` set.
- 33 strategies currently carry `strategy_metadata.pending_retirement=true` — some since **April 13**, 19 days ago.
- 21 of 64 DEMO strategies are at `decay_score=0` (edge expired) but still generating signals.
- Decay log confirms: `[StrategyDecay] Checked 64, updated 64, retired 0` — every cycle, nothing retires.

**Root cause:** `monitoring_service._check_strategy_decay` correctly computes decay, but when it hits 0 it sets `pending_retirement=true` and waits for all open positions to close before demoting status. Since losers in an uptrend tend to hold (trailing stop isn't triggered, positions ride flat), positions rarely close naturally. And signal generation code has **zero references to `pending_retirement`** — these zombie strategies continue to fire new signals for the duration of their position lifespan.

**Trading impact:**
- 33 strategies we've deemed dead are still firing signals and creating new positions.
- Each new position extends the zombie's lifespan further (new positions won't all close at once either).
- Spam signals compete for capital slots against healthy strategies.
- The SHORT leakage in a strong uptrend (4 of 5 active SHORTs are pending_retirement zombies) is exactly this bug.

**Fix options (need decision):**
- (a) Signal generation skips `pending_retirement=true` strategies. Smallest change, biggest impact. Positions bleed out naturally; no new positions added.
- (b) On `pending_retirement=true`, flag all open positions for closure (same pending_closure mechanic as F30). Fast cleanup, realises losses immediately.
- (c) Demote to BACKTESTED immediately on decay=0 (current "no open positions" branch). Let positions ride to SL/TP; just stop proposing.

**Recommendation: (a) + (c).** Stop new signal generation AND demote to BACKTESTED state. Positions ride out naturally without new ones piling on.

### P0-2 — `live_trade_count` is 0 on every strategy, ever

**Ground truth:** 0 of 180 strategies have `live_trade_count > 0`. Yet "4H VWAP Trend Continuation Multi V117" has 20 currently-open positions.

**Root cause:** `order_executor._increment_strategy_live_trade_count` exists and is called at `order_executor.py:866` on fill handler — but the counter only increments under the synchronous-fill path. eToro async fills go through `order_monitor.check_submitted_orders` which **never calls** this increment.

**Trading impact:**
- Retirement min-trade gate (`min_live_trades_before_evaluation: 5`) never fires because `live_trade_count` never reaches 5.
- Performance feedback decay-from-live-data is silently broken.
- Retirement evaluation runs keyed on this counter miss every time.

**Fix:** Move the increment to `order_monitor.check_submitted_orders` fill handler so it fires on every real fill regardless of path. One line change. Also backfill historical counts from `trade_journal` (the backfill script I wrote today can be extended).

### P0-3 — Crypto backtests systematically overstated returns by ~2% per trade (fixed in this session)

**Ground truth (verified against etoro.com/fees):** eToro charges 1% commission per side on crypto since mid-July 2025. Config had `commission_percent: 0.0` for crypto on the assumption that commission was baked into spread (stale assumption). Round-trip cost was modeled at 0.95%; real is 2.96%.

**Trading impact pre-fix:**
- Every crypto WF gate was passing strategies whose real net return was 2% lower per trade.
- Current-DEMO crypto strategies may have passed under inflated numbers.

**Fix applied this session:**
- `commission_percent: 0.01` for crypto (commit `93c89a8`).
- Template cost filter raised from 4% to 6% TP floor (2× round-trip).
- Cycle just run confirms activation gate now blocks crypto strategies with net return < 0 after real costs. E.g., "ATR Expansion Breakout ETH: Net return -1.1% < 0".

**Verification status:** working. Next step — let normal WF cycle decide retirement for strategies that would no longer pass; do not force-retire.

### P0-4 — SHORT strategies are a structural loser (-$3,929 realised across 97 trades)

**Ground truth:**
- LONG: 780 closed trades, 51.2% WR, avg +$186/trade, total +$145K.
- SHORT: 97 closed trades, 29.9% WR, avg -$40/trade, total -$3,929.

**Analysis:** SHORT win rate of 30% is catastrophically low — expected 35-40% in a trending-up regime for uptrend-hedge templates. Suggests either:
- (a) SHORT templates fire on noise, not real reversal setups.
- (b) Templates are in the wrong market regimes and aren't being correctly filtered.
- (c) SHORT signal timing is late (entering after reversal has already happened).

MAE/MFE analysis (when populated over Monday) will tell us which: high MAE-at-stop with low MFE = timing bad; low MAE with high drawdown = regime wrong.

The SHORT WF tightening shipped yesterday (`c5f949a`) is directionally right but doesn't repair historic damage. Active SHORT strategies (5) are 4/5 zombies pending retirement already. **No immediate fix needed beyond letting P0-1 retire the zombies.**

### P0-5 — Signal decisions writer was silently dropping every row (fixed this session)

**Status:** fixed (commit `1f28bfb`). `signal_decisions` table was created as `postgres` user without `GRANT` to `alphacent_user`. Every INSERT returned "permission denied for table signal_decisions". Writer caught all exceptions at DEBUG level → invisible. Fixed via `GRANT` + `ALTER DEFAULT PRIVILEGES` on schema.public. Cycle just ran populated 402 rows across 5 stages. Hardening: writer now logs failures at WARNING with 5-min per-signature cooldown so the next silent-write-failure can't hide for a week.

### P0-6 — Cycle-error observability gap

**Ground truth:** Cycles that throw mid-stage (e.g. the `SignalAction` NameError earlier today, the `Tuple` NameError at 07:22 UTC) leave a `[ERROR] CYCLE:` line in cycle_history.log but write **no row to `signal_decisions`**. The funnel stays incomplete and the Observability panel doesn't know the cycle stage failed.

**Fix:** Add a `cycle_error` stage write in the top-level autonomous_cycle try/except so stage failures surface in the funnel. ~10 lines. Should be done before any more observability work relies on the funnel being complete.

---

## P1 findings — operational waste or misleading metrics

### P1-1 — Entry order FAILED rate was 56% but now near-zero (was Apr 27-29 spike)

**Ground truth:**
- Total orders: 2,126. FAILED entries: 802 (56% of 1,443 entry orders).
- But all 802 are concentrated April 27-29 (170-200/day during UK market hours 09-13 UTC). Last 7 days: 0-2 failures/day.

**Root cause:** fixed by Batch-1 / Yahoo DST work on April 30. The spam was correct-on-retry signaling after DST caused batch fetch crashes → symbols returned empty → signals fired with stale prices → eToro rejected.

**Status:** resolved, but the 802 FAILED rows sit in the DB polluting the order history stats. Low-priority cleanup: DELETE rows where `status=FAILED AND submitted_at < '2026-04-30'`.

### P1-2 — 244 (now 69 post-backfill) trade_journal orphan rows

**Status:** partially fixed this session. 175 of 277 orphan "open" rows backfilled via `scripts/backfill_trade_journal_orphans.py` — they were closed positions where `log_exit` was never called due to trade_id convention mismatch between `order_monitor` (order UUID) and `order_executor` (position id). 69 remain unmatched — they reference positions that were deleted during earlier cleanup work.

**Follow-up:** log_entry and log_exit should agree on trade_id. Pick one (position.id recommended; it's available on both entry and exit), migrate order_monitor to use it, backfill is closed story.

### P1-3 — Execution fill times are heavily skewed, with legacy bad data

**Ground truth:**
- Entry orders: median fill 175s, P95 184,539s (51 hours), max 52 hours.
- 44 orders in the empty-action bucket have median fill time of **-3,225s** (negative — fill time < 0 means `filled_at < submitted_at` in DB).

**Analysis:** 
- The 51h P95 is orders submitted Friday filling on Monday. Expected on eToro DEMO for off-hours.
- Negative fill times are from historical data-migration bugs pre-today's compute-quality work; they don't poison future data because the new compute writes only when `delta >= 0` (verified in `order_monitor.py:1077`).

**Follow-up:** one-off DELETE or zero-out fill_time_seconds on the bad legacy rows so summary stats don't show negative median.

### P1-4 — MINIMUM_ORDER_SIZE floor undermines multi-layer sizing reductions

**Ground truth:** `risk_manager.calculate_position_size` Step 11 bumps any position sized below $5K back up to $5K if balance permits. A position that went through:
- Base: $2,879 (0.6% × $479,830)
- Drawdown sizing: 75% = $2,159
- Vol scaling: 0.5× = $1,080
- Loser penalty: 50% = $540
Will get reset to $5,000 — **10× the risk-managed target.**

**Trading impact:** penalty mechanisms (loser-pair, vol-scaling, DD-sizing) work correctly to reduce size, but are then bypassed by the floor. This is hidden in all order placements where the absolute size would be small.

**Fix options:**
- (a) Skip the bump if any size-reducing penalty fired (`old_size != pre_penalty_size`). 
- (b) Drop MINIMUM_ORDER_SIZE to $2K to preserve more sizing intent.
- (c) Return 0 if size < MINIMUM, skip the trade entirely (strictest).

Recommend (c) for symbols with active penalties, (b) universally.

### P1-5 — Factor-validation gate errors are noisy but correct

Every cycle shows 4 ERROR rows like "Insider Buying HII LONG: gate3 failed: primary symbol rank=0.0 not in right quintile for momentum_rank". Not a bug — the factor gate correctly rejects Alpha Edge proposals that don't clear factor-score quintiles. They're logged as ERROR when they should be INFO or DEBUG.

**Fix:** reclassify these from ERROR to INFO so the cycle log's ERROR count reflects real errors only.

### P1-6 — Log rotation window is too short for audit work (~8h)

10MB × 20 backups = 200MB main log, approximately 8-10 hours at current volume. Impossible to do DST-boundary forensics or cross-day incident investigation. Should go to 50MB × 20 or 10MB × 100.

---

## P2 findings — quality-of-life / nice-to-have

### P2-1 — New crypto template "Crypto Vol-Compression Momentum" didn't get proposed in the cycle you just ran

Loaded in library (verified) but not in `signal_decisions` as `stage=proposed`. `Crypto 21W MA Trend Follow` was proposed and WF-rejected (fair enough, 20-week crossover won't happen often in a 120-day test window). Vol-Compression never reached the proposer. Probable cause: `strategy_type=MOMENTUM` has interaction with the proposer's per-regime template pool or the hour-of-year rotation shuffle. Worth an hour of investigation but not urgent.

### P2-2 — Observability endpoints return 401 for our own diagnostic script

The `/analytics/observability/*` and `/health/trading-gates` endpoints are auth-gated which is correct for a web UI. For operational diagnosis, consider a separate `/debug/` prefix that only accepts requests from localhost (or from a known diagnostic IP allow-list).

### P2-3 — Stale `atr_sl_multiplier` config key was already removed (F13 OK)

Verified clean. `order_executor.py:241` is the source of truth with hardcoded 1.5x.

### P2-4 — FAILED factor_validation ERRORs should be INFO

See P1-5.

### P2-5 — Overview chart panel rewrite still pending

Known F25. Design doc should be written first.

---

## What changed in this session (already shipped)

| ID | Change | Commit |
|---|---|---|
| S-1 | Symbol concentration cap 3% → 5% | `8135334` |
| S-2 | decision_log writer: GRANT + ALTER DEFAULT PRIVILEGES + WARNING cooldown | `1f28bfb` |
| S-3 | Frontend timestamp drift fix (TradingCyclePipeline + formatTimestamp) | `efceb90` |
| S-4 | MAE/MFE updater trade_id mismatch fix | `03e08d8` |
| S-5 | Crypto min_trades tier (4) + 175 trade_journal orphan backfill | `9ef1419` |
| S-6 | Crypto real cost modeling + 6-coin universe + 2 new trend templates | `93c89a8` |

---

## Recommended execution order (pending your decision)

**Batch A — fix the retirement black hole (1 session, XS effort, big impact):**
- P0-1 (a+c): add `pending_retirement` skip in signal generation + demote to BACKTESTED on decay=0
- P0-2: fix `live_trade_count` increment in async fill path + historical backfill
- P1-5: reclassify factor_validation gate failures ERROR → INFO

**Batch B — observability completion (1 session, S effort):**
- P0-6: cycle_error stage write in autonomous_cycle try/except
- P1-3: zero-out legacy bad fill_time_seconds rows
- P1-6: raise log rotation to 50MB × 20

**Batch C — data-quality cleanup (1 session, S effort):**
- P1-1: DELETE the 802 FAILED legacy rows
- P1-2: migrate order_monitor log_entry to use position.id (then retire the fallback match)
- P1-4: tighten MINIMUM_ORDER_SIZE bypass — skip if penalty triggered

**Batch D — deferred / need design:**
- P2-1: debug Vol-Compression non-propose
- P2-2: localhost diagnostic endpoints
- P2-5: Overview chart panel

Batch A is the highest-leverage — it frees up ~19 zombie strategy slots and fixes the retirement counter everyone downstream depends on.
