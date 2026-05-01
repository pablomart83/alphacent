# Strategy Library Review — 2026-05

**Scope:** `src/strategy/strategy_templates.py` (~220 templates, 7,827 lines) reviewed against 2025–2026 public research from systematic hedge funds, academic working papers (last 18 months), and practitioner commentary. Ground-truth constraints: ~$475K equity, eToro CFD (no stock shorting intraday, at-touch fills, retail spread cost), 1d/4h/1h timeframes only, 297-symbol universe (232 stocks / 42 ETFs / 8 FX / 5 indices / 8 commodities / BTC+ETH).

Cross-referenced with F05, F08, F15, F17, F30 from `AUDIT_REPORT_2026-05-01.md` and the winner/loser P&L from `Session_Continuation.md`.

> **No code changes made.** Recommendations only. Implementation to be scheduled alongside Batch 4 (signal quality) work once F05 (Triple EMA substitution bug) is in production.

---

## Executive Summary

1. **Our trend-following and momentum families are the right strategies for this macro regime — the 2025 quant renaissance validated this in public performance.** AQR Apex +19.6%, Helix (trend) +18.6% in 2025, and equity long-short +7.7% in April 2026 ([AQR 2025 Scorecard](https://funanc1al.com/blogs/follow-the-pundits/aqr-capital-s-2025-scorecard-from-applied-quantitative-research-to-actually-quality-returns); [HedgeCo April 2026](https://hedgeco.net/news/04/2026/hedge-fund-alpha-roars-back-inside-the-resurgence-of-long-short-equity-and-the-violent-reset-driving-2026-performance.html)). Our winners (ATR Dynamic Trend, EMA Ribbon, 4H ADX Swing) align with this. The issue is not concept — it is that we have ~60 mean-reversion and bare-MA templates diluting the signal.

2. **The loser cohort — Fast EMA Crossover, SMA Proximity Entry, 4H VWAP Trend Continuation, BB Middle Band Bounce, SMA Envelope Reversion — is the bare-indicator crossover family. Academic and practitioner evidence is unambiguous: raw MA crossovers and unfiltered VWAP reversion do not produce standalone alpha at retail CFD cost structures.** SSRN 5186655 ([Chen 2024](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5186655)) shows 50/200 MA crossover underperformed buy-and-hold on every mega-cap in 2024. EMA crossover false-signal rates 57–76% ([Stockpathshala 2024](https://stockpathshala.com/is-ema-crossover-profitable/)). Our observed P&L matches. **Concept is broken for these specific formulations; better-filtered variants (our winners) retain the edge.**

3. **The biggest gap versus current hedge-fund practice is cross-sectional long-short equity — not single-name absolute signals.** April 2026 equity long-short +7.7% ([Goldman via HedgeCo](https://hedgeco.net/news/04/2026/hedge-funds-roar-back-inside-the-best-monthly-performance-in-a-decade-and-the-return-of-alpha.html)); sector rotation delivering 3–7% annualized alpha over buy-and-hold at retail-accessible scale ([TradeAlgo 2026](https://www.tradealgo.com/trading-guides/tools/sector-rotation-strategy-how-to-follow-institutional-money-in-2026)). **Our universe of 42 ETFs + 11 sector ETFs + 5 indices makes ETF rotation feasible; single-stock long-short is NOT feasible on eToro CFD (no intraday stock shorts).** Recommended additions are ETF-level, not stock-level.

4. **F05 (Triple EMA substitution bug) has been masking the real question about multi-EMA templates.** With `EMA(20) → EMA(fast_period)` regex collapsing conditions to `EMA(10) > EMA(10)`, we have no evidence about whether Triple EMA Alignment is a good or bad idea. It produced 0 trades. After F05 is deployed, we should treat every multi-MA-literal template (Triple EMA Alignment, Moving Average Crossover, Dual MA Volume Surge, MACD + EMA combos) as untested until fresh backtests run. **Do not retire any multi-EMA template until post-F05 backtests exist.**

5. **Six high-value additions, none requiring infrastructure beyond our DSL + Alpha Edge bypass.** Ranked by expected alpha on our book: ETF sector-rotation momentum, volatility-targeted position overlay (GARCH-lite), VIX regime-gate on the entry layer, commodity trend-following with MQS bump, PEAD residual momentum (improvement of existing Post-Earnings Drift Long), and a small-book pairs-basket for uncorrelated P&L. Anti-recommendations (below) explicitly rule out things that sound attractive but fail on eToro: single-stock long/short baskets, VXX short-vol carry, option-implied-vol signals without options access, sub-hour mean reversion.

---

## Current Library — Classification by Family

From grepping all `strategy_type` values and clustering by DSL pattern:

| Family | ~Count | Examples | Current Status |
|---|---|---|---|
| **Trend-following (filtered)** | ~40 | ATR Dynamic Trend Follow, EMA Ribbon, 4H ADX Trend Swing, MACD RSI Confirmed, Keltner Channel Breakout | **Winners** per Session P&L |
| **Trend-following (raw MA crossover)** | ~15 | Fast EMA Crossover, Moving Average Crossover, Dual MA Volume Surge, EMA Pullback Momentum | **Losers** (bare crossovers); some passable when volume/ADX filtered |
| **Mean-reversion (filtered / RSI-based)** | ~30 | RSI Mean Reversion, RSI Midrange Momentum, Stochastic Mean Reversion, RSI Bollinger Combo, Tight RSI Mean Reversion | **Mixed**; RSI Midrange is a winner |
| **Mean-reversion (envelope / proximity)** | ~12 | SMA Proximity Entry, SMA Envelope Reversion Long/Short, BB Middle Band Bounce, BB Midband Reversion Tight | **Losers** per Session P&L |
| **Breakout / Volatility** | ~20 | Bollinger Squeeze Breakout, ATR Expansion Breakout, Opening Range Breakout, Keltner Channel Breakout, High Vol ATR Breakout | **Mixed**; 1h/4h breakouts untested due to zero 1h active |
| **Momentum (pure)** | ~15 | Stochastic Momentum, 52-Week High Momentum Long, MACD Rising Momentum, Strong Uptrend MACD | **Not yet proven on our book** |
| **Short book (equity)** | ~20 | RSI Overbought Short, MACD Bearish Short, Exhaustion Gap Short Uptrend, Double Top Short, Volume Climax Short | **F17: zero active equity shorts** — pipeline broken, not concept |
| **Alpha Edge fundamental** | ~25 | Earnings Momentum, Sector Rotation, Quality Mean Reversion, Dividend Aristocrat, Insider Buying, Revenue Acceleration, FCF Yield Value, Accruals Quality, Multi-Factor Composite, Post-Earnings Drift Long, 52-Week High Momentum | Some active — needs per-AE-type P&L visibility |
| **Structural (pairs / relative value)** | 2 | Pairs Trading Market Neutral, Relative Value | **Positive open P&L but low activation rate** per Session |
| **Crypto-specialized** | ~40 | Crypto Quiet RSI Oscillator, Crypto Daily Oversold Bounce, Crypto 4H MACD Trend, 4H Crypto Trend Rider, Crypto Hourly Capitulation | BTC/ETH only; universe narrowed. F15 removed BTC Lead-Lag Altcoin |
| **Commodity-specialized** | ~10 | 4H Commodity Trend Continuation, Commodity Hourly Momentum Surge, Gold Momentum Long | New family — initial cohort |
| **Hourly intraday (1h)** | ~25 | Opening Range Breakout, Intraday Mean Reversion, Hourly RSI Oversold Bounce, Hourly EMA Crossover, Hourly MACD Signal Cross | **1 BACKTESTED, 0 DEMO** — emergent, not blocked; see §2.12 |

---

## 1. Web Research — What's Generating Alpha in 2025–2026

### 1.1 The macro regime

The post-Sept-2024 Fed rate-cut cycle and the ECB's June 2024 cuts created a durable "rate-cut tailwind" regime that extended into 2026. Rate-cut periods motivated by normalization (not recession) have historically delivered ~50% S&P 500 cumulative return over the following 2 years; actual performance 2024-Q3 → 2026-Q2 is tracking at ~20% ([TIAA 2026](https://www.tiaa.org/public/invest/services/wealth-management/perspectives/five-charts-fedpolicy-ai-interest-rates)). **Implication: long-bias trend-following remained profitable through this window, which our book benefited from.**

### 1.2 Who's winning and what they're running

- **AQR, 2025 full-year:** Apex (multi-strategy) +19.6%, Helix (trend-following) +18.6%. Trend equity factors, commodities, and volatility futures all contributed ([FUNanc1al 2025](https://funanc1al.com/blogs/follow-the-pundits/aqr-capital-s-2025-scorecard-from-applied-quantitative-research-to-actually-quality-returns)). AQR's disclosed trend fund explicitly combines price-based and fundamental trend signals ([AQR Trend](https://funds.aqr.com/funds/aqr-trend-total-return-fund)).
- **Global hedge funds, 2025:** ~12.6% annual returns; quantitative strategies 10.5%, discretionary macro 11.5%, systematic macro 0.5% ([ainvest 2026](https://www.ainvest.com/news/client-update-predict-prepare-2604/)). Systematic trend outperformed systematic macro.
- **April 2026:** Equity long-short had its best monthly print in a decade, +7.7% ([HedgeCo April 2026](https://hedgeco.net/news/04/2026/hedge-fund-alpha-roars-back-inside-the-resurgence-of-long-short-equity-and-the-violent-reset-driving-2026-performance.html)). Factor rotation — specifically "Pure Growth" and "Momentum" factors — reignited institutional interest in systematic rules-based investing ([HedgeCo April 2026 #2](https://hedgeco.net/news/04/2026/alternative-index-strategies-outpace-the-sp-500-as-factor-rotation-reignites-institutional-interest.html)).
- **CTA/trend followers:** 2024 and most of 2025 strong; early 2025 H1 was tough (April 2025 managed futures -4.47% at a low point per [RCM Alternatives](https://www.rcmalternatives.com/2025/05/aprils-shake-up-commodities-crash-managed-futures-follow/)). **Takeaway: trend-following is cyclical even within a favorable macro regime. Diversification across assets and timeframes mitigates.**

### 1.3 Regime-adaptation tactics paying now

- **Volatility targeting + regime-switching signals:** Man Group and academic work both document that vol-targeting improves Sharpe and reduces drawdown in 2025 vol spikes ([Man](https://www.man.com/insights/the-impact-of-volatility-targeting); [arxiv Dynamic Factor Allocation](https://arxiv.org/html/2410.14841v1)). GARCH-driven position sizing reduced crash exposure in the 2025 H1 quant unwind ([Resonanz Capital](https://resonanzcapital.com/insights/crowding-deleveraging-a-manual-for-the-next-quant-unwind)).
- **Confirmed momentum (price + operating):** Lord Abbett's research argues that combining price momentum with operating momentum (earnings revisions, sales growth) limits downside volatility vs. naive cross-sectional price momentum, while keeping upside ([Lord Abbett Nov 2025](https://www.lordabbett.com/en-us/financial-advisor/insights/investment-objectives/2025/the-benefits-of-price-and-operating-momentum-in-equity-portfolios.html)). **Relevant to our Post-Earnings Drift / Analyst Revision templates.**
- **Factor crowding and alpha decay:** 2025 quant unwind drove home that crowded factors (quality, low-vol ran into trouble in H1 2025) have hyperbolic decay `alpha(t) = K/(1+λt)` per [arxiv 2512.11913](https://arxiv.org/abs/2512.11913v1). Diversify across signal types; don't run one homogeneous factor.

### 1.4 Controversial call — "is momentum dead?"

**Steelman "yes":** 2025 H1 quant unwind hit quality and low-vol factors hard; crowding-based factor selection generated only 0.22 Sharpe vs 0.39 for factor momentum benchmark per [arxiv alpha decay paper](https://arxiv.org/abs/2512.11913v1); EMA crossovers show 57-76% false-signal rates in recent retail studies.

**Steelman "no":** AQR Large-Cap Momentum (Russell 1000 universe) continues to return; April 2026 long-short +7.7% was largely momentum driven; AQR Helix (trend-following) +18.6% in 2025; practitioner journals show explicit sector-rotation and confirmed-momentum variants still delivering 3-7% annualized alpha ([TradeAlgo 2026](https://www.tradealgo.com/trading-guides/tools/sector-rotation-strategy-how-to-follow-institutional-money-in-2026)).

**Resolution:** raw momentum (single-name 12-1 price momentum) is crowded and vulnerable to crashes. Refined momentum — time-series trend-following (AQR Helix), confirmed momentum (price + fundamentals), and sector/ETF rotation momentum — is alive. Our winners (ATR Dynamic Trend, EMA Ribbon) are already in the refined bucket. The loser templates (Fast EMA Crossover, SMA Proximity) are in the "raw" bucket that does not work at retail CFD cost.

---

## 2. Family-by-Family Verdict

### 2.1 Trend-Following (filtered) — KEEP, EXPAND

**Evidence:** AQR Helix +18.6% 2025 (trend); our own winners ATR Dynamic Trend Follow and 4H ADX Trend Swing are top performers. [AQR Trend Fund](https://funds.aqr.com/funds/aqr-trend-total-return-fund) describes the exact architecture — trend signals + regime filters.

**What distinguishes winners from losers in this family:** filter quality. Winners have ADX > 20/25 confirming trend, RSI in 50-65 momentum zone, and often price > SMA(50) structural filter. Losers rely on raw crossovers with no filter.

**Verdict:** This is the core of our equity/ETF/index alpha. Expand with regime-gating (trend templates suppressed when MQS < 40) — already partially implemented, tighten.

### 2.2 Trend-Following (raw MA crossover) — REMOVE or REDESIGN

**Evidence:** SSRN 5186655 ([Chen 2024](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5186655)): 50/200 MA crossover underperformed buy-and-hold on AAPL/MSFT/META/NFLX/NVDA through 2024. [crosstrade.io](https://crosstrade.io/learn/trading-strategies/moving-average-crossover): "In its raw form, it loses money in most conditions because of whipsaws in choppy markets." [alphaontheedge backtest](https://www.alphaontheedge.com/p/lets-test-every-moving-average-crossover): "no real value as a standalone trading strategy."

**Our data:** Fast EMA Crossover -$378 open P&L. Matches the literature.

**Important caveat:** F05 collision bug may be masking the true performance of Triple EMA Alignment, Dual MA Volume Surge, and other multi-literal templates. **Don't retire these until post-F05 backtests.**

**Verdict:**
- Fast EMA Crossover (EMA(5)/EMA(13)): REMOVE. Evidence is clear. No filter, tightest stops 2%, retail CFD spread alone kills this.
- Moving Average Crossover (generic SMA/EMA): REDESIGN with ADX > 20 filter + volume confirmation, or remove.
- Triple EMA Alignment: HOLD pending post-F05 backtest.
- Dual MA Volume Surge: HOLD — volume filter is the right idea, but needs fresh backtest post-F05.

### 2.3 Mean-Reversion (filtered RSI-based) — KEEP selectively

**Evidence:** RSI Midrange Momentum is a live winner in Session. RSI oversold/overbought mean reversion in ranging markets remains a solid family per [mbrenndoerfer](https://mbrenndoerfer.com/writing/mean-reversion-statistical-arbitrage-pairs-trading). Key: requires ranging regime (ADX < 20 or similar).

**Verdict:** Keep RSI Mean Reversion, Stochastic Mean Reversion, RSI Bollinger Combo, RSI Midrange Momentum, Tight RSI Mean Reversion. Raise activation bar: min trades ≥ 8 AND ADX filter at entry.

### 2.4 Mean-Reversion (envelope / proximity) — REMOVE

**Evidence:**
- SMA Proximity Entry -$308 open P&L on our book. Thin logic (price within 1% of SMA(10) with RSI < 45) — signals fire constantly, no regime filter; captures every small pullback including the ones that become trends.
- BB Middle Band Bounce -$141; crossing above middle band is a weak signal with no edge.
- SMA Envelope Reversion Long/Short: enters on ANY close below/above SMA(20) with RSI extreme; too loose.

These templates have a structural problem: they fire in trending markets (where the "envelope" gets crossed and then keeps extending) *and* in ranging markets. Without a regime filter, the signal is dominated by trending-market losses.

**Verdict:**
- SMA Proximity Entry: REMOVE.
- BB Middle Band Bounce: REMOVE.
- SMA Envelope Reversion Long/Short: REMOVE.
- BB Midband Reversion Tight: REMOVE unless gated on ranging_low_vol AND ATR/price < 1% explicitly.

### 2.5 Breakout / Volatility — KEEP, EXPAND into intraday

**Evidence:** Keltner Channel Breakout variants with ADX filter produce Sharpe > 1.0 in trending markets ([AQR commentary](https://www.aqr.com/Learning-Center/Systematic-Equities)). Opening Range Breakout has strong published ES/NQ results: [edgeful](https://www.edgeful.com/blog/posts/5-minute-opening-range-breakout-es-strategy), [quantmacro substack review](https://quantmacro.substack.com/p/paper-review-an-effective-intraday).

**Verdict:** Keep Keltner Breakout, Bollinger Squeeze, ATR Expansion, Opening Range Breakout. **Opening Range Breakout cannot currently activate (we have no 1h strategies live).** After Batch 4 stabilises, reopen 1h strategies per Session roadmap.

### 2.6 Momentum (pure) — MIXED

**Evidence on 52-week high momentum (George & Hwang 2004):**
- Original paper showed 52WH outperforms other momentum measures.
- [SSRN 4587697](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4587697) confirms 52WH strategies have weaker long-term reversals than academic momentum.
- HOWEVER [Byun & Jeon](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2900073) document 52WH as a contributor to momentum crashes during market rebounds.
- [Cambridge JFQA](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/investor-behavior-at-the-52week-high/5D1C7CA21396521F3B41D91B06A25BE1): household sellers at 52-WH *amplify* the anomaly rather than erode it.

**Our implementation:** 52-Week High Momentum Long has RSI < 70 filter and `best_symbols` restricted to megacap. Consistent with modern "residual momentum" implementations.

**Verdict:** Keep 52-Week High Momentum, Stochastic Momentum, MACD Rising Momentum. **Add a momentum-crash circuit breaker:** suppress momentum longs when SPY 5-day return > -3% with rising VIX (early rebound window).

### 2.7 Short book (equity) — KEEP templates, FIX pipeline

**Evidence:** April 2026 long-short +7.7% was largely short-side contribution ([HedgeCo](https://hedgeco.net/news/04/2026/hedge-fund-alpha-roars-back-inside-the-resurgence-of-long-short-equity-and-the-violent-reset-driving-2026-performance.html)). Hedge funds are shorting crowded names.

**Our problem (F17):** zero active equity shorts despite the `trending_up_weak` regime requiring min 8% short allocation. Uptrend-specific shorts (Exhaustion Gap, BB Squeeze Reversal, MACD Divergence) are exempted in code but still failing at activation — likely because fast-feedback suppresses them before they get trades.

**eToro constraint:** cannot short stocks intraday. Index CFDs and forex shorts work fine. Daily stock shorts work for overnight holds.

**Verdict:** Keep the uptrend-specific short templates. Prioritize F17 unblock by relaxing min_trades_dsl to 4 for this cohort temporarily.

### 2.8 Alpha Edge fundamental — KEEP, REFINE

**Evidence:** Post-Earnings Announcement Drift (PEAD):
- [SSRN 5173167 (2025)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5173167): PEAD is "one of the most prevailing anomalies in stock markets" — still alive.
- [SSRN 4751735 (2024)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4751735): PEAD declining but persistent through COVID systemic shock.
- [SSRN 4941391 (2024)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4941391): PEAD earns 5.1%/yr Democratic presidencies, 16.8%/yr Republican — cycle-sensitive.
- [SSRN 4655959 (2023)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4655959): social communication is eroding PEAD slowly.

**Our implementation:** `Post-Earnings Drift Long` uses surprise > 2%, entry 2-5 days post, RSI < 70, 8% TP / 4% SL / 20d max hold. Consistent with literature.

**Verdict:** Keep. Consider lowering `min_earnings_surprise_pct` from 2% to 4% to avoid weak signals post the social-communication erosion.

### 2.9 Structural (pairs / relative value) — KEEP, RAISE ACTIVATION

**Evidence:** [Wilkens 2024](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4807915) "Is There Still Life in the Old Dog?" — yes, stat arb pairs still generate alpha with modern methods. [Harbourfront Quant](https://harbourfrontquant.substack.com/p/modern-pairs-trading-what-still-works): modern pairs trading survives with structural-break-aware implementations.

**Our data:** Pairs Trading Market Neutral: +$327 open P&L. Relative Value: +$158. Small absolute but positive — the problem is low activation rate (noted in prompt).

**Verdict:** Investigate low activation rate — likely the DSL can't express cointegration tests natively, so the Alpha Edge bypass path is the right home for these. Raise priority of pairs-discovery logic.

### 2.10 Crypto-specialized — TRIM, REFOCUS

**Constraint:** BTC and ETH only. 40+ templates is overkill.

**Verdict:** Audit which crypto templates have ever traded. Retire zero-trade templates. Keep 10-15 winners + a few complement variants across 1h/4h/1d.

### 2.11 Commodity-specialized — KEEP initial cohort, WATCH

Our 10 commodity templates are new. Public commentary ([CBH 2026](https://www.cbh.com/insights/newsletters/alternative-investments-brief-2025-records-impact-2026-market/)) shows precious metals setting records in 2025. Too early to judge; let them accumulate live trades.

### 2.12 Hourly intraday (1h) — LET THE PIPELINE CATCH UP

We have 25 1h templates in the library and 1 BACKTESTED / 0 DEMO in the live book. **Nothing blocks 1h — it's emergent from the activation funnel, not imposed.** Contributing factors:

- `min_trades_dsl_1h = 15` vs 8 for 1d/4h — 1h needs ~2× the trade count to qualify
- WF test window is 90 days for 1h (vs 240 for 4h, 180 for 1d); fewer trades in window, fewer passes
- F07 bug: MC annualization hardcoded to 180 days regardless of timeframe — inflates 1h Sharpe by ~41%, which the strict `min_sharpe = 1.0` gate then rejects as unrealistic
- Until F02 / F26 shipped May 1, 1h data had DST crashes and stale bars — walk-forward on corrupted data produced unreliable Sharpe

**Evidence:** ORB on ES/NQ has robust backtest results ([edgeful 2026](https://www.edgeful.com/blog/posts/5-minute-opening-range-breakout-es-strategy)). Per [VWAP research](https://www.tradealgo.com/trading-guides/technical-analysis/vwap-trading-strategy-the-institutional-benchmark-every-trader-should-know), VWAP mean reversion from 2-sigma has 63% reversion rate in non-trending sessions.

**Verdict:** No direct action on templates. After F07 + Batch 4 WF fixes deploy on clean post-F02 data, let the next 1-2 autonomous cycles run and watch what graduates. If 1h count is still <5 after 2 weeks of clean data, consider lowering `min_trades_dsl_1h` to 10 or adding a 1h proposer quota. Opening Range Breakout, Hourly RSI Oversold Bounce, and Intraday Mean Reversion have the clearest published evidence.

---

## 3. Losing Templates — Per-Template Recommendation

| Template | Concept broken? | Implementation broken? | Recommendation |
|---|---|---|---|
| **Fast EMA Crossover (EMA(5)/EMA(13))** | Yes — raw MA crossover is a known retail loser at CFD spreads. Academic + practitioner evidence aligned. | Possibly (2% SL / 3% TP is tight enough that spread alone kills 1-2 trades of R) | **REMOVE.** Do not wait for post-F05 — this template has no multi-literal substitution (only 5 and 13), so F05 doesn't affect its behavior. |
| **SMA Proximity Entry** | Yes — no regime filter, fires in trending markets where the "pullback" becomes a continuation leg. | No | **REMOVE.** |
| **4H VWAP Trend Continuation** | Partially — VWAP trend continuation WORKS intraday but the template fires ADX > 18, not > 25, and the 1.2× volume filter is weak. VWAP drift on 4H bars is also a stretched concept (VWAP resets session-by-session; 4H spanning multiple sessions muddles the signal). | Yes — VWAP on 4H is conceptually dubious. | **REMOVE or REDESIGN.** If kept, redesign as 1h VWAP during active session with ADX > 22, not 4H. |
| **BB Middle Band Bounce** | Yes — crossing above BB middle band is a zero-edge signal without other confluence. | No | **REMOVE.** |
| **SMA Envelope Reversion Long** | Yes — structurally similar to SMA Proximity. | No | **REMOVE.** |
| **SMA Envelope Reversion Short** | Same as Long variant. | No | **REMOVE.** |
| **Moving Average Crossover (generic)** | Unclear pending F05 backtest. Probably borderline; ADX/volume filters may redeem it. | F05 may have been degrading behavior. | **HOLD pending post-F05 backtest.** |
| **Triple EMA Alignment** | Unknown — blocked by F05. | YES (F05 regex collision → `EMA(10) > EMA(10)` always false → 0 trades). | **HOLD; rebacktest after F05 deploy.** If still negative-edge after fix, remove. |
| **Dual MA Volume Surge** | Unclear pending F05. Volume filter is a real filter. | F05 may affect it. | **HOLD pending post-F05 backtest.** |
| **BB Midband Reversion Tight** | Yes — same pattern as BB Middle Band Bounce. | No | **REMOVE.** |

---

## 4. Gap Analysis — What Top Funds Run That We Don't

Ranked by expected alpha on a $475K eToro CFD book with our current universe.

### 4.1 ETF Sector-Rotation Momentum — **HIGH PRIORITY**

**Concept:** Rank 11 sector SPDR ETFs (XLK, XLF, XLE, XLU, XLV, XLY, XLP, XLI, XLB, XLRE, XLC) by trailing 3-6m return, go long top 3–5 on monthly rebalance, optionally short bottom 2. Classic momentum rotation, documented to deliver 3-7% annualized alpha over buy-and-hold ([TradeAlgo 2026](https://www.tradealgo.com/trading-guides/tools/sector-rotation-strategy-how-to-follow-institutional-money-in-2026); [FactSet Thematic Momentum](https://insight.factset.com/harnessing-thematic-momentum-in-portfolio-rotation-and-alpha-generation)).

**Feasibility:**
- Our universe includes all 11 SPDR sectors.
- Expressable in DSL? Partially — our DSL is per-symbol, so rank-based signals require Alpha Edge bypass pattern (similar to Sector Rotation template at line 1734). That template already exists but may have low activation.
- eToro constraint: ETFs can be held long; short-side hedge would need index CFD instead (SPY short equivalent = SPX500 short CFD).

**Sketch:**
- `Sector Rotation Momentum ETF`: monthly-recomputed (rebalance trigger every 21 trading days), top-3 sector ETFs by 3-month return, long with BASE_RISK_PCT × 1.5. Hedge with 1 small SPX500 short at 0.5× of any one long if regime is TRENDING_UP_WEAK.

**Priority:** HIGH. $475K × 15% turnover per rebalance = $70K across 3 ETFs = feasible.

### 4.2 Volatility-Targeted Position Overlay (GARCH-lite) — **HIGH PRIORITY**

**Concept:** GARCH(1,1) or EWMA realized-vol forecast on SPY, recomputed nightly, used as a multiplier on position sizes. When SPY vol > 20% annualized, scale existing 0.10-1.50× vol scaler DOWN by another 0.5. During the April 2025 vol spike this would have saved meaningful drawdown ([Man Group Volatility Targeting](https://www.man.com/insights/the-impact-of-volatility-targeting)).

**Feasibility:**
- Not a template — this is a sizing overlay in `position_sizing` / `order_executor`.
- Current system has `target_vol: 16%` and 0.10–1.50× scaling; extend to incorporate forward-looking GARCH estimate, not just trailing realized.

**Sketch:**
- In `risk_service`, compute EWMA(60) of SPY daily log returns with decay 0.94 (RiskMetrics standard).
- `vol_adj = min(1.0, target_vol / forecast_vol)`
- Apply as additional multiplier after existing vol scaling.

**Priority:** HIGH. Reduces drawdown in vol events — Audit Alpha Generation Opportunity #4.

### 4.3 VIX Regime Gate at Signal Time — **MEDIUM PRIORITY**

**Concept:** Our MQS uses VIX for 10 points of the 0-100 score, but the gate is coarse (choppy < 40 → block trend LONG). Add a signal-time VIX check: when VIX > 25 AND rising > 10% day-over-day, skip any new trend LONG entries for 24h. Related: High-VIX Mean Reversion Long template exists.

**Evidence:** [Bilello research](https://finance.yahoo.com/news/why-the-vix-spike-may-be-a-bullish-stock-market-indicator-135902073.html): after 3-day VIX spikes of 63-176%, 1yr forward S&P return averaged only 4.4% — vol spikes mark turning points.

**Feasibility:** Already in conviction_scorer as an MQS component; add as hard gate at order_executor before LONG entry.

**Priority:** MEDIUM. Audit Alpha Generation Opportunity #4/#7.

### 4.4 Commodity Trend-Following with Term-Structure Tilt — **MEDIUM PRIORITY**

**Concept:** AQR Helix returned 18.6% in 2025 partly from commodity trend. Our commodity templates are new; augment with a term-structure carry tilt: when oil/gas curves are in backwardation, prefer long; in contango, prefer short or neutral.

**Feasibility:**
- eToro provides spot commodity CFDs but **not the full futures curve**. We can't directly observe front-month vs second-month spread for oil/gas.
- Workaround: use USO vs UNG ETF behavior as a proxy — limited but possible.

**Priority:** MEDIUM. Commodity trend alone (without term structure) is already our starting cohort; upgrade when we can access curve data.

### 4.5 Cross-Sectional Equity Long-Short — **LOW PRIORITY (infeasible direct)**

**Concept:** Rank 232 stocks by composite factor (value + quality + momentum), long top decile, short bottom decile.

**Feasibility:** **BLOCKED on eToro.** Cannot short stocks intraday. Can only do stock shorts as overnight CFD holds, and those are the most expensive spreads. A 232-stock decile basket = ~23 positions per side, each at $2K-5K; spread + financing cost alone would eat any factor alpha.

**Alternative:** Collapse to sector-ETF decile (4.1 above) or keep as Alpha Edge fundamental single-stock long-only basket (which is what our Multi-Factor Composite already does).

**Priority:** LOW / SKIP. Covered by 4.1.

### 4.6 News/Earnings-Driven Systematic Entry with NLP — **LOW PRIORITY**

**Concept:** News sentiment → systematic entry on earnings-related news with positive sentiment.

**Feasibility:** We already have `news_sentiment_provider` — check if it's integrated into conviction scoring or Alpha Edge templates. Current audit notes a ±1 contribution to conviction; that's token influence.

**Priority:** LOW. The effect size is small at our capital level, and NLP-driven entries require high-quality news data feed. Our current FMP news is adequate for context but not driving-signal quality.

### 4.7 VIX Term-Structure Carry (short-vol) — **DO NOT ADD**

**Concept:** Short VIX front-month futures when curve is in contango. 10% annualized return most years but 80% crash in 2018 ([navnoorbawa substack](https://navnoorbawa.substack.com/p/the-volatility-carry-trade-how-selling)).

**Feasibility:** eToro offers VIXX / VXX CFDs but the margin and slippage mean retail-CFD short-vol has wiped out accounts historically (XIV termination 2018). With our $475K book, a single tail event wipes years of edge.

**Priority:** DO NOT ADD. Anti-recommendation.

### 4.8 Options-Implied Volatility Signals — **DO NOT ADD**

**Concept:** Use implied vol skew, term structure, put/call ratios as leading signals.

**Feasibility:** We don't have options data in our stack, and eToro doesn't offer liquid options trading on most underlyings. Even as an *input* signal to stock-direction trades, vol surface data is expensive.

**Priority:** DO NOT ADD. Anti-recommendation.

### 4.9 Intraday (1h) Mean Reversion on High-Volume Names — **MEDIUM PRIORITY**

**Concept:** VWAP mean reversion from 2-sigma extensions on liquid large-caps. [crosstrade.io](https://crosstrade.io/learn/trading-strategies/vwap-reversion): "mean-reversion strategy ... works best on ES and NQ during non-event days." Per [VWAP research](https://www.tradealgo.com/trading-guides/technical-analysis/vwap-trading-strategy-the-institutional-benchmark-every-trader-should-know), 63% reversion rate from 2-std VWAP extensions.

**Feasibility:**
- We already have Intraday Mean Reversion template.
- Needs 1h strategies to be live (currently zero active).
- Needs regime filter (the "non-event days" caveat is real — trends break this strategy).

**Priority:** MEDIUM. Reactivate after Batch 4.

### 4.10 Small-Book Pairs Basket (ETF Pairs) — **MEDIUM PRIORITY**

**Concept:** 3-5 cointegrated ETF pairs (e.g., XLK/XLY, QQQ/SPY, GLD/GDX) as market-neutral book. Capital-efficient because net beta ~0.

**Feasibility:**
- Our 42 ETFs includes enough candidates.
- Existing "Pairs Trading Market Neutral" template (+$327 open P&L) confirms feasibility but low activation.
- eToro allows long and short on ETFs (short sleeve via index CFDs if needed).

**Sketch:**
- Cointegration-tested pairs list maintained in config.
- Entry: Z-score of spread > 2.0; exit: Z-score crosses 0.
- Capital: equal-dollar long and short, $5-10K per side, 3-5 pairs = $30-75K deployment.

**Priority:** MEDIUM. Alpha Generation Opportunity #3 in audit.

---

## 5. Additions — Full Table

| Family | Concept | Evidence | DSL or Alpha Edge | Implementation Sketch | Priority |
|---|---|---|---|---|---|
| **ETF Sector-Rotation Momentum** | Monthly rebalance top-3 sector ETFs by 3m return | [TradeAlgo 2026](https://www.tradealgo.com/trading-guides/tools/sector-rotation-strategy-how-to-follow-institutional-money-in-2026), [FactSet](https://insight.factset.com/harnessing-thematic-momentum-in-portfolio-rotation-and-alpha-generation) | **Alpha Edge** (rank-based) | Modify existing `Sector Rotation` template to actually activate; rebalance trigger every 21 days; top-3 by ret_63 | HIGH |
| **Volatility-Targeted Sizing Overlay** | EWMA(60) vol forecast; multiplicative size scaler | [Man Group](https://www.man.com/insights/the-impact-of-volatility-targeting), [arxiv](https://arxiv.org/html/2410.14841v1) | **Infra (not template)** | In `risk_service`, compute EWMA daily vol; append `vol_adj = min(1.0, 16% / forecast)` to existing sizing chain | HIGH |
| **VIX Signal-Time Gate** | Block LONG entry when VIX rising + VIX > 25 | [Bilello](https://finance.yahoo.com/news/why-the-vix-spike-may-be-a-bullish-stock-market-indicator-135902073.html) | **Infra (order_executor gate)** | Pre-flight check: `if VIX > 25 and VIX_5d_return > 0.15: reject LONG entries` for equity/ETF strategies | MEDIUM |
| **Momentum Crash Circuit Breaker** | Suppress momentum longs post-drawdown | [Byun & Jeon](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2900073) | **Infra (conviction)** | Add `if SPY_5d < -3% AND VIX rising: momentum_regime_score = -50` | MEDIUM |
| **ETF Pairs Basket (market-neutral)** | 3-5 cointegrated ETF pairs | [Wilkens 2024](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4807915) | **Alpha Edge** | Curate 5 cointegrated pairs in config; spread Z-score signal; ensure activation not dependent on single-symbol trade threshold | MEDIUM |
| **Confirmed Momentum Enhancement (existing PEAD)** | Lower PEAD surprise threshold + require operating momentum (revenue growth > 8%) | [Lord Abbett](https://www.lordabbett.com/en-us/financial-advisor/insights/investment-objectives/2025/the-benefits-of-price-and-operating-momentum-in-equity-portfolios.html), [SSRN 5173167](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5173167) | **Alpha Edge** | Modify existing `Post-Earnings Drift Long`: min surprise 2% → 4%, add `revenue_growth_qoq > 0.08` predicate | MEDIUM |

---

## 6. Anti-Recommendations

Things that sound good but won't work on a $475K eToro CFD book.

| Proposal | Why it fails |
|---|---|
| **Cross-sectional stock long-short (long top decile / short bottom decile)** | eToro does not offer intraday stock shorting. Overnight CFD shorts are priced at retail spreads + financing; any factor alpha is eaten. Only works at prime-broker cost structure. **Sector-ETF substitute (§4.1) gets most of the alpha at CFD-viable cost.** |
| **Short VIX carry (short VXX / front-month VX futures)** | 2018 XIV termination wiped retail accounts overnight. Tail risk not worth 10%/yr expected. Not suitable for any retail CFD account. |
| **Options-implied volatility signals as a primary input** | No access to options chain data in our stack; eToro doesn't offer options trading; vol surface data providers cost thousands/month. ROI negative at our capital level. |
| **Sub-hour (5min / 15min) mean reversion** | Our DSL is 1h minimum. Even if we added a sub-hour timeframe, eToro fills are at touch with delay — execution alone kills any 5min mean-reversion edge. |
| **52-week high momentum as an unfiltered cross-sectional basket** | Even though 52WH is validated, the basket size needed for the anomaly to stabilize is hundreds of stocks, and the crash risk documented by [Byun & Jeon](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2900073) means that without a circuit breaker, one bad drawdown destroys 2 years of returns. Our existing `52-Week High Momentum Long` template on a small megacap list is fine; don't scale to the full 232-stock universe. |
| **Block-trading / basket futures** | Below prime-broker scale. Our $475K can't execute block basket futures. |
| **Machine-learning alpha mining on alternative data (credit card, satellite, foot traffic)** | Data feeds cost $50K-$500K/year; retail CFD execution quality means model gains are below transaction costs. Public alt-data is already commoditized ([arxiv alpha decay](https://arxiv.org/abs/2512.11913v1)). Stick to FMP + Yahoo + news for signal inputs. |
| **Running 150+ templates at once (current state)** | F01/F12 showed test > train by 1.92 Sharpe on average — this is a direct symptom of too-broad testing leading to selection bias. Fewer, higher-conviction templates outperform the kitchen-sink approach. Pruning the losers (§3) directly improves the selection-bias profile. |
| **HFT / market-making** | Not possible on retail CFD. Requires co-location and tick data. |
| **Short-term reversal (1-week mean reversion on individual stocks)** | High turnover, retail spreads kill it, and 1-week stock reversal is the most-crowded factor at hedge-fund level. |

---

## 7. Recommended Sequencing (for follow-on session)

Ordered to stack with Batch 4:

1. **After F05 deploys** (substitution fix): re-backtest Triple EMA Alignment, Moving Average Crossover, Dual MA Volume Surge. Decide keep/remove from fresh data.
2. **Alongside F08 fix** (fast-feedback on open-book P&L): remove Fast EMA Crossover, SMA Proximity Entry, BB Middle Band Bounce, SMA Envelope Reversion Long/Short, BB Midband Reversion Tight — this stops the 7-template drag identified in the loser cohort.
3. **Unblock F17**: relax `min_trades_dsl` for uptrend-specific shorts to 4, seed 2-3 index/ETF shorts.
4. **Add volatility-targeted sizing overlay** (infra change in `risk_service`).
5. **Activate Sector Rotation template** (exists but low activation) with proper rank-based Alpha Edge integration.
6. **After Batch 4 stabilises** (not a new action — just observation): watch whether 1h strategies start graduating now that F02/F26 give clean 1h data and F07 fixes the Sharpe inflation. Intervene (lower `min_trades_dsl_1h` or add quota) only if <5 1h active after 2 weeks.
7. **Add ETF Pairs basket** (5 cointegrated pairs) once pairs trading discovery logic is instrumented.
8. **Refine PEAD** with operating-momentum confirmation (revenue growth ≥ 8% QoQ predicate).

---

## Sources

Content from external sources was rephrased and summarized for compliance with licensing restrictions. Inline links preserved in each section.

- AQR public research, disclosure, and 2025 fund performance commentary: https://funds.aqr.com/funds/aqr-trend-total-return-fund, https://www.aqr.com/Learning-Center/Systematic-Equities, https://funanc1al.com/blogs/follow-the-pundits/aqr-capital-s-2025-scorecard-from-applied-quantitative-research-to-actually-quality-returns
- Man Group research on vol-targeting and regime-based investing: https://www.man.com/insights/the-impact-of-volatility-targeting, https://www.man.com/insights/road-ahead-regime-based-investing
- SSRN working papers (PEAD, 52WH, pairs, alpha decay) published 2023–2025: 5173167, 4751735, 4941391, 4655959, 4587697, 2900073, 4122300, 4807915, 5186655
- arxiv papers on cross-sectional predictability, factor allocation, alpha decay: 2511.12490, 2410.14841, 2512.11913
- Hedge fund press 2025–2026: HedgeCo April 2026 coverage, Institutional Investor CTA coverage, CBH Alternative Investments 2026
- Practitioner research: Lord Abbett (Nov 2025), FactSet Thematic Momentum, TradeAlgo Sector Rotation 2026, crosstrade.io, edgeful.com, orbstats.com
- Macro context: TIAA 2026 annual outlook, Natixis 2026 Regime note

All content was paraphrased; no single source exceeds 30 consecutive words.
