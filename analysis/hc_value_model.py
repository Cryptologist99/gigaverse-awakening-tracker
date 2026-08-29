#!/usr/bin/env python3
"""
Hard Core (HC) value model for Gigaverse "The Awakening".

Estimates what each HC is worth as a share of the prize pot, under the
assumed distribution mechanism: HC are converted into fixed-cost boxes that
pay out cash, and the pot is split in proportion to boxes opened.

Two models:
  A  proportional     : payout_i = HC_i / sum(eligible HC) * pot
                        (every HC of an eligible player counts)
  B  whole-boxes only : payout_i = spent_i / sum(spent) * pot,   [DEFAULT]
                        spent_i = floor(HC_i / box_cost) * box_cost
                        (HC below the next whole box is wasted)

Reads the snapshots this repo collects:
  ../data/leaderboard_history.csv   (timestamp_utc, rank, wallet, username, hard_cores)
  ../data/pot_history.csv           (timestamp_utc, prizepot_usd, prizepot_raw_cents)

By default it uses the most recent snapshot. Because both files accumulate
over time, you can point --timestamp at any past snapshot to model that moment.

Examples
--------
  python analysis/hc_value_model.py                       # latest snapshot, Model B, 500 HC box
  python analysis/hc_value_model.py --box-cost 1000       # 1000 HC box
  python analysis/hc_value_model.py --model A             # proportional model
  python analysis/hc_value_model.py --sweep 250 500 1000 2500   # box-cost sensitivity table
  python analysis/hc_value_model.py --timestamp 2026-08-28T23:11:19Z
  python analysis/hc_value_model.py --examples 500 2500 10000 100000
"""

import argparse
import csv
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LB_CSV = REPO / "data" / "leaderboard_history.csv"
POT_CSV = REPO / "data" / "pot_history.csv"

DEFAULT_EXAMPLES = [500, 1000, 2500, 5000, 10000, 50000, 100000]


def load_snapshot(timestamp=None):
    """Return (timestamp, pot_usd, [hc ints desc]) for one snapshot."""
    lb = list(csv.DictReader(open(LB_CSV, encoding="utf-8")))
    pot_rows = list(csv.DictReader(open(POT_CSV, encoding="utf-8")))
    if not lb:
        raise SystemExit("No leaderboard data yet — wait for a snapshot to run.")

    if timestamp is None:
        timestamp = max(r["timestamp_utc"] for r in lb)

    snap = [r for r in lb if r["timestamp_utc"] == timestamp]
    if not snap:
        avail = sorted({r["timestamp_utc"] for r in lb})
        raise SystemExit(f"No snapshot at {timestamp}. Available:\n  " + "\n  ".join(avail))

    def as_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    hc = sorted((h for h in (as_int(r["hard_cores"]) for r in snap) if h is not None), reverse=True)

    pot_match = [p for p in pot_rows if p["timestamp_utc"] == timestamp]
    if not pot_match:
        # fall back to nearest-in-time pot if the pot row is missing for this ts
        pot_match = [max(pot_rows, key=lambda p: p["timestamp_utc"])]
    pot = float(pot_match[0]["prizepot_usd"])
    return timestamp, pot, hc


