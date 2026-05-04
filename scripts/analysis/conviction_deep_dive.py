"""Deep-dive analysis of live P&L across conviction scorer components,
templates, symbols, sectors, regimes, directions, asset classes.

Goal: find the real signal in the 700-trade dataset, beyond the simple
conviction-bucket view. Identify the alpha drivers and the loss sources.

Usage (on EC2):
  set -a; source /home/ubuntu/alphacent/.env.production; set +a
  /home/ubuntu/alphacent/venv/bin/python3 scripts/analysis/conviction_deep_dive.py
"""
from __future__ import annotations

import os
import sys
import json
from collections import defaultdict


def _stats(pnls):
    n = len(pnls)
    if n == 0:
        return n, 0.0, 0.0, 0.0, 0.0
    avg = sum(pnls) / n
    total = sum(pnls)
    wr = 100.0 * sum(1 for p in pnls if p > 0) / n
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    return n, avg, wr, total, (avg_win / abs(avg_loss)) if avg_loss else 0.0


def _print_table(title, groups, min_n=5, sort_by="total"):
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)
    print(f"{'group':<40} {'n':>4} {'avg':>8} {'wr%':>6} {'total':>10} {'RR':>5}")
    print("-" * 72)

    rows = []
    for k, pnls in groups.items():
        n, avg, wr, total, rr = _stats(pnls)
        if n >= min_n:
            rows.append((k, n, avg, wr, total, rr))

    if sort_by == "total":
        rows.sort(key=lambda r: r[4], reverse=True)
    elif sort_by == "avg":
        rows.sort(key=lambda r: r[2], reverse=True)

    for k, n, avg, wr, total, rr in rows[:25]:
        label = str(k)[:40]
        print(f"{label:<40} {n:>4} {avg:>8.2f} {wr:>6.1f} {total:>10.2f} {rr:>5.2f}")


