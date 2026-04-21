"""Trim existing strategy watchlists to match new quality rules:
- Max 3 symbols total (primary + 2)
- Remove cross-asset symbols that don't meet the stricter threshold
  (uses validated combos cache as the source of truth)
- Remove symbols that fail the tiered threshold based on asset class relationship

Applies to DEMO and BACKTESTED strategies only.
Does NOT touch the primary symbol (index 0).
"""
import sys, os, json
sys.path.insert(0, "/home/ubuntu/alphacent")
os.chdir("/home/ubuntu/alphacent")

from collections import defaultdict
from sqlalchemy import create_engine, text
import subprocess

result = subprocess.run(
    ["grep", "DATABASE_URL", ".env.production"],
    capture_output=True, text=True, cwd="/home/ubuntu/alphacent"
)
db_url = result.stdout.strip().split("=", 1)[1]
engine = create_engine(db_url)

# Load validated combos cache
with open("config/.wf_validated_combos.json") as f:
    cache_data = json.load(f)
validated_entries = {
    (e["template"], e["symbol"]): e
    for e in cache_data.get("entries", [])
}

# Asset class helpers
from src.core.tradeable_instruments import (
    DEMO_ALLOWED_ETFS, DEMO_ALLOWED_FOREX, DEMO_ALLOWED_CRYPTO,
    DEMO_ALLOWED_INDICES, DEMO_ALLOWED_COMMODITIES
)

def get_asset_class(sym):
    s = sym.upper()
    if s in DEMO_ALLOWED_FOREX: return "forex"
    if s in DEMO_ALLOWED_CRYPTO: return "crypto"
    if s in DEMO_ALLOWED_ETFS: return "etf"
    if s in DEMO_ALLOWED_INDICES: return "index"
    if s in DEMO_ALLOWED_COMMODITIES: return "commodity"
    return "stock"

def wl_thresholds(primary_class, sym_class):
    if primary_class == sym_class:
        return 0.2, 3
    equity = {"stock", "etf", "index"}
    if primary_class in equity and sym_class in equity:
        return 0.3, 4
    return 0.5, 6

WL_MAX = 3  # total including primary

with engine.connect() as conn:
    # Pre-load open positions per strategy to protect them from trimming
    pos_rows = conn.execute(text(
        "SELECT strategy_id::text, symbol FROM positions WHERE closed_at IS NULL"
    )).fetchall()
    open_position_symbols = defaultdict(set)
    for pr in pos_rows:
        if pr[0]:
            open_position_symbols[pr[0]].add(pr[1])

    rows = conn.execute(text(
        "SELECT id, name, symbols, strategy_metadata->>'template_name' as template "
        "FROM strategies WHERE status IN ('DEMO','BACKTESTED') "
        "AND jsonb_array_length(symbols::jsonb) > 1"
    )).fetchall()

    print(f"Checking {len(rows)} strategies with watchlists...")
    trimmed = 0
    unchanged = 0

    for row in rows:
        sid, name, symbols_raw, template = row
        try:
            symbols = json.loads(symbols_raw) if isinstance(symbols_raw, str) else symbols_raw
        except Exception:
            continue

        if not symbols or len(symbols) <= 1:
            unchanged += 1
            continue

        primary = symbols[0]
        primary_class = get_asset_class(primary)
        template_name = template or name

        new_symbols = [primary]
        for sym in symbols[1:]:
            if len(new_symbols) >= WL_MAX:
                break  # cap at 3

            # Never remove a symbol that has an open position — exit signals must fire
            if sym in open_position_symbols.get(str(sid), set()):
                new_symbols.append(sym)
                continue

            sym_class = get_asset_class(sym)
            min_sharpe, min_trades = wl_thresholds(primary_class, sym_class)

            # Check validated combos cache
            key = (template_name, sym)
            entry = validated_entries.get(key)
            if entry:
                s = float(entry.get("sharpe", 0) or 0)
                t = int(entry.get("trades", 0) or 0)
                if s > min_sharpe and t >= min_trades:
                    new_symbols.append(sym)
                else:
                    print(f"  TRIM {name}: drop {sym} (S={s:.2f}<{min_sharpe}, t={t}<{min_trades}, {primary_class}→{sym_class})")
            else:
                # Not in validated cache — keep if same asset class (benefit of doubt),
                # drop if cross-asset (no evidence)
                if primary_class == sym_class or (
                    primary_class in {"stock","etf","index"} and sym_class in {"stock","etf","index"}
                ):
                    new_symbols.append(sym)  # same/adjacent, keep
                else:
                    print(f"  TRIM {name}: drop {sym} (not in validated cache, cross-asset {primary_class}→{sym_class})")

        if new_symbols != symbols:
            conn.execute(text(
                "UPDATE strategies SET symbols = cast(:syms as json) WHERE id = :sid"
            ), {"syms": json.dumps(new_symbols), "sid": str(sid)})
            print(f"  UPDATED {name}: {symbols} → {new_symbols}")
            trimmed += 1
        else:
            unchanged += 1

    conn.commit()

print(f"\nDone: {trimmed} strategies trimmed, {unchanged} unchanged.")
