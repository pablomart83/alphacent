# ML Signal Filter Retraining Plan
**Date Created**: February 23, 2026  
**Target Re-enable Date**: August 23, 2026 (6 months)  
**Status**: DISABLED - Collecting production data

---

## Why ML Filter is Disabled

### Current Issues
1. **Rejecting all signals**: 100% rejection rate (confidence 0.426 < 0.55)
2. **Insufficient training data**: Model trained on limited historical data
3. **Attribute error bug**: `'TradingSignal' object has no attribute 'signal_type'`
4. **Poor generalization**: Model doesn't reflect current market conditions

### Decision
Disable ML filter temporarily to:
- Allow system to generate signals and collect production data
- Build a robust dataset of real trades with outcomes
- Fix the attribute error bug
- Retrain model with 6+ months of production data

---

## Data Collection Requirements (6 Months)

### Minimum Data Needed
- **Trades**: 200+ completed trades (entry + exit)
- **Signals**: 1,000+ signals generated (both accepted and rejected by other filters)
- **Outcomes**: Win/loss, profit/loss, holding period for each trade
- **Features**: All 8 features captured for each signal:
  - rsi_14
  - macd_signal
  - volume_ratio
  - price_vs_ma_50
  - price_vs_ma_200
  - sector_momentum
  - market_regime
  - vix_level

### Data Quality Requirements
- **Market conditions**: Data should span multiple market regimes (trending, ranging, volatile)
- **Strategy diversity**: Data from multiple strategy types (momentum, mean-reversion, trend-following)
- **Symbol diversity**: Data from stocks, ETFs, indices, forex
- **Time diversity**: Data from different times of day, days of week, market conditions

---

## Retraining Process (Month 6)

### Step 1: Data Preparation (Week 1)
```bash
# Extract training data from database
python scripts/ml/extract_training_data.py --start-date 2026-02-23 --end-date 2026-08-23

# Validate data quality
python scripts/ml/validate_training_data.py

# Split data: 70% train, 15% validation, 15% test
python scripts/ml/split_training_data.py --train 0.7 --val 0.15 --test 0.15
```

**Expected Output**:
- `data/ml/training_data.csv` (1,000+ signals)
- `data/ml/trade_outcomes.csv` (200+ trades)
- Data quality report

### Step 2: Feature Engineering (Week 1-2)
```python
# Review feature importance from old model
python scripts/ml/analyze_feature_importance.py

# Add new features if needed:
# - Recent strategy performance
# - Signal strength score
# - Fundamental quality score
# - Market volatility (VIX)
# - Sector rotation signals
```

### Step 3: Model Training (Week 2)
```bash
# Train multiple models and compare
python scripts/ml/train_signal_filter.py --models rf,xgboost,lightgbm

# Hyperparameter tuning
python scripts/ml/tune_hyperparameters.py --model rf --trials 100

# Cross-validation
python scripts/ml/cross_validate.py --folds 5
```

**Target Metrics**:
- **Precision**: >70% (signals predicted as good are actually profitable)
- **Recall**: >60% (catch most profitable signals)
- **F1 Score**: >0.65
- **ROC AUC**: >0.75

### Step 4: Backtesting (Week 3)
```bash
# Backtest new model on held-out test set
python scripts/ml/backtest_ml_filter.py --model models/ml/signal_filter_v2.pkl

# Compare with no-filter baseline
python scripts/ml/compare_filter_performance.py
```

**Success Criteria**:
- Sharpe ratio improvement: >10%
- Win rate improvement: >5%
- Drawdown reduction: >10%
- Signal rejection rate: 30-50% (not 100%!)

### Step 5: A/B Testing (Week 4)
```bash
# Deploy model to 50% of strategies
python scripts/ml/deploy_ab_test.py --model v2 --percentage 50

# Monitor for 1 week
python scripts/ml/monitor_ab_test.py --days 7

# Compare performance
python scripts/ml/analyze_ab_test.py
```

### Step 6: Full Deployment (Week 4)
If A/B test successful:
```yaml
# config/autonomous_trading.yaml
ml_filter:
  enabled: true
  min_confidence: 0.50  # Adjusted based on retraining
  model_version: v2
  retrain_frequency_days: 90  # Retrain quarterly
```

---

## Monitoring After Re-enable

### Daily Checks
- Signal rejection rate (target: 30-50%)
- ML confidence distribution
- False positive rate (signals that passed but lost money)
- False negative rate (signals that were rejected but would have won)

