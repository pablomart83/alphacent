"""Shared ATR-based stop-loss floor.

Single source of truth for the volatility floor a stop-loss must respect:
a stop tighter than ~1.5-2x ATR sits inside the instrument's normal noise band
and gets noise-stopped before any edge can play out (Wilder's original ATR stop).

This is used in two places that MUST agree, or the SL/TP recommender will keep
proposing stops the execution layer silently overrides:
  - order_executor.execute_signal — enforces the floor at order time (the stop
    that actually goes to the broker).
  - sl_tp_recommender — must NOT recommend a stop below this floor, so that a
    CIO-approved recommendation equals what actually executes.

Multipliers match execute_signal exactly:
  - Daily strategies: 1.5x ATR (institutional standard).
  - 4H strategies:    2.0x ATR (4H intraday noise is ~40% of a daily bar; the
                      1.5x daily multiplier translates to ~0.6x on 4H — too tight).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def compute_atr_floor_pct(
    symbol: str,
    is_4h: bool = False,
    current_price: Optional[float] = None,
    mdm: object = None,
) -> Optional[float]:
    """Return the ATR-based minimum stop distance as a fraction of price
    (e.g. 0.09 = 9%), or None if it can't be computed.

    `mdm` is an optional MarketDataManager; if omitted the shared singleton is
    used. `current_price` is the reference price for the percentage; if omitted
    the latest close is used.
    """
    try:
        if mdm is None:
            from src.data.market_data_manager import get_market_data_manager
            mdm = get_market_data_manager()
        if mdm is None:
            return None

        interval = "4h" if is_4h else "1d"
        lookback_days = 14 if is_4h else 30  # ~84 4H bars, or 30 daily bars
        end = datetime.now()
        start = end - timedelta(days=lookback_days)
        bars = mdm.get_historical_data(symbol, start, end, interval=interval)
        if not bars or len(bars) <= 14:
            return None

        highs = [b.high for b in bars if b.high and b.low and b.close]
        lows = [b.low for b in bars if b.high and b.low and b.close]
        closes = [b.close for b in bars if b.high and b.low and b.close]
        if len(closes) <= 14:
            return None

        tr_list = []
        for i in range(1, len(closes)):
            tr_list.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        if not tr_list:
            return None

        atr14 = sum(tr_list[-14:]) / min(14, len(tr_list[-14:]))
        ref = current_price or closes[-1]
        if not ref or ref <= 0:
            return None

        atr_pct = atr14 / ref
        multiplier = 2.0 if is_4h else 1.5
        return atr_pct * multiplier
    except Exception as e:
        logger.debug(f"compute_atr_floor_pct({symbol}) failed: {e}")
        return None
