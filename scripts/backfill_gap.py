"""One-time backfill: fill Apr 22 - Sep 1 2025 gap for symbols missing that window."""
import sys, os
sys.path.insert(0, "/home/ubuntu/alphacent")
os.chdir("/home/ubuntu/alphacent")

import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

from sqlalchemy import create_engine, text
import subprocess

result = subprocess.run(["grep", "DATABASE_URL", ".env.production"], capture_output=True, text=True, cwd="/home/ubuntu/alphacent")
db_url = result.stdout.strip().split("=", 1)[1] if result.stdout else None
if not db_url:
    print("ERROR: Could not read DATABASE_URL")
    sys.exit(1)

engine = create_engine(db_url)

with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT DISTINCT symbol FROM historical_price_cache "
        "WHERE interval='1d' "
        "AND symbol NOT IN ("
        "  SELECT DISTINCT symbol FROM historical_price_cache "
        "  WHERE interval='1d' AND date >= '2025-04-22' AND date <= '2025-08-31'"
        ") "
        "AND symbol IN ("
        "  SELECT DISTINCT symbol FROM historical_price_cache "
        "  WHERE interval='1d' AND date >= '2026-01-01'"
        ") ORDER BY symbol"
    )).fetchall()

symbols = [r[0] for r in rows]
print(f"Backfilling {len(symbols)} symbols for Apr 22 - Sep 1 2025 gap")

from src.utils.symbol_mapper import YAHOO_FINANCE_TICKERS

gap_start = "2025-04-21"
gap_end   = "2025-09-02"

filled = 0
failed = 0
skipped = 0
chunk_size = 50

for i in range(0, len(symbols), chunk_size):
    chunk = symbols[i:i+chunk_size]
    sym_to_yf = {s: YAHOO_FINANCE_TICKERS.get(s, s) for s in chunk}
    yf_tickers = list(set(sym_to_yf.values()))
    yf_to_syms = {}
    for s, yf_t in sym_to_yf.items():
        yf_to_syms.setdefault(yf_t, []).append(s)

    try:
        data = yf.download(yf_tickers, start=gap_start, end=gap_end,
                           interval="1d", auto_adjust=True, progress=False, threads=True)
        if data.empty:
            print(f"  Chunk {i//chunk_size+1}: no data returned")
            failed += len(chunk)
            continue

        is_multi = len(yf_tickers) > 1

        for yf_ticker in yf_tickers:
            our_syms = yf_to_syms.get(yf_ticker, [])
            try:
                if is_multi:
                    # Multi-ticker: columns are (field, ticker) MultiIndex — level 1 is ticker
                    lvl1 = data.columns.get_level_values(1)
                    if yf_ticker not in lvl1:
                        skipped += len(our_syms)
                        continue
                    ticker_data = data.xs(yf_ticker, axis=1, level=1).dropna(how="all")
                else:
                    ticker_data = data.dropna(how="all")

                if ticker_data.empty:
                    skipped += len(our_syms)
                    continue

                rows_to_insert = []
                for dt, row in ticker_data.iterrows():
                    o = float(row.get("Open", 0) or 0)
                    h = float(row.get("High", 0) or 0)
                    l = float(row.get("Low", 0) or 0)
                    c = float(row.get("Close", 0) or 0)
                    v = float(row.get("Volume", 0) or 0)
                    if c <= 0 or h < l:
                        continue
                    rows_to_insert.append({
                        "dt": dt.to_pydatetime().replace(tzinfo=None),
                        "o": o, "h": h, "l": l, "c": c, "v": v
                    })

                if not rows_to_insert:
                    skipped += len(our_syms)
                    continue

                for sym in our_syms:
                    with engine.connect() as conn:
                        for r in rows_to_insert:
                            conn.execute(text(
                                "INSERT INTO historical_price_cache "
                                "(symbol, interval, date, open, high, low, close, volume, source, fetched_at) "
                                "VALUES (:sym, '1d', :dt, :o, :h, :l, :c, :v, 'yahoo', NOW()) "
                                "ON CONFLICT (symbol, interval, date) DO NOTHING"
                            ), {"sym": sym, **r})
                        conn.commit()
                    filled += 1

            except Exception as e:
                print(f"  Error for {yf_ticker}: {e}")
                failed += len(our_syms)

    except Exception as e:
        print(f"  Chunk download failed: {e}")
        failed += len(chunk)

    done = min(i + chunk_size, len(symbols))
    print(f"  {done}/{len(symbols)} processed — filled={filled} skipped={skipped} failed={failed}")

print(f"\nDone: {filled} filled, {skipped} skipped, {failed} failed")
