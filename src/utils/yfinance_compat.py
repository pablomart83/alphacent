"""
yfinance compatibility / defensive utilities.

This module centralises workarounds for yfinance quirks so fixes live in one
place. The primary concern is DST boundary crashes:

yfinance internally converts datetime bounds to the target exchange's local
timezone (typically America/New_York for US equities). On DST transition days
(2nd Sunday March spring-forward, 1st Sunday November fall-back in US; last
Sunday March/October in EU) the conversion can hit ambiguous local hours and
raise AmbiguousTimeError inside pandas.tz_localize. This causes yf.download()
and Ticker.history() to return empty DataFrames for entire batches.

Passing tz-aware UTC datetimes bypasses yfinance's internal tz inference on
the input bounds. The output still arrives tz-aware, so callers must also
normalise the index with `normalize_yf_index_to_utc_naive()` before any
iteration or resampling.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Union

import pandas as pd


def to_tz_aware_utc(dt: Optional[Union[datetime, str]]) -> Optional[datetime]:
    """
    Convert a naive or tz-aware datetime to tz-aware UTC.

    Passing tz-aware UTC bounds to yfinance prevents its internal local-tz
    inference from hitting DST ambiguous hours.

    Args:
        dt: datetime (naive or tz-aware) or date-string. None passes through.

    Returns:
        tz-aware UTC datetime, or None if input was None.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        # Let pandas handle string parsing; result is tz-naive unless string has tz
        ts = pd.to_datetime(dt)
        dt = ts.to_pydatetime() if hasattr(ts, 'to_pydatetime') else ts
    if dt.tzinfo is None:
        # Treat naive datetimes as UTC. This is a deliberate choice: all naive
        # datetimes in AlphaCent are UTC by convention (see
        # trading-system-context.md — "Data Pipeline" section).
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_yf_index_to_utc_naive(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise a yfinance-returned DataFrame's DatetimeIndex to UTC-naive.

    yfinance returns tz-aware timestamps. Downstream code that iterates the
    index (e.g. `for ts, row in df.iterrows(): ts.to_pydatetime()`) or resamples
    (e.g. `df.resample('4h')`) will crash on DST boundaries if the index is
    tz-aware and contains an ambiguous local hour.

    This converts to UTC then strips tz so downstream operations are safe.

    Args:
        df: DataFrame with (potentially) tz-aware DatetimeIndex. Modified
            in place AND returned for chaining convenience.

    Returns:
        The same DataFrame with tz-naive UTC index.
    """
    if df is None or df.empty:
        return df
    if hasattr(df.index, 'tz') and df.index.tz is not None:
        df.index = df.index.tz_convert('UTC').tz_localize(None)
    return df
