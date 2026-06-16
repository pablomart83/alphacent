"""Validate candidate templates produce trades in a real backtest (the 'would I
trade this' gate). Run on EC2 with data access:

    set -a && . ./.env.production && set +a
    ./venv/bin/python scripts/validate_new_templates.py
"""
import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")
from src.strategy.strategy_engine import StrategyEngine
from src.data.market_data_manager import MarketDataManager
from src.core.config import Configuration
from src.api.etoro_client import EToroAPIClient
from src.models.enums import TradingMode
from src.strategy.template_catalog import load_catalog
from src.models.dataclasses import Strategy
from src.models.enums import StrategyStatus

_cfg = Configuration()
_cr = _cfg.load_credentials(TradingMode.DEMO)
_client = EToroAPIClient(public_key=_cr["public_key"], user_key=_cr["user_key"], mode=TradingMode.DEMO)
mdm = MarketDataManager(etoro_client=_client)
engine = StrategyEngine(llm_service=None, market_data=mdm)

CATALOG = {t.name: t for t in load_catalog()}

# (template_name, [symbols to test])
TESTS = [
    ("Multi-Month High Momentum", ["NVDA", "AAPL", "MSFT", "AVGO"]),
    ("Dual Momentum Trend Long", ["MSFT", "AAPL", "SPY", "QQQ"]),
    ("Cross-Asset Trend Follow Long", ["SPX500", "NSDQ100", "GOLD", "SPY"]),
]

end = datetime.now()
start = end - timedelta(days=730)

for tname, symbols in TESTS:
    t = CATALOG.get(tname)
    if not t:
        print(f"!! {tname}: NOT in catalog")
        continue
    print(f"\n=== {tname} ===")
    for sym in symbols:
        strat = Strategy(
            id=f"test-{tname}-{sym}",
            name=f"{tname} {sym} TEST",
            created_at=datetime.now(),
            description=t.description,
            status=StrategyStatus.PROPOSED,
            rules={
                "entry_conditions": list(t.entry_conditions),
                "exit_conditions": list(t.exit_conditions),
                "indicators": list(t.required_indicators),
            },
            symbols=[sym],
            risk_params={},
            metadata=dict(t.metadata or {}),
        )
        try:
            r = engine.backtest_strategy(strat, start, end, interval="1d")
            print(f"  {sym:8} trades={r.total_trades:3}  sharpe={r.sharpe_ratio:+.2f}  "
                  f"ret={r.total_return:+.1%}  wr={r.win_rate:.0%}")
        except Exception as e:
            print(f"  {sym:8} ERROR: {e}")
