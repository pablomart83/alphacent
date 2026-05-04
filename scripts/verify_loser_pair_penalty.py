"""One-off verification that the loser-pair penalty lookup sees the backfilled
trade_journal rows.

Instantiates a RiskManager (with a dummy etoro_client) just to reach
_get_symbol_template_loser_stats, then invokes the lookup for known loser
pairs. Expects trades >= 3 AND pnl < 0 for each target.

Usage on EC2:
    python3 scripts/verify_loser_pair_penalty.py
"""

import logging
import sys

from src.risk.risk_manager import RiskManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("verify_loser_pair")

# Known losers from the backfill output on 2026-05-05
TARGETS = [
    ("SCCO", "EMA Ribbon Expansion Long"),
    ("HIMS", "4H VWAP Trend Continuation"),
    ("GEV", "4H EMA Ribbon Trend Long"),
    ("GS", "ATR Dynamic Trend Follow"),
    ("PYPL", "4H ADX Trend Swing"),
    ("BTC", "EMA Pullback Momentum"),
    # Control: pair with no losing history — lookup should return trades=0
    ("DOES_NOT_EXIST_XYZ", "no such template"),
]


def main() -> int:
    # Minimal RiskManager — the loser-pair helper is a plain method that only
    # needs a DB connection. We don't exercise any sizing logic here.
    class _Stub:
        pass

    rm = RiskManager.__new__(RiskManager)
    rm._last_sizing_reason = ""
    # ignore anything sizing-related; we only call _get_symbol_template_loser_stats

    all_good = True
    for symbol, template in TARGETS:
        stats = rm._get_symbol_template_loser_stats(symbol, template)
        if stats is None:
            logger.error("NULL return for %s × %s — lookup failed", symbol, template)
            all_good = False
            continue
        trades = stats.get("trades", 0)
        pnl = stats.get("pnl", 0.0)
        would_fire = trades >= 3 and pnl < 0
        logger.info(
            "%-20s × %-40s -> trades=%d pnl=%.2f would_fire_penalty=%s",
            symbol,
            template,
            trades,
            pnl,
            would_fire,
        )
        # For real losers we expect the penalty to fire; for the control it must not
        if symbol.startswith("DOES_NOT_EXIST"):
            if would_fire:
                logger.error("Control target unexpectedly triggered the penalty — bug")
                all_good = False
        else:
            if not would_fire:
                logger.error(
                    "Expected %s × %s to trigger the penalty (%d trades, $%.2f) — bug",
                    symbol, template, trades, pnl,
                )
                all_good = False

    if all_good:
        logger.info("VERIFICATION PASSED — loser-pair penalty lookup is healthy")
        return 0
    logger.error("VERIFICATION FAILED — see errors above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