def main() -> int:
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 not available")
        return 1

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set")
        return 1

    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("""
        SELECT
          tj.trade_id, tj.strategy_id, tj.symbol, tj.side, tj.pnl, tj.pnl_percent,
          tj.conviction_score, tj.market_regime, tj.sector,
          tj.hold_time_hours, tj.max_adverse_excursion, tj.max_favorable_excursion,
          tj.entry_time, tj.trade_metadata, tj.ml_confidence
        FROM trade_journal tj
        WHERE tj.pnl IS NOT NULL
          AND tj.conviction_score IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    print(f"Trades analyzed: {len(rows)}")

    # Derive template_name and asset class from metadata / symbol
    from src.core.tradeable_instruments import (
        DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX, DEMO_ALLOWED_INDICES,
        DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_ETFS,
    )
    CRYPTO = set(DEMO_ALLOWED_CRYPTO)
    FOREX = set(DEMO_ALLOWED_FOREX)
    INDEX = set(DEMO_ALLOWED_INDICES)
    COMMOD = set(DEMO_ALLOWED_COMMODITIES)
    ETFS = set(DEMO_ALLOWED_ETFS)

    def asset_class(sym):
        s = sym.upper()
        if s in CRYPTO: return "crypto"
        if s in FOREX: return "forex"
        if s in INDEX: return "index"
        if s in COMMOD: return "commodity"
        if s in ETFS: return "etf"
        return "stock"

    enriched = []
    for r in rows:
        (tid, sid, sym, side, pnl, pnl_pct, conv, regime, sector,
         hold_hrs, mae, mfe, entry_time, meta, ml_conf) = r
        tmpl = None
        if meta:
            try:
                md = meta if isinstance(meta, dict) else json.loads(meta)
                tmpl = md.get("template_name")
            except Exception:
                pass
        aclass = asset_class(sym)
        enriched.append({
            "trade_id": tid, "strategy_id": sid, "symbol": sym, "side": side,
            "pnl": float(pnl), "pnl_pct": float(pnl_pct) if pnl_pct is not None else None,
            "conv": float(conv),
            "regime": regime, "sector": sector, "template": tmpl,
            "asset_class": aclass,
            "hold_hrs": float(hold_hrs) if hold_hrs else None,
            "mae": float(mae) if mae else None,
            "mfe": float(mfe) if mfe else None,
            "entry_time": entry_time,
            "ml_conf": float(ml_conf) if ml_conf else None,
        })

    total_pnl = sum(t["pnl"] for t in enriched)
    winners = [t for t in enriched if t["pnl"] > 0]
    losers = [t for t in enriched if t["pnl"] < 0]
    print(f"Total P&L: ${total_pnl:,.2f}")
    print(f"Winners: {len(winners)} (avg +${sum(t['pnl'] for t in winners)/max(len(winners),1):.2f})")
    print(f"Losers: {len(losers)} (avg ${sum(t['pnl'] for t in losers)/max(len(losers),1):.2f})")
    print(f"Payoff ratio: {(sum(t['pnl'] for t in winners)/max(len(winners),1)) / abs(sum(t['pnl'] for t in losers)/max(len(losers),1)):.2f}")

    # =================================================================
    # 1. By conviction decile (finer than 5-point buckets)
    # =================================================================
    decile_groups = defaultdict(list)
    for t in enriched:
        c = t["conv"]
        if c < 50: b = "0:<50"
        elif c < 55: b = "1:50-55"
        elif c < 60: b = "2:55-60"
        elif c < 62: b = "3:60-62"
        elif c < 65: b = "4:62-65"
        elif c < 67: b = "5:65-67"
        elif c < 70: b = "6:67-70"
        elif c < 75: b = "7:70-75"
        else: b = "8:>=75"
        decile_groups[b].append(t["pnl"])
    _print_table("Finer-grain conviction buckets (all trades)", decile_groups, min_n=3)

    # =================================================================
    # 2. By template (the real alpha drivers)
    # =================================================================
    tmpl_groups = defaultdict(list)
    for t in enriched:
        if t["template"]:
            tmpl_groups[t["template"]].append(t["pnl"])
    _print_table("Best templates by total P&L (min n=5)", tmpl_groups, min_n=5, sort_by="total")

    tmpl_avg = defaultdict(list)
    for t in enriched:
        if t["template"]:
            tmpl_avg[t["template"]].append(t["pnl"])
    _print_table("Best templates by avg P&L per trade (min n=5)", tmpl_avg, min_n=5, sort_by="avg")

    # =================================================================
    # 3. By symbol (concentration of alpha)
    # =================================================================
    sym_groups = defaultdict(list)
    for t in enriched:
        sym_groups[t["symbol"]].append(t["pnl"])
    _print_table("Symbols by total P&L (min n=3)", sym_groups, min_n=3, sort_by="total")

    # =================================================================
    # 4. By (template, symbol) pair
    # =================================================================
    pair_groups = defaultdict(list)
    for t in enriched:
        if t["template"]:
            pair_groups[f"{t['template'][:25]} × {t['symbol']}"].append(t["pnl"])
    _print_table("Best (template, symbol) pairs by total P&L (min n=3)", pair_groups, min_n=3)

    # =================================================================
    # 5. By asset class
    # =================================================================
    ac_groups = defaultdict(list)
    for t in enriched:
        ac_groups[t["asset_class"]].append(t["pnl"])
    _print_table("By asset class", ac_groups, min_n=1, sort_by="total")

    # =================================================================
    # 6. By side (LONG vs SHORT)
    # =================================================================
    side_groups = defaultdict(list)
    for t in enriched:
        side_groups[str(t["side"])].append(t["pnl"])
    _print_table("By side", side_groups, min_n=1, sort_by="total")

    # =================================================================
    # 7. By market regime at entry
    # =================================================================
    reg_groups = defaultdict(list)
    for t in enriched:
        reg_groups[t["regime"] or "unknown"].append(t["pnl"])
    _print_table("By market regime at entry", reg_groups, min_n=3, sort_by="total")

    # =================================================================
    # 8. Hold time quartiles
    # =================================================================
    hold_groups = defaultdict(list)
    for t in enriched:
        h = t["hold_hrs"]
        if h is None: continue
        if h < 24: b = "a:<1d"
        elif h < 72: b = "b:1-3d"
        elif h < 168: b = "c:3-7d"
        elif h < 336: b = "d:7-14d"
        else: b = "e:>=14d"
        hold_groups[b].append(t["pnl"])
    _print_table("By hold duration", hold_groups, min_n=5, sort_by="total")

    # =================================================================
    # 9. Cross: conviction bucket × asset class
    # =================================================================
    cross_groups = defaultdict(list)
    for t in enriched:
        c = t["conv"]
        if c < 60: b = "<60"
        elif c < 65: b = "60-65"
        elif c < 70: b = "65-70"
        elif c < 75: b = "70-75"
        else: b = ">=75"
        cross_groups[f"{b}/{t['asset_class']}"].append(t["pnl"])
    _print_table("Conviction bucket × asset class", cross_groups, min_n=5)

    # =================================================================
    # 10. Top/bottom 15 trades
    # =================================================================
    print()
    print("=" * 72)
    print("Top 15 winners")
    print("=" * 72)
    for t in sorted(enriched, key=lambda x: x["pnl"], reverse=True)[:15]:
        print(f"  {t['symbol']:<8} {t['side']:<6} conv={t['conv']:5.1f}  "
              f"pnl=${t['pnl']:8.2f}  hold={t['hold_hrs'] or 0:5.1f}h  "
              f"tmpl={(t['template'] or '?')[:30]}")

    print()
    print("=" * 72)
    print("Top 15 losers")
    print("=" * 72)
    for t in sorted(enriched, key=lambda x: x["pnl"])[:15]:
        print(f"  {t['symbol']:<8} {t['side']:<6} conv={t['conv']:5.1f}  "
              f"pnl=${t['pnl']:8.2f}  hold={t['hold_hrs'] or 0:5.1f}h  "
              f"tmpl={(t['template'] or '?')[:30]}")

    # =================================================================
    # 11. Correlation: conviction vs realized outcomes
    # =================================================================
    print()
    print("=" * 72)
    print("Correlation: conviction score vs outcomes")
    print("=" * 72)
    convs = [t["conv"] for t in enriched]
    pnls = [t["pnl"] for t in enriched]

    # Pearson correlation
    if len(convs) > 10:
        n = len(convs)
        mean_c = sum(convs) / n
        mean_p = sum(pnls) / n
        num = sum((c - mean_c) * (p - mean_p) for c, p in zip(convs, pnls))
        den_c = (sum((c - mean_c)**2 for c in convs)) ** 0.5
        den_p = (sum((p - mean_p)**2 for p in pnls)) ** 0.5
        pearson = num / (den_c * den_p) if den_c and den_p else 0.0
        print(f"  Pearson correlation (conv, pnl): {pearson:+.3f}")

        # Spearman rank correlation — better for non-linear
        ranked_c = sorted(range(n), key=lambda i: convs[i])
        ranked_p = sorted(range(n), key=lambda i: pnls[i])
        rank_c = [0]*n; rank_p = [0]*n
        for r, i in enumerate(ranked_c): rank_c[i] = r
        for r, i in enumerate(ranked_p): rank_p[i] = r
        mean_rc = (n - 1) / 2
        num_s = sum((rc - mean_rc) * (rp - mean_rc) for rc, rp in zip(rank_c, rank_p))
        den_s = sum((rc - mean_rc)**2 for rc in rank_c)
        spearman = num_s / den_s if den_s else 0.0
        print(f"  Spearman rank correlation: {spearman:+.3f}")

        # Binary correlation: conviction > 65 -> profit?
        hi = [t["pnl"] > 0 for t in enriched if t["conv"] >= 65]
        lo = [t["pnl"] > 0 for t in enriched if t["conv"] < 65]
        hi_wr = 100 * sum(hi) / len(hi) if hi else 0
        lo_wr = 100 * sum(lo) / len(lo) if lo else 0
        print(f"  Win rate if conv >= 65: {hi_wr:.1f}% (n={len(hi)})")
        print(f"  Win rate if conv <  65: {lo_wr:.1f}% (n={len(lo)})")
        print(f"  Lift: {hi_wr - lo_wr:+.1f} percentage points")

    return 0


if __name__ == "__main__":
    sys.exit(main())
