"""F3 verification: does vectorbt's sharpe_ratio() with freq='1D' annualize by
365 (calendar) or 252 (trading days)?

The strategy_engine path computes `vbt.Portfolio.from_signals(..., freq='1D').sharpe_ratio()`
for daily strategies and trusts it as-is (only 1h/4h get a manual annualization
correction). If vectorbt uses calendar 365 on a business-day series, daily Sharpe
is overstated by sqrt(365/252) ~= 1.204x — inflating every daily WF/conviction gate.

This script replicates the engine path on a synthetic daily series and backs out
the annualization factor empirically. Pure compute — no DB/creds needed.

Run on EC2:  /home/ubuntu/alphacent/venv/bin/python3 scripts/verify_sharpe_annualization.py
"""
import math
import numpy as np
import pandas as pd

try:
    import vectorbt as vbt
except Exception as e:  # pragma: no cover
    print(f"vectorbt import failed: {e}")
    raise SystemExit(1)

print(f"vectorbt version: {getattr(vbt, '__version__', 'unknown')}")

# --- Build a synthetic daily series on a BUSINESS-DAY index (like stock data) ---
np.random.seed(42)
n_days = 504  # ~2 trading years
dates = pd.bdate_range(start="2024-01-01", periods=n_days)  # business days only (no weekends)
daily_ret = np.random.normal(loc=0.0005, scale=0.01, size=n_days)  # ~0.05%/day drift, 1% vol
close = pd.Series(100.0 * np.cumprod(1.0 + daily_ret), index=dates)

# Buy-and-hold-style: enter bar 1, never exit (full-period exposure) so portfolio
# daily returns ~= asset daily returns — makes the annualization back-out clean.
entries = pd.Series(False, index=dates)
exits = pd.Series(False, index=dates)
entries.iloc[1] = True

pf = vbt.Portfolio.from_signals(
    close=close, entries=entries, exits=exits,
    init_cash=100000, fees=0.0, freq="1D",
)

vbt_sharpe = pf.sharpe_ratio()

# Manual Sharpe from the portfolio's own daily returns, both conventions.
r = pf.returns()
r = r[r.notna()]
mean_d = r.mean()
std_d = r.std(ddof=1)
sharpe_per_bar = mean_d / std_d if std_d > 0 else float("nan")
manual_252 = sharpe_per_bar * math.sqrt(252)
manual_365 = sharpe_per_bar * math.sqrt(365)

print("\n--- Results ---")
print(f"bars (non-nan daily returns): {len(r)}")
print(f"per-bar Sharpe (mean/std):    {sharpe_per_bar:.4f}")
print(f"vectorbt sharpe_ratio():      {vbt_sharpe:.4f}")
print(f"manual x sqrt(252):           {manual_252:.4f}")
print(f"manual x sqrt(365):           {manual_365:.4f}")

ratio_252 = vbt_sharpe / manual_252 if manual_252 else float("nan")
ratio_365 = vbt_sharpe / manual_365 if manual_365 else float("nan")
print(f"\nvbt / manual_252 = {ratio_252:.4f}  (==1.00 means vbt uses 252)")
print(f"vbt / manual_365 = {ratio_365:.4f}  (==1.00 means vbt uses 365)")

implied_ann = (vbt_sharpe / sharpe_per_bar) ** 2 if sharpe_per_bar else float("nan")
print(f"\nimplied annualization factor (vbt/per-bar)^2 = {implied_ann:.1f}")
print(f"  -> 252 = trading-day convention; 365 = calendar (overstates by {math.sqrt(365/252):.3f}x)")

if abs(implied_ann - 365) < abs(implied_ann - 252):
    print("\nVERDICT: vectorbt annualizes by ~365 (CALENDAR). F3 CONFIRMED — daily Sharpe")
    print(f"         is overstated ~{math.sqrt(365/252):.1%} vs the sqrt(252) trading-day convention.")
else:
    print("\nVERDICT: vectorbt annualizes by ~252 (trading days). F3 NOT a bug — daily Sharpe is correct.")
