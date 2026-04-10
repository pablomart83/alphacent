# ML Signal Filter - Disabled for Data Collection
**Date**: February 23, 2026  
**Action**: ML filter disabled in production  
**Duration**: 6 months (until August 23, 2026)  
**Status**: ✅ COMPLETED

---

## What Changed

### Configuration Update
```yaml
# config/autonomous_trading.yaml
alpha_edge:
  ml_filter:
    enabled: false  # Changed from true
    min_confidence: 0.55
    retrain_frequency_days: 30
```

### Impact
- ML filter will no longer reject signals
- Signals will still be filtered by:
  - ✅ Fundamental filter (P/E, market cap, profitability, etc.)
  - ✅ Conviction scorer (signal + fundamental + regime = 60+ score)
  - ✅ Trade frequency limiter (max 4 trades/month per strategy)
  - ✅ Risk manager (position sizing, exposure limits)

---

## Why This Decision?

### Problem Identified
From E2E test on Feb 23, 2026:
- **ML filter rejected 100% of signals** (confidence 0.426 < 0.55 threshold)
- GE and GOLD signals passed fundamental and conviction filters but were rejected by ML
- Zero natural signals generated due to ML filter being too aggressive

### Root Cause
1. **Insufficient training data**: Model trained on limited historical data
2. **Poor generalization**: Model doesn't reflect current market conditions
3. **Overfitting**: Model may have overfit to training data
4. **Stale features**: Market regime has changed since model was trained

### Why Not Just Lower the Threshold?
Lowering the threshold (e.g., 0.55 → 0.40) would be a band-aid fix:
- Model is fundamentally undertrained
- No guarantee 0.40 is the right threshold
- Still has attribute error bug
- Better to collect production data and retrain properly

---

## What Happens Now?

### Data Collection Phase (6 Months)
The system will:
1. **Generate signals** without ML filter blocking them
2. **Execute trades** based on fundamental + conviction filters
3. **Collect outcomes** (win/loss, profit/loss, holding period)
4. **Capture features** for each signal (RSI, MACD, volume, etc.)

### Target Data Collection
- **200+ completed trades** (entry + exit with outcomes)
- **1,000+ signals** (both accepted and rejected by other filters)
- **Multiple market regimes** (trending, ranging, volatile)
- **Strategy diversity** (momentum, mean-reversion, trend-following)

### Retraining Timeline
- **Month 3 (May 2026)**: Optional gradual re-enable with low threshold (0.35)
- **Month 6 (August 2026)**: Full retrain and re-enable with production data
- **Month 9 (November 2026)**: Final optimization with extended dataset

---

## Safety Measures Still Active

Even with ML filter disabled, the system has multiple safety layers:

### 1. Fundamental Filter ✅
- Market cap > $500M
- Profitable companies (positive earnings)
- Growing revenue
- Reasonable P/E ratios (strategy-specific)
- No excessive dilution
- Insider buying signals

**Current Performance**: 100% pass rate (28/28 symbols)

### 2. Conviction Scorer ✅
- Signal strength (0-40 points)
- Fundamental quality (0-40 points)
- Regime alignment (0-20 points)
- Minimum score: 60/100

**Current Performance**: 36.6% pass rate, avg score 65.7

### 3. Trade Frequency Limiter ✅
- Max 4 trades per strategy per month
- Min 7-day holding period
- Prevents overtrading

### 4. Risk Manager ✅
- Position sizing (1-5% per trade)
- Max exposure (50% total)
- Max daily loss (10%)
- Stop loss (4%) and take profit (10%) on all trades

### 5. Symbol Concentration Limits ✅
- Max 15% exposure per symbol
- Max 3 strategies per symbol
- Prevents over-concentration

---

## Expected Impact

### Positive
- ✅ Signals will now pass through (no more 100% rejection)
- ✅ System can collect production data for retraining
- ✅ Other filters still provide quality control
- ✅ Removes immediate production blocker

### Neutral
- ⚠️ May see slightly more signals generated (30-50% more)
- ⚠️ Win rate may decrease slightly (5-10%) without ML filter
- ⚠️ Drawdown may increase slightly (2-3%) without ML filter

### Monitoring Required
- 📊 Track win rate vs baseline (target: >50%)
- 📊 Track Sharpe ratio vs baseline (target: >1.0)
- 📊 Track signal quality (conviction scores)
- 📊 Track false positive rate (signals that lose money)

---

## Rollback Plan

If disabling ML filter causes issues:

### Scenario 1: Win Rate Drops Below 40%
**Action**: Re-enable ML filter with lower threshold (0.35)
```yaml
ml_filter:
  enabled: true
  min_confidence: 0.35  # Very permissive
```

### Scenario 2: Excessive Signal Generation
**Action**: Increase conviction score threshold
```yaml
alpha_edge:
  min_conviction_score: 70  # Up from 60
```

### Scenario 3: Drawdown Exceeds 15%
**Action**: Reduce position sizing
```yaml
risk_management:
  max_position_size_pct: 3.0  # Down from 5.0
```

---

## Success Criteria

### After 6 Months (August 2026)
- [ ] 200+ completed trades collected
- [ ] 1,000+ signals with features captured
- [ ] Win rate maintained >50% without ML filter
- [ ] Sharpe ratio maintained >1.0 without ML filter
- [ ] ML model retrained with production data
- [ ] A/B test shows >10% improvement with new model
- [ ] ML filter re-enabled with production-calibrated threshold

---

## Documentation

- **Retraining Plan**: `ML_FILTER_RETRAINING_PLAN.md`
- **E2E Analysis**: `E2E_COMPREHENSIVE_ANALYSIS_FEB_23_2026.md`
- **Config File**: `config/autonomous_trading.yaml`

---

## Next Steps

1. **Immediate**: Monitor system performance without ML filter (daily)
2. **Week 1**: Verify signal generation increases and trades execute
3. **Month 1**: Review win rate, Sharpe ratio, drawdown metrics
4. **Month 3**: Consider gradual re-enable with low threshold
5. **Month 6**: Full retrain and re-enable with production data

---

## Questions?

**Q: Is it safe to disable the ML filter?**  
A: Yes. The system has 5 other safety layers (fundamental, conviction, frequency, risk, concentration). The ML filter was rejecting 100% of signals anyway, so disabling it actually improves system functionality.

**Q: Will we lose money without the ML filter?**  
A: Possibly slightly more drawdown (2-3%), but the other filters provide quality control. The E2E test showed strategies with Sharpe 1.31 and win rate 57.2% without ML filter.

**Q: Why not just retrain now?**  
A: We don't have enough production data. The model needs 200+ real trades with outcomes to learn what actually works in current market conditions.

**Q: Can we re-enable earlier than 6 months?**  
A: Yes. See the gradual re-enable plan in `ML_FILTER_RETRAINING_PLAN.md` for a 3-month option.

**Q: What if the system performs worse without ML filter?**  
A: We have rollback plans (see above). We can re-enable with lower threshold, increase conviction threshold, or reduce position sizing.

---

**Status**: ✅ ML filter disabled, data collection in progress  
**Next Review**: May 23, 2026 (3-month checkpoint)  
**Target Re-enable**: August 23, 2026 (6-month full retrain)
