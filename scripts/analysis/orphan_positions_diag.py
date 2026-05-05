"""Diagnose positions with strategy_id='etoro_position'.

These should be strictly sync-path positions (opened directly on eToro UI,
no matching DB order). If we see them for trades WE submitted, the
sync path is mis-classifying our own fills.
"""
from __future__ import annotations
import os, sys

def main():
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set")
        return 1
    conn = psycopg2.connect(url)
    cur = conn.cursor()

    # Get orphan positions
    cur.execute("""
      SELECT id, symbol, strategy_id, etoro_position_id, opened_at, entry_price
      FROM positions
      WHERE strategy_id = 'etoro_position' AND closed_at IS NULL
      ORDER BY opened_at DESC
    """)
    orphans = cur.fetchall()
    print(f"Orphan open positions: {len(orphans)}")
    print()
    for p in orphans:
        pid, sym, sid, eid, opened, entry = p
        print(f"  {sym:6s}  pos_id={pid}  etoro_id={eid}  opened={opened}  entry=${entry}")
        # Find matching orders within 5 min of opened_at
        cur.execute("""
          SELECT id, strategy_id, status, submitted_at, filled_at, etoro_order_id
          FROM orders
          WHERE symbol = %s
            AND submitted_at BETWEEN %s - INTERVAL '5 minutes' AND %s + INTERVAL '5 minutes'
          ORDER BY submitted_at DESC
        """, (sym, opened, opened))
        matches = cur.fetchall()
        if matches:
            for m in matches:
                print(f"    ORDER MATCH: id={m[0][:8]}  strategy_id={m[1]}  status={m[2]}  filled_at={m[4]}  etoro_oid={m[5]}")
        else:
            print(f"    NO ORDER MATCH within ±5min")
        # Widen search: any order for this symbol in last 48h
        cur.execute("""
          SELECT id, strategy_id, status, submitted_at, filled_at, etoro_order_id
          FROM orders
          WHERE symbol = %s
            AND submitted_at > %s - INTERVAL '48 hours'
          ORDER BY submitted_at DESC
          LIMIT 8
        """, (sym, opened))
        wider = cur.fetchall()
        if wider:
            print(f"    (widened 48h search: {len(wider)} orders)")
            for m in wider:
                print(f"      {m[3]} id={m[0][:8]} sid={(m[1] or '?')[:8]} status={m[2]} filled_at={m[4]} etoro_oid={m[5]}")
        # Check signal_decisions for a submission around that time
        cur.execute("""
          SELECT stage, decision, template_name, reason, timestamp
          FROM signal_decisions
          WHERE symbol = %s
            AND timestamp BETWEEN %s - INTERVAL '10 minutes' AND %s
            AND stage IN ('order_submitted', 'gate_blocked', 'signal_emitted')
          ORDER BY timestamp DESC
          LIMIT 5
        """, (sym, opened, opened))
        sigs = cur.fetchall()
        if sigs:
            for s in sigs:
                print(f"    SIGNAL: {s[4]} stage={s[0]}/{s[1]} tmpl={s[2]} reason={s[3][:50] if s[3] else ''}")
        print()

    cur.close()
    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
