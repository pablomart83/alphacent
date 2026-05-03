"""One-shot diagnostic for FMP Starter plan coverage.

Probes the symbols we actually trade against FMP's 1h and 4h endpoints
and reports: available, premium-blocked, or empty. Run this locally
before any deploy that assumes FMP serves a new symbol.

Output is a table that maps directly to what the FMP OHLC client does:
- "OK" → FMP primary path works, no fallback needed
- "PREMIUM" → FMP returns 402-style error, fall through to Yahoo
- "EMPTY" → FMP returns []; need to investigate whether the ticker
             symbol is wrong or the asset isn't on FMP at all.

Reads the API key from config/api_keys.yaml (on EC2 this is written
from Secrets Manager at boot; locally you need to scp it or stub it).
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

import requests
import yaml

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)


# Our full trading universe (matches config/autonomous_trading.yaml::symbols).
# Grouped so the output table stays readable.
UNIVERSE = {
    "stocks": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "NFLX",
        "AMD", "INTC", "AVGO", "LULU", "PLTR", "BABA",  # liquidity spread
    ],
    "etfs": ["SPY", "QQQ", "IWM", "XLE", "XLF", "XLK", "TLT", "GLD"],
    "indices": [
        ("^GSPC", "SPX500"),
        ("^IXIC", "NSDQ100"),
        ("^DJI",  "DJ30"),
        ("^FTSE", "UK100"),
        ("^GDAXI", "GER40"),     # known premium-blocked
        ("^FCHI",  "FR40"),      # known premium-blocked
        ("^STOXX50E", "STOXX50"),
    ],
    "forex": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"],
    "commodities": [
        ("GCUSD", "GOLD"),
        ("SIUSD", "SILVER"),
        ("CLUSD", "OIL"),        # known premium-blocked
        ("HGUSD", "COPPER"),     # known premium-blocked
    ],
    "crypto": [
        ("BTCUSD", "BTC"),
        ("ETHUSD", "ETH"),
        ("SOLUSD", "SOL"),
        ("AVAXUSD", "AVAX"),
        ("LINKUSD", "LINK"),
        ("DOTUSD", "DOT"),
    ],
}

BASE = "https://financialmodelingprep.com/stable/historical-chart"
TIMEOUT = 10.0


def _load_key() -> Optional[str]:
    """Read the FMP api_key. Structure is `financial_modeling_prep.api_key`
    (top-level, NOT nested under `data_sources`)."""
    for candidate in ("config/api_keys.yaml", "/home/ubuntu/alphacent/config/api_keys.yaml"):
        p = os.path.join(WORKSPACE, candidate) if not os.path.isabs(candidate) else candidate
        if os.path.exists(p):
            try:
                with open(p) as f:
                    cfg = yaml.safe_load(f) or {}
                k = (cfg.get("financial_modeling_prep") or {}).get("api_key", "")
                if k and k != "REPLACE_VIA_SECRETS_MANAGER":
                    return k
            except Exception:
                continue
    return None


def _classify(resp: requests.Response, body: str) -> str:
    """Map FMP response → one of {OK, PREMIUM, EMPTY, ERROR}."""
    if resp.status_code != 200:
        return f"HTTP_{resp.status_code}"
    if "Premium Query Parameter" in body or "not available under your current subscription" in body:
        return "PREMIUM"
    if body.strip() == "[]":
        return "EMPTY"
    if body.startswith("["):
        return "OK"
    return "ERROR"


def probe(api_key: str, symbol: str, interval: str) -> tuple[str, int]:
    """Return (status, bar_count). bar_count is 0 for non-OK statuses."""
    url = (
        f"{BASE}/{interval}"
        f"?symbol={requests.utils.quote(symbol, safe='')}"
        f"&from=2024-01-01&to=2024-01-31&apikey={api_key}"
    )
    try:
        r = requests.get(url, timeout=TIMEOUT)
        body = r.text
        status = _classify(r, body)
        if status == "OK":
            try:
                import json as _j
                data = _j.loads(body)
                return status, len(data) if isinstance(data, list) else 0
            except Exception:
                return "ERROR_PARSE", 0
        return status, 0
    except requests.RequestException as e:
        return f"EXC_{type(e).__name__}", 0


def main() -> int:
    key = _load_key()
    if not key:
        print(
            "ERROR: FMP api_key not found. Run the probe on EC2, or copy "
            "config/api_keys.yaml locally after running deploy/patch-api-keys.sh."
        )
        return 1

    print("FMP Starter coverage probe")
    print("=" * 78)
    print(f"{'group':<12} {'fmp_sym':<12} {'display':<10} {'1h':<14} {'4h':<14}")
    print("-" * 78)

    supported_intervals = ("1hour", "4hour")
    ok_count = 0
    premium_count = 0
    other_count = 0

    for group, items in UNIVERSE.items():
        for item in items:
            if isinstance(item, tuple):
                fmp_sym, display = item
            else:
                fmp_sym = item
                display = item
            cells: List[str] = []
            for itv in supported_intervals:
                status, n = probe(key, fmp_sym, itv)
                if status == "OK":
                    cells.append(f"OK ({n} bars)")
                    ok_count += 1
                elif status == "PREMIUM":
                    cells.append("PREMIUM")
                    premium_count += 1
                else:
                    cells.append(status)
                    other_count += 1
            print(f"{group:<12} {fmp_sym:<12} {display:<10} {cells[0]:<14} {cells[1]:<14}")

    print("-" * 78)
    print(f"Totals: OK={ok_count}  PREMIUM={premium_count}  OTHER={other_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
