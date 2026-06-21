#!/usr/bin/env python3
"""Per-symbol trading-edge diagnostic — the analysis that cracked SOXL (2026-06-21).

For any symbol (or the whole book), reveals WHERE the edge lives and whether we
capture or give it back:
  - P&L + win-rate by HOLDING-PERIOD bucket (<1d / 1-3d / 3-7d / >7d)
  - exit-reason distribution (stop/TSL/signal/TP)
  - MAE/MFE capture ratio (avg favorable move vs avg realized)
  - a CHURN flag: sub-day P&L < 0 AND >=3d P&L > 0 (the SOXL/MU signature)

Read-only. Run on EC2 via venv with .env.production sourced for DB:
    ./venv/bin/python3 scripts/diagnose_symbol_edge.py [--symbol SOXL] [--account demo|live|all]
    ./venv/bin/python3 scripts/diagnose_symbol_edge.py --scan   # book-wide churn-cohort scan
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from src.models.database import get_database


def _bucket_sql(where: str) -> str:
    return f"""
        SELECT CASE WHEN hold_time_hours < 24 THEN 'a <1d'
                    WHEN hold_time_hours < 72 THEN 'b 1-3d'
                    WHEN hold_time_hours < 168 THEN 'c 3-7d'
                    ELSE 'd >7d' END AS bucket,
               COUNT(*) n,
               ROUND((AVG(CASE WHEN pnl>0 THEN 1.0 ELSE 0 END)*100)::numeric,0) win,
               ROUND(AVG(pnl_percent)::numeric,2) avg_ret,
               ROUND(SUM(pnl)::numeric,0) tot
        FROM trade_journal
        WHERE exit_time IS NOT NULL AND {where}
        GROUP BY 1 ORDER BY 1
    """


def diagnose(session, symbol: str, account: str):
    acct = "" if account == "all" else f"AND account_type = '{account}'"
    where = f"symbol = '{symbol}' {acct}"
    print(f"\n{'='*70}\n{symbol}  (account={account})\n{'='*70}")
    rows = session.execute(text(_bucket_sql(where))).fetchall()
    if not rows:
        print("  no closed trades")
        return
    print(f"  {'bucket':7} {'n':>4} {'win%':>5} {'avgRet':>7} {'totP&L':>9}")
    for r in rows:
        print(f"  {r.bucket:7} {r.n:>4} {r.win:>5} {r.avg_ret:>7} {r.tot:>9}")
    # MAE/MFE capture
    mm = session.execute(text(
        f"SELECT ROUND(AVG(max_favorable_excursion)::numeric,3) mfe, "
        f"ROUND(AVG(max_adverse_excursion)::numeric,3) mae, "
        f"ROUND(AVG(pnl_percent)::numeric,3) realized, COUNT(*) n "
        f"FROM trade_journal WHERE exit_time IS NOT NULL AND {where}"
    )).fetchone()
    if mm and mm.n:
        print(f"  MFE avg={mm.mfe}  MAE avg={mm.mae}  realized avg={mm.realized}  "
              f"(capturing realized/MFE; low ratio = giving the move back)")
    # exit reasons (top 6)
    er = session.execute(text(
        f"SELECT exit_reason, COUNT(*) n, ROUND(AVG(pnl_percent)::numeric,2) avg_pct "
        f"FROM trade_journal WHERE exit_time IS NOT NULL AND {where} "
        f"GROUP BY 1 ORDER BY n DESC LIMIT 6"
    )).fetchall()
    print("  top exit reasons:")
    for e in er:
        reason = (e.exit_reason or "?")[:50]
        print(f"    {e.n:>3}x {e.avg_pct:>6}%  {reason}")


def scan(session):
    """Book-wide: rank symbols by the SOXL/MU churn signature."""
    sql = """
        SELECT symbol,
               COUNT(*) n,
               ROUND(SUM(CASE WHEN hold_time_hours<24 THEN pnl ELSE 0 END)::numeric,0) subday_pnl,
               ROUND(SUM(CASE WHEN hold_time_hours>=72 THEN pnl ELSE 0 END)::numeric,0) hold3d_pnl,
               ROUND(SUM(pnl)::numeric,0) total_pnl
        FROM trade_journal WHERE exit_time IS NOT NULL AND account_type='demo'
        GROUP BY symbol HAVING COUNT(*) >= 15
    """
    rows = session.execute(text(sql)).fetchall()
    # Churn signature: bleeding sub-day, earning on multi-day holds.
    cohort = [r for r in rows if (r.subday_pnl or 0) < -150 and (r.hold3d_pnl or 0) > 0]
    cohort.sort(key=lambda r: r.subday_pnl)
    print(f"\n{'='*70}\nCHURN COHORT (sub-day bleed + ≥3d edge) — anti-churn candidates\n{'='*70}")
    print(f"  {'sym':6} {'n':>4} {'subdayP&L':>10} {'>=3dP&L':>9} {'totP&L':>9}")
    for r in cohort:
        print(f"  {r.symbol:6} {r.n:>4} {r.subday_pnl:>10} {r.hold3d_pnl:>9} {r.total_pnl:>9}")
    print(f"\n  {len(cohort)} symbols show the churn signature.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol")
    ap.add_argument("--account", default="all", choices=["demo", "live", "all"])
    ap.add_argument("--scan", action="store_true", help="book-wide churn-cohort scan")
    args = ap.parse_args()

    db = get_database()
    session = db.get_session()
    try:
        if args.scan:
            scan(session)
        elif args.symbol:
            diagnose(session, args.symbol.upper(), args.account)
        else:
            for s in ("SOXL", "MU", "TQQQ"):
                diagnose(session, s, args.account)
    finally:
        session.close()


if __name__ == "__main__":
    main()
