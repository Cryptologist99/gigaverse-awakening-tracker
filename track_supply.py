#!/usr/bin/env python3
"""
Daily supply + holders tracker for Gigaverse silver/gold rings (giga.market).

For each ring, giga.market streams (SSE) the LIVE total supply, total holder
count, and the top-100 holders (wallet, username, balance). We append:

  data/ring_supply_history.csv  — one row per (run x ring): timestamp, supply, holders
  data/ring_holders_top.csv     — one row per (run x ring x holder): top-100 wallets

Endpoint: GET https://giga.market/api/holders/{docId}  (text/event-stream)
Item docIds come from Gigaverse's item metadata (gigaverse.io/api/indexer/gameitems).
"""
import csv
import json
import os
import datetime as dt
from pathlib import Path

import requests

# docId -> display name. Silver rings are the 134-140 block; gold rings 243-249.
# (In Gigaverse metadata the Athena silver ring is named just "Athena Ring".)
RINGS = [
    ("134", "Chobo Silver Ring"),
    ("135", "Crusader Silver Ring"),
    ("136", "Overseer Silver Ring"),
    ("137", "Athena Silver Ring"),
    ("138", "Archon Silver Ring"),
    ("139", "Foxglove Silver Ring"),
    ("140", "Summoner Silver Ring"),
    ("243", "Golden Archon Ring"),
    ("244", "Golden Athena Ring"),
    ("245", "Golden Chobo Ring"),
    ("246", "Golden Crusader Ring"),
    ("247", "Golden Foxglove Ring"),
    ("248", "Golden Overseer Ring"),
    ("249", "Golden Summoner Ring"),
]

HOLDERS_URL = "https://giga.market/api/holders/{}"
# giga.market gates its API behind an X-App-Version header (else HTTP 426
# "Client version missing"). This value can change when giga.market ships a new
# build — if every ring starts returning 426, grab the current value from the
# site (window.fetch is patched to send "X-App-Version") and update it here, or
# set the GIGA_APP_VERSION env var to override without editing code.
APP_VERSION = os.environ.get("GIGA_APP_VERSION", "v260301-UIHBksjdfjhdhjs-002")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
    "Accept": "text/event-stream",
    "X-App-Version": APP_VERSION,
    "Referer": "https://giga.market/supply",
}
TIMEOUT_S = 30

DATA_DIR = Path(os.environ.get("TRACKER_DATA_DIR") or (Path(__file__).parent / "data"))
SUPPLY_CSV = DATA_DIR / "ring_supply_history.csv"
HOLDERS_CSV = DATA_DIR / "ring_holders_top.csv"

SUPPLY_FIELDS = ["timestamp_utc", "doc_id", "name", "supply", "holders", "source"]
HOLDER_FIELDS = ["timestamp_utc", "doc_id", "name", "rank", "wallet", "username", "balance"]


def fetch_holders(doc_id):
    """Consume the SSE stream and return the first JSON payload with topHolders."""
    with requests.get(HOLDERS_URL.format(doc_id), headers=HEADERS, stream=True, timeout=TIMEOUT_S) as r:
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                payload = line[5:].strip()
                if payload.startswith("{"):
                    data = json.loads(payload)
                    if "topHolders" in data or "totalSupply" in data:
                        return data
    return None


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
    supply_rows, holder_rows = [], []
    for doc_id, name in RINGS:
        try:
            data = fetch_holders(doc_id)
        except Exception as e:
            print(f"[{now}] {name} ({doc_id}) ERROR: {e}")
            continue
        if not data:
            print(f"[{now}] {name} ({doc_id}) no data")
            continue
        supply_rows.append({
            "timestamp_utc": now, "doc_id": doc_id, "name": name,
            "supply": data.get("totalSupply"), "holders": data.get("totalHolders"),
            "source": "live",
        })
        for i, h in enumerate(data.get("topHolders", []), 1):
            holder_rows.append({
                "timestamp_utc": now, "doc_id": doc_id, "name": name, "rank": i,
                "wallet": h.get("address"), "username": h.get("username"), "balance": h.get("balance"),
            })
        print(f"[{now}] {name}: supply {data.get('totalSupply')} | holders {data.get('totalHolders')} | top {len(data.get('topHolders', []))}")

    if supply_rows:
        append_csv(SUPPLY_CSV, supply_rows, SUPPLY_FIELDS)
    if holder_rows:
        append_csv(HOLDERS_CSV, holder_rows, HOLDER_FIELDS)
    print(f"[{now}] wrote {len(supply_rows)} supply rows, {len(holder_rows)} holder rows")


if __name__ == "__main__":
    main()
