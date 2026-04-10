# Bugfix Requirements Document

## Introduction

The trade journal fails with `sqlite3.IntegrityError: UNIQUE constraint failed: trade_journal.trade_id` when the order monitor's monitoring cycle detects filled orders and attempts to log trade entries. The root cause is that `OrderMonitor.check_submitted_orders()` calls `TradeJournal.log_entry()` every time it processes a filled order, but the order may remain in the submitted-orders query across multiple monitoring cycles (e.g., during position matching retries or before the commit finalizes the status change). Since `trade_journal.trade_id` has a UNIQUE constraint, the second INSERT for the same `trade_id` raises an `IntegrityError`, which propagates as an unhandled error. This affects all filled orders and prevents trade analytics data from being reliably recorded.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the order monitor detects a filled order and calls `TradeJournal.log_entry()` with a `trade_id` that already exists in the `trade_journal` table THEN the system raises `sqlite3.IntegrityError: UNIQUE constraint failed: trade_journal.trade_id` and the trade journal entry is not recorded

1.2 WHEN the `IntegrityError` is raised inside `log_entry()` THEN the system logs `Failed to log trade entry` at ERROR level and re-raises the exception, which propagates up to `check_submitted_orders()` where it is caught as a warning but the duplicate scenario is not distinguished from a genuine failure

1.3 WHEN multiple filled orders are processed in the same monitoring cycle and any of them have pre-existing journal entries THEN the system fails on each duplicate individually, logging repeated ERROR messages for each order (e.g., INTC order b24c1829 and NKE order 4b96359e both fail with the same constraint violation)

### Expected Behavior (Correct)

2.1 WHEN the order monitor detects a filled order and calls `TradeJournal.log_entry()` with a `trade_id` that already exists in the `trade_journal` table THEN the system SHALL detect the existing entry and skip the duplicate insert without raising an error

2.2 WHEN a duplicate trade journal entry is detected THEN the system SHALL log an informational message indicating the entry was skipped (not an error) so operators can distinguish between genuine failures and benign duplicate attempts

2.3 WHEN multiple filled orders are processed in the same monitoring cycle and some have pre-existing journal entries THEN the system SHALL handle each order independently, skipping duplicates and successfully inserting new entries without any `IntegrityError` exceptions

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the order monitor detects a filled order and calls `TradeJournal.log_entry()` with a `trade_id` that does NOT exist in the `trade_journal` table THEN the system SHALL CONTINUE TO insert the new trade journal entry with all provided fields (slippage, metadata, strategy_id, etc.)

3.2 WHEN `TradeJournal.log_entry()` encounters a genuine database error (not a duplicate key violation) THEN the system SHALL CONTINUE TO log the error, rollback the session, and raise the exception

3.3 WHEN `TradeJournal.log_entry()` successfully inserts a new entry THEN the system SHALL CONTINUE TO calculate and store entry slippage when `expected_price` and `order_side` are provided

3.4 WHEN `TradeJournal.get_trade()` is called with a valid `trade_id` THEN the system SHALL CONTINUE TO return the trade data dictionary for existing entries and `None` for non-existent entries