def model(hc, pot, box_cost, kind="B", min_participate=None):
    """Compute value-per-HC and pool stats for one (box_cost, model)."""
    if min_participate is None:
        min_participate = box_cost  # need at least one box to participate
    elig = [h for h in hc if h >= min_participate]
    gated = [h for h in hc if h < min_participate]

    if kind == "A":
        pool = sum(elig)                      # every eligible HC counts
        spent_of = lambda h: h
    else:  # Model B — whole boxes only
        pool = sum((h // box_cost) * box_cost for h in elig)
        spent_of = lambda h: (h // box_cost) * box_cost

    vphc = pot / pool if pool else 0.0        # $ per HC that counts
    return {
        "box_cost": box_cost,
        "kind": kind,
        "pot": pot,
        "n_all": len(hc),
        "hc_all": sum(hc),
        "n_gated": len(gated),
        "hc_gated": sum(gated),
        "n_elig": len(elig),
        "hc_elig": sum(elig),
        "pool": pool,                          # HC that actually earns
        "wasted": sum(elig) - pool if kind == "B" else 0,
        "vphc": vphc,
        "vpbox": vphc * box_cost,
        "n_boxes": sum(h // box_cost for h in elig),
        "elig": elig,
        "spent_of": spent_of,
    }


def pct(x, whole):
    return 100.0 * x / whole if whole else 0.0


def print_report(ts, m, examples):
    box, kind = m["box_cost"], m["kind"]
    name = "proportional (all eligible HC)" if kind == "A" else "whole boxes only (remainder wasted)"
    print(f"Snapshot: {ts}")
    print(f"Prize pot: ${m['pot']:,.2f}")
    print(f"Box cost: {box:,} HC   |   Model {kind} - {name}")
    print("=" * 72)
    print(f"Players on leaderboard : {m['n_all']:,}   (total {m['hc_all']:,} HC)")
    print(f"Gated out (< {box:,} HC)  : {m['n_gated']:,} "
          f"({pct(m['n_gated'], m['n_all']):.1f}% of players, "
          f"{pct(m['hc_gated'], m['hc_all']):.2f}% of HC)")
    print(f"Eligible               : {m['n_elig']:,} "
          f"({pct(m['n_elig'], m['n_all']):.1f}% of players)")
    if kind == "B":
        print(f"Boxes opened           : {m['n_boxes']:,}   "
              f"(spent {m['pool']:,} HC, wasted {m['wasted']:,} HC)")
    print("=" * 72)
    print(f"Value per HC (counted) : ${m['vphc']:.6f}   ({pct(m['vphc'], m['pot']):.6f}% of pot)")
    print(f"Value per box          : ${m['vpbox']:,.4f}  per {box:,} HC")
    if m["n_boxes"]:
        print(f"Implied $ per box      : ${m['pot'] / m['n_boxes']:,.4f}")
    print("=" * 72)

    e = m["elig"]
    if e:
        q = st.quantiles(e, n=100) if len(e) >= 100 else None
        line = (f"Eligible HC: min {min(e):,} | median {int(st.median(e)):,} | "
                f"mean {int(st.mean(e)):,} | max {max(e):,}")
        if q:
            line += f" | 90th {int(q[89]):,} | 99th {int(q[98]):,}"
        print(line)
        print("=" * 72)

    print(f"Payout examples (Model {kind}):")
    for h in examples:
        spent = m["spent_of"](h)
        payout = spent * m["vphc"]
        waste = h - spent
        wtxt = f", wastes {waste:,}" if (kind == "B" and waste) else ""
        boxes = f"{h // box:,} box(es), " if kind == "B" else ""
        print(f"  {h:>8,} HC -> ${payout:>10,.2f}   {boxes}spends {spent:,} HC{wtxt}"
              f"   ({pct(spent if kind=='B' else h, m['pool']):.4f}% of pot)")


def print_sweep(ts, pot, hc, box_costs, kind):
    print(f"Snapshot: {ts}   |   Prize pot: ${pot:,.2f}   |   Model {kind}")
    print("Box-cost sensitivity")
    print("=" * 72)
    hdr = f"{'Box HC':>8} | {'Eligible':>8} | {'%players':>8} | {'Spent HC':>13} | {'$/HC':>10} | {'$/box':>9}"
    print(hdr)
    print("-" * len(hdr))
    for bc in box_costs:
        m = model(hc, pot, bc, kind)
        print(f"{bc:>8,} | {m['n_elig']:>8,} | {pct(m['n_elig'], m['n_all']):>7.1f}% | "
              f"{m['pool']:>13,} | ${m['vphc']:>9.6f} | ${m['vpbox']:>8.4f}")
    print("=" * 72)
    print("Lower box cost -> more players & HC included -> pot split over more HC -> lower $/HC.")


def main():
    ap = argparse.ArgumentParser(description="Model HC value as a share of the Gigaverse prize pot.")
    ap.add_argument("--box-cost", type=int, default=500, help="HC per box (default 500)")
    ap.add_argument("--model", choices=["A", "B"], default="B", help="A=proportional, B=whole-boxes (default B)")
    ap.add_argument("--timestamp", default=None, help="snapshot timestamp_utc (default: latest)")
    ap.add_argument("--min-participate", type=int, default=None,
                    help="min HC to participate (default: = box cost)")
    ap.add_argument("--examples", type=int, nargs="+", default=DEFAULT_EXAMPLES,
                    help="HC amounts to show payouts for")
    ap.add_argument("--sweep", type=int, nargs="+", default=None,
                    help="box costs to compare in a sensitivity table (overrides single report)")
    args = ap.parse_args()

    ts, pot, hc = load_snapshot(args.timestamp)

    if args.sweep:
        print_sweep(ts, pot, hc, args.sweep, args.model)
    else:
        m = model(hc, pot, args.box_cost, args.model, args.min_participate)
        print_report(ts, m, sorted(set(args.examples)))


if __name__ == "__main__":
    main()
