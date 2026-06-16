"""Alpha Edge fundamental-field coverage audit.

For a representative equity universe, fetch historical quarterly fundamentals from
FMP and report what fraction of (symbol, quarter) rows actually populate each field
that an AE template depends on. Template families whose required field is universally
empty on the current plan can never validate/trade and should be disabled in the
catalog.

Run on EC2 (has FMP creds + cache):
    set -a && . ./.env.production && set +a
    ./venv/bin/python scripts/ae_field_coverage.py
"""
import sys
import collections

import yaml

sys.path.insert(0, ".")
from src.data.fundamental_data_provider import get_fundamental_data_provider

# Field required by each AE template family (from strategy_engine.factor_checks).
TEMPLATE_FIELD = {
    "earnings_momentum": "earnings_surprise",
    "earnings_miss_momentum_short": "earnings_surprise",
    "quality_mean_reversion": "roe",
    "quality_deterioration_short": "roe",
    "revenue_acceleration": "revenue_growth",
    "dividend_aristocrat": "dividend_yield",
    "multi_factor_composite": "piotroski_f_score",
    "gross_profitability": "gross_profit",
    "accruals_quality": "accruals_ratio",
    "fcf_yield_value": "fcf_yield",
    "shareholder_yield": "shares_outstanding",
    "deleveraging": "long_term_debt",
    "relative_value": "pe_ratio",
    "analyst_revision_momentum": "estimated_eps",
    "share_buyback": "shares_outstanding",
    "earnings_momentum_combo": "sue",
    "price_target_upside": "pe_ratio",
}

# Representative liquid equity universe (mix of profitable large-cap + growth names).
UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "META", "JPM", "PNC", "C", "ORCL",
    "DELL", "ASML", "SNOW", "RIVN", "RKLB", "ZIM", "MU", "AMZN", "DDOG", "ARM",
]

ALL_FIELDS = sorted(set(TEMPLATE_FIELD.values()))


def main():
    config = {}
    try:
        with open("config/autonomous_trading.yaml") as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        pass
    provider = get_fundamental_data_provider(config)

    # field -> [non_null_count, total_count]
    cov = {f: [0, 0] for f in ALL_FIELDS}
    symbols_with_data = 0
    for sym in UNIVERSE:
        try:
            quarters = provider.get_historical_fundamentals(sym, quarters=8) or []
        except Exception as e:
            print(f"  {sym}: error {e}")
            quarters = []
        if quarters:
            symbols_with_data += 1
        for q in quarters:
            for f in ALL_FIELDS:
                cov[f][1] += 1
                if q.get(f) is not None:
                    cov[f][0] += 1

    print(f"Universe: {len(UNIVERSE)} symbols, {symbols_with_data} returned quarterly data\n")
    print(f"{'FIELD':24} {'COVERAGE':>12}")
    for f in ALL_FIELDS:
        nn, tot = cov[f]
        pct = (100.0 * nn / tot) if tot else 0.0
        flag = "  <-- DEAD" if pct < 5 else ("  <-- sparse" if pct < 40 else "")
        print(f"{f:24} {nn:5}/{tot:<5} {pct:5.1f}%{flag}")

    print("\n=== Per-template verdict ===")
    for tmpl, field in sorted(TEMPLATE_FIELD.items()):
        nn, tot = cov[field]
        pct = (100.0 * nn / tot) if tot else 0.0
        verdict = "DISABLE (field dead)" if pct < 5 else ("REVIEW (sparse)" if pct < 40 else "OK")
        print(f"  {tmpl:32} field={field:22} {pct:5.1f}%  {verdict}")


if __name__ == "__main__":
    main()
