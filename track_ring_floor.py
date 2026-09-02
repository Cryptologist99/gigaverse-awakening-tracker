#!/usr/bin/env python3
"""
Daily floor-price snapshot for the 14 Gigaverse rings (giga.market).

Unlike item-day-data-all (full trade-volume history in one call), the order
book is LIVE only — giga.market has no floor-price history API. So this
accumulates one snapshot per run, same pattern as track_supply.py.

  GET /api/orderbook/{docId} -> {itemId, asks:[{price, amount, ...}], ...}
    asks are sorted ascending; the floor is the lowest ask price (ETH).
  GET /api/eth-price -> {"data":{"ethereum":{"usd": <rate>}}, "price": <rate>}

  data/ring_floor_history.csv — one row per (run x ring): timestamp,doc_id,name,floor_eth,eth_usd_rate,floor_usd
"""
import csv
import os
import datetime as dt
from pathlib import Path

import requests

from track_supply import RINGS, APP_VERSION, DATA_DIR

ORDERBOOK_URL = "https://giga.market/api/orderbook/{}"
ETH_PRICE_URL = "https://giga.market/api/eth-price"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
    "Accept": "application/json",
    "X-App-Version": APP_VERSION,
    "Referer": "https://giga.market/supply",
}
TIMEOUT_S = 30

OUT_CSV = DATA_DIR / "ring_floor_history.csv"
FIELDS = ["timestamp_utc", "doc_id", "name", "floor_eth", "eth_usd_rate", "floor_usd"]


def fetch_floor(doc_id):
    r = requests.get(ORDERBOOK_URL.format(doc_id), headers=HEADERS, timeout=TIMEOUT_S)
    r.raise_for_status()
    asks = r.json().get("asks") or []
    return min((a["price"] for a in asks if a.get("price")), default=None)


def fetch_eth_usd():
    r = requests.get(ETH_PRICE_URL, headers=HEADERS, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json().get("price")


def append_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            w.writeheader()
        w.writerows(rows)


def main():
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    eth_usd = fetch_eth_usd()
    print(f"[{now}] ETH/USD: {eth_usd}")

    rows = []
    for doc_id, name in RINGS:
        try:
            floor_eth = fetch_floor(doc_id)
        except Exception as e:
            print(f"[{now}] {name} ({doc_id}) ERROR: {e}")
            continue
        floor_usd = round(floor_eth * eth_usd, 4) if floor_eth and eth_usd else None
        rows.append({
            "timestamp_utc": now, "doc_id": doc_id, "name": name,
            "floor_eth": floor_eth, "eth_usd_rate": eth_usd, "floor_usd": floor_usd,
        })
        print(f"[{now}] {name}: floor {floor_eth} ETH (${floor_usd})" if floor_eth else f"[{now}] {name}: no asks")

    if rows:
        append_csv(OUT_CSV, rows, FIELDS)
    print(f"[{now}] wrote {len(rows)} floor rows")


if __name__ == "__main__":
    main()
