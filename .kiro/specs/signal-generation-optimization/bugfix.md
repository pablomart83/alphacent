# Bugfix Requirements Document

## Introduction

The signal generation scheduler in `TradingScheduler` runs every 5 minutes (300s), but all current strategies use daily bars (`1d` interval) with a 1-hour in-memory cache TTL. Since daily bars only change once per day at market close, the 5-minute cycle redundantly fetches the same cached data and produces identical signals ~287 times per day. This wastes CPU, generates log noise, and makes unnecessary DB/API calls for account info, positions, and orders each cycle — even when no new data exists.

The fix keeps the 5-minute polling interval but adds a staleness check: before running the full signal generation pipeline, compare the latest bar timestamp of tracked symbols against the last-seen timestamp. If the latest bar hasn't changed, skip the cycle entirely. This turns most 5-minute ticks into cheap no-ops while still catching new daily bars as soon as they appear in the data source.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the signal generation cycle runs every 5 minutes and the latest daily bar has not changed since the last cycle THEN the system performs a full signal generation pipeline (fetching account info, querying positions, querying orders, running batch signal generation across all active strategies) producing identical results to the previous cycle

1.2 WHEN the in-memory historical cache has a valid entry (within 1-hour TTL) for a symbol THEN the system still executes the full signal coordination, risk validation, and order filtering logic on the same unchanged data, wasting CPU and generating redundant log entries

1.3 WHEN the system runs 12 signal generation cycles per hour for daily-bar strategies THEN the system produces up to 11 redundant cycles per hour that query the database for active strategies, open positions, and pending orders without any possibility of generating different signals

### Expected Behavior (Correct)

2.1 WHEN the signal generation cycle runs and the latest daily bar timestamp for all tracked symbols has not changed since the last successful signal generation THEN the system SHALL skip the full signal generation pipeline and log a concise skip message

2.2 WHEN the latest daily bar timestamp for any tracked symbol has changed since the last signal generation THEN the system SHALL proceed with the full signal generation pipeline as normal

2.3 WHEN a signal generation cycle is skipped due to unchanged data THEN the system SHALL NOT query the database for active strategies, positions, or pending orders, and SHALL NOT invoke batch signal generation

2.4 WHEN the system starts up or has never completed a signal generation cycle THEN the system SHALL run the full signal generation pipeline without skipping (no previous bar timestamp to compare against)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the latest daily bar timestamp has changed (new data available) THEN the system SHALL CONTINUE TO run the complete signal generation pipeline including batch signal generation, signal coordination, risk validation, and order execution

3.2 WHEN the system is in a non-ACTIVE state THEN the system SHALL CONTINUE TO skip the trading cycle as before (state check happens before the bar staleness check)

3.3 WHEN startup reconciliation has not yet completed THEN the system SHALL CONTINUE TO perform reconciliation before any signal generation

3.4 WHEN strategies use non-daily intervals in the future THEN the system SHALL CONTINUE TO support them (the staleness check should only apply to daily-bar data or be interval-aware)

3.5 WHEN the MonitoringService runs its 5-second position monitoring loop (trailing stops, partial exits, time-based exits) THEN the system SHALL CONTINUE TO operate independently and unaffected by signal generation skip logic
