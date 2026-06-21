#!/usr/bin/env python3
"""PROOF backtest: does signalling a leveraged ETF off its CLEAN UNDERLYING beat
signalling off the ETF's own (noisy) price?

Runs the REAL production rolling walk-forward (`walk_forward_validate_rolling`,
the same path the proposer uses — costs, SL/TP simulation and all) on:

  A) the new "Leveraged ETF Trend (Underlying-Signaled)" template  (signal off SOXX/QQQ/SPY)
  B) the SELF-signalled daily trend templates that already work     (EMA / ADX Trend Following)

over {SOXL, TQQQ, UPRO}, full history, OUR costs. Reports the test-window
cost-net Sharpe, return, trade count and overfit verdict — the quantities the
equity acceptance gate uses — so we can see whether the cross-asset signal
improves the risk-adjusted edge (or honestly report that it doesn't).

Read-only (no DB writes, no orders). Run on EC2 via the venv:
    /home/ubuntu/alphacent/venv/bin/python3 scripts/verify_underlying_signaled_edge.py
"""
import os, sys, argparse
_S = os.path.dirname(os.path.abspath(__file__)); _W = os.path.dirname(_S)
if _W not in sys.path:
    sys.path.insert(0, _W)

from datetime import datetime
from src.core.config import Configuration
from src.models.enums import TradingMode
from src.api.etoro_client import EToroAPIClient
from src.data.market_data_manager import MarketDataManager
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.strategy_proposer import StrategyProposer
from src.strategy.template_catalog import load_catalog

UNDERLYING_TEMPLATE = "Leveraged ETF Trend (Underlying-Signaled)"
# SELF-signalled daily trend templates — the current SOXL earners (the baseline).
_DEFAULT_BASELINES = ["EMA Trend Following", "ADX Trend Following"]
_DEFAULT_SYMBOLS = ["SOXL", "TQQQ", "UPRO"]

_ap = argparse.ArgumentParser(description=__doc__)
_ap.add_argument("--baselines", help="comma-separated SELF-signalled template names")
_ap.add_argument("--symbols", help="comma-separated leveraged ETFs (default: SOXL,TQQQ,UPRO)")
_args = _ap.parse_args()
BASELINES = [s.strip() for s in _args.baselines.split(",")] if _args.baselines else list(_DEFAULT_BASELINES)
SYMBOLS = [s.strip().upper() for s in _args.symbols.split(",")] if _args.symbols else list(_DEFAULT_SYMBOLS)

cfg = Configuration()
cr = cfg.load_credentials(TradingMode.DEMO)
client = EToroAPIClient(public_key=cr["public_key"], user_key=cr["user_key"], mode=TradingMode.DEMO)
mdm = MarketDataManager(client)
engine = StrategyEngine(None, mdm, None)
proposer = StrategyProposer(llm_service=None, market_data=mdm)

cat = {t.name: t for t in load_catalog()}
end = datetime.now()


def run(tname, sym):
    t = cat.get(tname)
    if t is None:
        print(f"{tname:42} {sym:5} (not in catalog — skipped)")
        return
    try:
        strat = proposer._create_strategy_from_params(t, [sym], dict(t.default_parameters or {}), None)
        strat.metadata = strat.metadata or {}
        tr, te, sd, ed = proposer._select_wf_window(strat, end)
        wf = engine.walk_forward_validate_rolling(strat, end=ed, train_days=tr, test_days=te,
                                                  n_windows=3, min_pass_windows=2)
        ntr = wf.get('test_trades') or (wf['test_results'].total_trades if wf.get('test_results') else 0)
        ret = wf['test_results'].total_return if wf.get('test_results') else 0.0
        per_trade = (ret / ntr * 100) if ntr else 0.0
        print(f"{tname:42} {sym:5} {wf.get('test_sharpe', 0) or 0:7.2f} "
              f"{ret*100:8.1f}% {per_trade:8.2f}% {ntr:6d}  "
              f"pass={wf.get('rolling_pass_count','?')}/3 overfit={wf.get('is_overfitted')}")
    except Exception as e:
        print(f"{tname:42} {sym:5}  ERROR: {str(e)[:60]}")


print(f"{'template':42} {'sym':5} {'testS':>7} {'tot_ret':>9} {'ret/tr':>9} {'ntr':>6}  verdict")
print("-" * 110)
print("== A) UNDERLYING-SIGNALED (new cross-asset primitive) ==")
for sym in SYMBOLS:
    run(UNDERLYING_TEMPLATE, sym)
print("== B) SELF-SIGNALLED daily trend (current baseline) ==")
for tname in BASELINES:
    for sym in SYMBOLS:
        run(tname, sym)
print("-" * 110)
print("testS = test-window cost-net Sharpe (pooled across 3 rolling windows, full history, OUR costs).")
print("Compare A vs B per symbol: higher cost-net Sharpe / fewer overfit windows = the cross-asset signal adds edge.")