### Weekly Checks
- Model performance vs baseline
- Feature drift detection
- Prediction calibration

### Monthly Checks
- Retrain model if:
  - Rejection rate >70% or <20%
  - Win rate of accepted signals <50%
  - Significant feature drift detected
  - New market regime not seen in training data

---

## Alternative: Gradual Re-enable

Instead of waiting 6 months, consider gradual re-enable:

### Month 3 (May 2026)
- **Data collected**: ~100 trades, ~500 signals
- **Action**: Train preliminary model with lower confidence threshold
- **Config**: `enabled: true, min_confidence: 0.35`
- **Purpose**: Soft filter that only rejects very low-quality signals

### Month 6 (August 2026)
- **Data collected**: ~200 trades, ~1,000 signals
- **Action**: Retrain with full dataset, increase threshold
- **Config**: `enabled: true, min_confidence: 0.50`
- **Purpose**: Full filter with production-calibrated threshold

### Month 9 (November 2026)
- **Data collected**: ~300 trades, ~1,500 signals
- **Action**: Final retrain with extended dataset
- **Config**: `enabled: true, min_confidence: 0.55`
- **Purpose**: Mature filter with high confidence threshold

---

## Bug Fixes Required Before Re-enable

### Fix 1: Attribute Error
```python
# src/ml/signal_filter.py - Line ~168
def _log_filter_result(self, signal: TradingSignal, strategy: Strategy, result: MLFilterResult) -> None:
    try:
        # Fix: Use hasattr to check for signal_type
        signal_type = signal.signal_type if hasattr(signal, 'signal_type') else signal.action
        
        self.db.execute("""
            INSERT INTO ml_filter_results 
            (signal_id, strategy_id, symbol, signal_type, confidence, passed, features, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal.id,
            strategy.id,
            signal.symbol,
            signal_type,  # Use the safe variable
            result.confidence,
            result.passed,
            json.dumps(result.features),
            datetime.now(timezone.utc)
        ))
    except Exception as e:
        logger.error(f"Failed to log ML filter result: {e}")
```

### Fix 2: Add signal_type to TradingSignal
```python
# src/models/trading_signal.py
class TradingSignal:
    def __init__(self, ...):
        # ... existing fields ...
        self.signal_type = action  # Add this line
```

---

## Success Metrics

### Before Re-enable (Current State)
- Signal rejection rate: 100% ❌
- Signals passing all filters: 0
- ML filter confidence: 0.426 (too low)

### After Re-enable (Target State)
- Signal rejection rate: 30-50% ✅
- Signals passing all filters: 50-70% of generated signals
- ML filter confidence: 0.50-0.80 (well-calibrated)
- Win rate improvement: +5-10% vs no-filter baseline
- Sharpe ratio improvement: +10-15% vs no-filter baseline

---

## Checklist for Re-enable

- [ ] 6 months of production data collected (or 3 months for gradual approach)
- [ ] Minimum 200 completed trades in database
- [ ] Minimum 1,000 signals with features captured
- [ ] Attribute error bug fixed
- [ ] Model retrained with production data
- [ ] Backtest shows >10% Sharpe improvement
- [ ] A/B test shows positive results
- [ ] Monitoring dashboard created
- [ ] Alert thresholds configured
- [ ] Rollback plan documented

---

## Rollback Plan

If ML filter causes issues after re-enable:

1. **Immediate**: Set `enabled: false` in config
2. **Investigate**: Check rejection rate, confidence distribution, false positives
3. **Adjust**: Lower threshold or retrain model
4. **Re-test**: Run A/B test again
5. **Document**: Update this plan with lessons learned

---

## Contact & Review

**Review Date**: August 15, 2026 (1 week before target re-enable)  
**Responsible**: ML/Trading team  
**Stakeholders**: Risk management, Trading operations

**Questions to Answer at Review**:
1. Do we have sufficient data quality and quantity?
2. Has the model been retrained and validated?
3. Are all bugs fixed?
4. Is monitoring infrastructure ready?
5. Is the team comfortable with re-enabling?

---

**Status Updates**:
- **Feb 23, 2026**: ML filter disabled, data collection started
- **May 23, 2026**: (Planned) 3-month review, consider gradual re-enable
- **Aug 15, 2026**: (Planned) 6-month review, prepare for full re-enable
- **Aug 23, 2026**: (Planned) Full re-enable with production-trained model
