# Bugfix Requirements Document

## Introduction

Intraday and hourly strategies are systematically failing to activate and generate signals in the autonomous trading system. The root cause is that activation and walk-forward validation thresholds are calibrated for daily strategies and are too strict for shorter timeframes. Hourly strategies with Sharpe ratios of 0.68-0.81 and win rates of 75% are being rejected despite being statistically significant for their timeframe. Additionally, intraday strategies show severe walk-forward overfitting (train Sharpe 2.27 vs test 0.16), and 1H signal generation consistently produces zero signals despite 52 active hourly strategies.

The bug affects the entire lifecycle of intraday/hourly strategies:
- Walk-forward validation rejects strategies with timeframe-appropriate metrics
- Activation thresholds (Sharpe 0.9, win rate 45%) are too high for hourly data
- Signal generation fails to produce signals for activated hourly strategies
- Retirement checks eventually kill all intraday/hourly strategies

This fix will implement timeframe-aware thresholds that recognize the statistical properties of shorter timeframes (lower Sharpe ratios, different win rate distributions) while maintaining quality standards.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a hourly strategy achieves Sharpe ratio 0.68-0.81 with 75% win rate THEN the system rejects it with message "Sharpe 0.81 < 0.9" despite strong performance for the timeframe

1.2 WHEN an intraday strategy is validated using walk-forward THEN the system applies daily-calibrated thresholds (min_sharpe 0.3, min_win_rate 0.45) causing severe overfitting (train=2.27, test=0.16)

1.3 WHEN 1H signal generation runs with 52 active hourly strategies THEN the system produces "52 strategies | 0 signals | 0 orders" consistently

1.4 WHEN hourly strategies pass walk-forward validation THEN the system still rejects them at activation due to Sharpe threshold 0.9 being too high for hourly timeframes

1.5 WHEN intraday strategies are evaluated for retirement THEN the system applies daily-calibrated thresholds causing premature retirement of timeframe-appropriate performers

1.6 WHEN the system detects strategy timeframe THEN it fails to adjust average loss checks (3x stop-loss) and win rate requirements (45%) for intraday volatility patterns

### Expected Behavior (Correct)

2.1 WHEN a hourly strategy achieves Sharpe ratio 0.6+ with 40%+ win rate THEN the system SHALL activate it recognizing these are strong metrics for hourly timeframes

2.2 WHEN an intraday strategy is validated using walk-forward THEN the system SHALL apply timeframe-aware thresholds (relaxed Sharpe, adjusted win rate) to prevent overfitting while allowing legitimate intraday patterns

2.3 WHEN 1H signal generation runs with active hourly strategies THEN the system SHALL generate signals when hourly conditions are met using appropriate indicator calculations

2.4 WHEN hourly strategies pass walk-forward validation with timeframe-appropriate metrics THEN the system SHALL activate them without applying daily-calibrated thresholds

2.5 WHEN intraday strategies are evaluated for retirement THEN the system SHALL apply timeframe-aware thresholds that account for the statistical properties of shorter timeframes

2.6 WHEN the system detects strategy timeframe THEN it SHALL adjust average loss checks, win rate requirements, and risk parameters based on intraday volatility characteristics

### Unchanged Behavior (Regression Prevention)

3.1 WHEN daily strategies are validated using walk-forward THEN the system SHALL CONTINUE TO apply existing thresholds (min_sharpe 0.3, min_win_rate 0.45)

3.2 WHEN daily strategies are evaluated for activation THEN the system SHALL CONTINUE TO use existing Sharpe threshold 0.9 and win rate 45%

3.3 WHEN 4H strategies are processed THEN the system SHALL CONTINUE TO use existing thresholds as they are working correctly

3.4 WHEN strategies in ranging_low_vol regime are evaluated THEN the system SHALL CONTINUE TO apply regime-aware threshold relaxation

3.5 WHEN crypto strategies are evaluated THEN the system SHALL CONTINUE TO use min_sharpe_crypto (0.2) and min_win_rate_crypto (0.3) thresholds

3.6 WHEN Alpha Edge strategies are evaluated THEN the system SHALL CONTINUE TO use relaxed thresholds (Sharpe 0.2, win rate 35%)

3.7 WHEN signal generation runs for daily strategies THEN the system SHALL CONTINUE TO produce signals using existing indicator calculation logic
