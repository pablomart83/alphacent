# Task 9.5: Fix Critical Integration Issues

## Purpose

Address the critical issues discovered in Task 9 integration testing that prevent strategies from generating actual trades and producing meaningful backtest results.

## Problem Statement

The integration test revealed that while the autonomous system architecture works correctly, the strategies are not functional:
- **Zero trades generated** in backtests
- **Insufficient historical data** (39 days vs 90 required)
- **Indicator naming mismatches** between LLM and indicator library
- **Market regime defaulting** to RANGING instead of real detection

## Task Breakdown

### 9.5.1 Implement eToro Historical Data Fetching (1-2 hours)

**Problem:** eToro client missing `get_historical_data()` method, forcing fallback to Yahoo Finance which only returns 39 days.

**Solution:**
- Implement proper eToro API historical data endpoint
- Support 90+ days of data
- Maintain Yahoo Finance as fallback

**Success Criteria:**
- Can fetch 90 days of OHLCV data from eToro
- Data format standardized
- Fallback works if eToro fails

---

### 9.5.2 Standardize Indicator Naming Convention (2-3 hours)

**Problem:** LLM generates references like `SMA_20`, `RSI_14` but indicator library returns `SMA`, `RSI`, causing runtime errors and fragile patching.

**Solution:**
- Define standard: `{indicator}_{period}` format
- Update indicator library to return standardized keys
- Update LLM prompts with exact naming examples
- Remove runtime patching code
- Add validation to reject invalid references

**Success Criteria:**
- No indicator key errors in logs
- No "attempting to fix" warnings
- LLM and indicator library use same names

---

### 9.5.3 Add Strategy Signal Validation (1-2 hours)

**Problem:** Strategies are backtested even when they generate zero signals, wasting time and producing meaningless results.

**Solution:**
- Add pre-backtest validation step
- Quick 30-day signal generation test
- Require at least 1 entry and 1 exit signal
- Skip backtesting if validation fails
- Log detailed errors for debugging

**Success Criteria:**
- Only strategies that generate signals are backtested
- Invalid strategies logged with reasons
- Backtest results always have trades > 0

---

### 9.5.4 Improve Market Regime Detection (1 hour)

**Problem:** Requires 60 days but only gets 39, so defaults to RANGING without real analysis.

**Solution:**
- Reduce minimum to 30 days (more realistic)
- Add data quality scoring (EXCELLENT/GOOD/FAIR/POOR)
- Only default to RANGING if data is POOR
- Use real analysis for FAIR or better
- Log data quality in cycle stats

**Success Criteria:**
- Market regime based on actual analysis when 30+ days available
- Data quality visible in logs
- System warns when data quality is poor

---

### 9.5.5 Re-run Integration Test & Verify (30 min + iteration)

**Problem:** Need to verify all fixes work together and produce meaningful results.

**Solution:**
- Run `test_e2e_autonomous_system.py` again
- Verify all improvements
- Document results
- Iterate if needed

**Success Criteria:**
- ✅ 90+ days of historical data fetched
- ✅ No indicator naming errors
- ✅ Market regime detected (not defaulted)
- ✅ Strategies generate signals (trades > 0)
- ✅ Backtest results meaningful (Sharpe not inf)
- ✅ At least 1 strategy meets activation criteria

---

## Total Estimated Time: 4-6 hours

## Priority: P0 (Blocks Frontend Development)

These issues must be fixed before Task 10 (Frontend Integration) because:
1. Frontend will display backtest results (currently meaningless)
2. Frontend will show market regime (currently guessed)
3. Frontend will show strategy signals (currently zero)
4. Users will see "inf" Sharpe ratios and 0% returns (bad UX)

## Expected Outcome

After completing Task 9.5:
- Strategies generate 20+ trades in 90-day backtests
- Backtest results show realistic Sharpe ratios (0.5 - 3.0 range)
- Market regime accurately detected
- At least 1-2 strategies meet activation criteria
- System ready for frontend integration

## Risk Mitigation

If eToro historical data is not available:
- Keep Yahoo Finance as primary
- Adjust data requirements to 30 days minimum
- Add data quality warnings to UI
- Consider alternative data sources (Alpha Vantage, IEX Cloud)

## Next Steps After Completion

1. Verify all tests pass
2. Document improvements in `TASK_9.5_VERIFICATION.md`
3. Proceed to Task 10 (Frontend Integration)
4. Deploy to production with confidence
