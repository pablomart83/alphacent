"""Restore symbols to strategy watchlists where open positions exist but symbol was trimmed.

The trim_watchlists.py script correctly removed low-quality watchlist symbols,
but it didn't account for strategies that already had open positions on those symbols.
Those positions need their symbol back in the watchlist so exit signals can fire.

Rule: if a strategy has an open position on symbol X, X must be in strategy.symbols.
"""
import sys, os, json
sys.path.insert(0, "/home/ubuntu/alphacent")
os.chdir("/home/ubuntu/alphacent")

from sqlalchemy import create_engine, text
import subprocess

result = subprocess.run(
    ["grep", "DATABASE_URL", ".env.production"],
    capture_output=True, text=True, cwd="/home/ubuntu/alphacent"
)
db_url = result.stdout.strip().split("=", 1)[1]
engine = create_engine(db_url)

with engine.connect() as conn:
    # Find all open positions whose symbol is not in the strategy's watchlist
    rows = conn.execute(text("""
        SELECT s.id, s.name, s.symbols, p.symbol as position_symbol,
               p.unrealized_pnl, p.invested_amount
        FROM strategies s
        JOIN positions p ON p.strategy_id = s.id
        WHERE p.closed_at IS NULL
        AND NOT (s.symbols::jsonb @> jsonb_build_array(p.symbol))
        ORDER BY s.name, p.symbol
    """)).fetchall()

    if not rows:
        print("No orphaned positions found.")
        sys.exit(0)

    print(f"Found {len(rows)} orphaned positions — restoring symbols to watchlists...")

    # Group by strategy
    from collections import defaultdict
    strategy_fixes = defaultdict(lambda: {"name": "", "symbols": [], "to_add": []})
    for row in rows:
        sid, name, symbols_raw, pos_sym, pnl, invested = row
        try:
            symbols = json.loads(symbols_raw) if isinstance(symbols_raw, str) else symbols_raw
        except Exception:
            symbols = []
        strategy_fixes[str(sid)]["name"] = name
        strategy_fixes[str(sid)]["symbols"] = symbols
        if pos_sym not in strategy_fixes[str(sid)]["to_add"]:
            strategy_fixes[str(sid)]["to_add"].append(pos_sym)

    restored = 0
    for sid, fix in strategy_fixes.items():
        current = fix["symbols"]
        to_add = [s for s in fix["to_add"] if s not in current]
        if not to_add:
            continue
        new_symbols = current + to_add
        conn.execute(text(
            "UPDATE strategies SET symbols = cast(:syms as json) WHERE id = :sid"
        ), {"syms": json.dumps(new_symbols), "sid": sid})
        print(f"  RESTORED {fix['name']}: added {to_add} → {new_symbols}")
        restored += 1

    conn.commit()

print(f"\nDone: {restored} strategies updated, {len(rows)} positions now have exit signal coverage.")
