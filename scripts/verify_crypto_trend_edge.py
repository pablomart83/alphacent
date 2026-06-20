#!/usr/bin/env python3
"""PROOF backtest: do the kept crypto TREND/MOMENTUM templates have positive
cost-net edge over the full Binance history (2023-2026, bull + bear)?

Runs the REAL production rolling-WF + the honest per-trade cost-net Sharpe gate
(not a reimplementation) on a sample of trend templates x {BTC, ETH}. Reports
the per-trade cost-net Sharpe, mean-net-per-trade and trade count — the exact
quantities the live crypto acceptance gate uses.

Read-only (no DB writes, no orders). Run on EC2 via the venv:
    /home/ubuntu/alphacent/venv/bin/python3 scripts/verify_crypto_trend_edge.py
"""
import os, sys
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

TEMPLATES = [
    "Crypto Vol-Managed Trend",
    "Crypto BTC Relative Strength",
    "Crypto Time-Series Momentum",
    "Crypto Dominance Rotation Alt Long",
    "Crypto 21W MA Trend Follow",
]
SYMBOLS = ["BTC", "ETH", "SOL"]

cfg = Configuration()
cr = cfg.load_credentials(TradingMode.DEMO)
client = EToroAPIClient(public_key=cr["public_key"], user_key=cr["user_key"], mode=TradingMode.DEMO)
mdm = MarketDataManager(client)
engine = StrategyEngine(None, mdm, None)
proposer = StrategyProposer(llm_service=None, market_data=mdm)

cat = {t.name: t for t in load_catalog()}
end = datetime.now()
print(f"{'template':32} {'sym':4} {'ptSharpe':>9} {'net/trade':>10} {'ntrades':>7}  verdict")
print("-" * 86)
for tname in TEMPLATES:
    t = cat.get(tname)
    if t is None:
        print(f"{tname:32} (not in surviving catalog — skipped)")
        continue
    for sym in SYMBOLS:
        try:
            strat = proposer._create_strategy_from_params(t, [sym], dict(t.default_parameters or {}), None)
            strat.metadata = strat.metadata or {}
            tr, te, sd, ed = proposer._select_wf_window(strat, end)
            wf = engine.walk_forward_validate_rolling(strat, end=ed, train_days=tr, test_days=te,
                                                      n_windows=3, min_pass_windows=2)
            pt = proposer._per_trade_net_sharpe(proposer._crypto_wf_results_for_sharpe(wf, 'test'), sym,
                                                str((strat.metadata or {}).get('interval', '1d')).lower())
            if pt is None:
                print(f"{tname:32} {sym:4} {'--':>9} {'--':>10} {'<3':>7}  no honest sharpe (too few trades)")
            else:
                ok = pt['sharpe'] >= 0.3 and pt['mean_net'] > 0
                print(f"{tname:32} {sym:4} {pt['sharpe']:9.2f} {pt['mean_net']*100:9.2f}% {pt['n_trades']:7d}  "
                      f"{'PASS (positive cost-net edge)' if ok else 'fail'}")
        except Exception as e:
            print(f"{tname:32} {sym:4}  ERROR: {str(e)[:50]}")
print("-" * 86)
print("PASS = per-trade cost-net Sharpe >= 0.3 AND positive net expectancy/trade")
print("(window pools 3 rolling windows across 2023-2026 incl. the 2024 bull and 2025-26 chop)")
