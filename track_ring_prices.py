#!/usr/bin/env python3
"""
Daily trade-price history for the 14 Gigaverse rings (giga.market).

giga.market has no floor-price feed for rings (no active listings — Floor/MCap
show "-" on the site). What it does have is `item-day-data-all/{docId}`: a full
per-day trade history (volumeItems, volumeETH) going back to the item's launch.
We treat volumeETH/volumeItems as the day's average trade price.

The endpoint returns the ENTIRE history every call, so unlike supply/holders
(live snapshots) this file is fully rewritten each run — no incremental merge.

  data/ring_price_daily.csv — one row per (doc_id x day): date,doc_id,name,volume_items,volume_eth
"""
import csv
import datetime as dt
import os
from pathlib import Path

import requests

from track_supply import RINGS, APP_VERSION, DATA_DIR

DAY_DATA_URL = "https://giga.market/api/item-day-data-all/{}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
    "Accept": "application/json",
    "X-App-Version": APP_VERSION,
    "Referer": "https://giga.market/supply",
}
TIMEOUT_S = 30

OUT_CSV = DATA_DIR / "ring_price_daily.csv"
FIELDS = ["date", "doc_id", "name", "volume_items", "volume_eth"]


def fetch_day_data(doc_id):
    r = requests.get(DAY_DATA_URL.format(doc_id), headers=HEADERS, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def main():
    rows = []
    for doc_id, name in RINGS:
        try:
            data = fetch_day_data(doc_id)
        except Exception as e:
            print(f"{name} ({doc_id}) ERROR: {e}")
            continue
        for epoch_s, d in data.items():
            date = dt.datetime.fromtimestamp(int(epoch_s), dt.timezone.utc).strftime("%Y-%m-%d")
            rows.append({
                "date": date, "doc_id": doc_id, "name": name,
                "volume_items": d.get("volumeItems"), "volume_eth": d.get("volumeETH"),
            })
        print(f"{name} ({doc_id}): {len(data)} days")

    rows.sort(key=lambda r: (r["date"], r["doc_id"]))
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT_CSV.name}: {len(rows)} rows")


if __name__ == "__main__":
    main()
