#!/usr/bin/env python3
"""
One-time backfill of data/ring_supply_history.csv from giga.market's
supply-history (daily supply + holder COUNTS, back to ~Nov 2025).

Run this ONCE to seed the history file; track_supply.py then appends "live" rows
going forward. Wallet-level data (ring_holders_top.csv) can't be backfilled —
giga.market only exposes the *current* top-holders list, so that file starts
accumulating from the first daily run.

Overwrites ring_supply_history.csv (re-running just rebuilds the same base).
"""
import csv
from pathlib import Path

import requests

from track_supply import RINGS, HEADERS, TIMEOUT_S, DATA_DIR, SUPPLY_CSV, SUPPLY_FIELDS

SH_URL = "https://giga.market/api/supply-history/{}"


def main():
    rows = []
    for doc_id, name in RINGS:
        r = requests.get(SH_URL.format(doc_id), headers=HEADERS, timeout=TIMEOUT_S)
        r.raise_for_status()
        pts = r.json().get("dailyData", [])
        for p in pts:
            rows.append({
                "timestamp_utc": p.get("timestamp"), "doc_id": doc_id, "name": name,
                "supply": p.get("supply"), "holders": p.get("holders"), "source": "backfill",
            })
        print(f"{name} ({doc_id}): {len(pts)} daily points")

    rows.sort(key=lambda x: (x["timestamp_utc"] or "", x["doc_id"]))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with SUPPLY_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SUPPLY_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} backfill rows to {SUPPLY_CSV}")


if __name__ == "__main__":
    main()
