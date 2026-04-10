# Bug Fix: Correlation Analyzer Database File Creation

## Problem
Found 1,106 SQLite database files in the root directory with names like:
```
<src.data.market_data_manager.MarketDataManager object at 0x146974d70>
```

## Root Cause
In `src/api/routers/strategies.py` line 1389, the `CorrelationAnalyzer` was being instantiated incorrectly:

```python
# WRONG - passing MarketDataManager object instead of db_path string
correlation_analyzer = CorrelationAnalyzer(market_data)
```

The `CorrelationAnalyzer.__init__` expects a `db_path: str` parameter, but was receiving a `MarketDataManager` object. When SQLite tried to create the database file, it converted the object to a string using `str(market_data)`, which produced the Python object representation.

## Fix Applied
Changed line 1389 in `src/api/routers/strategies.py`:

```python
# CORRECT - uses default db_path="alphacent.db"
correlation_analyzer = CorrelationAnalyzer()
```

## Cleanup
Deleted all 1,106 incorrectly created database files from the root directory.

## Why So Many Files?
Each time the correlation calculation endpoint was called (likely during portfolio rebalancing or strategy analysis), a new database file was created with a unique memory address in the filename. This happened repeatedly, creating hundreds of files.

## Optimization
The fix ensures:
1. Only one database file (`alphacent.db`) is used for correlation data
2. No more files created in the root directory
3. Proper database connection pooling and reuse
