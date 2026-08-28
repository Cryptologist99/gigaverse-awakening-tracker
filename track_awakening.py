#!/usr/bin/env python3
"""
Gigaverse "The Awakening" event tracker.

Snapshots two public, unauthenticated Gigaverse endpoints on every run:
  - Prize pot (USD)         : GET https://gigaverse.io/api/itempools/public
  - Leaderboard (Hard Cores): GET https://gigaverse.io/api/leaderboard/id/{LEADERBOARD_ID}?page=N

Appends results to CSV files under ./data/ so history builds up run over run.
Meant to be run on a schedule (see .github/workflows/track.yml) so it keeps
working even when nothing is open on your machine.
"""

import csv
import time
import datetime as dt
from pathlib import Path

import requests

# --- config -----------------------------------------------------------
LEADERBOARD_ID = 8          # "The Awakening" / Hard Cores leaderboard id.
                             # If Gigaverse launches a new event with a new
                             # leaderboard, update this.
PAGE_SIZE_HINT = 200         # observed page size; loop stops on a short/empty page regardless
MAX_PAGES = 60               # safety cap so an API hiccup can't loop forever
REQUEST_DELAY_S = 0.4        # be polite between leaderboard page requests
TIMEOUT_S = 15

DATA_DIR = Path(__file__).parent / "data"
POT_CSV = DATA_DIR / "pot_history.csv"
LEADERBOARD_CSV = DATA_DIR / "leaderboard_history.csv"

HEADERS = {"User-Agent": "gigaverse-awakening-tracker/1.0 (personal use)"}


def fetch_pot(now_iso):
    r = requests.get(
        "https://gigaverse.io/api/itempools/public", headers=HEADERS, timeout=TIMEOUT_S
    )
    r.raise_for_status()
    j = r.json()
    pot_cents = j["prizePot"]["poolBalance"]
    return {
        "timestamp_utc": now_iso,
        "prizepot_usd": round(pot_cents / 100, 2),
        "prizepot_raw_cents": pot_cents,
    }


def fetch_leaderboard(now_iso):
    rows = []
    page = 1
    while page <= MAX_PAGES:
        r = requests.get(
            f"https://gigaverse.io/api/leaderboard/id/{LEADERBOARD_ID}",
            params={"page": page},
            headers=HEADERS,
            timeout=TIMEOUT_S,
        )
        r.raise_for_status()
        j = r.json()
        entries = j.get("leaderboard", [])
        if not entries:
            break
        for e in entries:
            rows.append(
                {
                    "timestamp_utc": now_iso,
                    "rank": e.get("rank"),
                    "wallet": e.get("wallet"),
                    "username": e.get("username"),
                    "hard_cores": e.get("amount"),
                }
            )
        if len(entries) < PAGE_SIZE_HINT:
            break
        page += 1
        time.sleep(REQUEST_DELAY_S)
    return rows


def append_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(rows, list):
        rows = [rows]
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        w.writerows(rows)


def main():
    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    pot = fetch_pot(now_iso)
    append_csv(POT_CSV, pot, fieldnames=list(pot.keys()))
    print(f"[{now_iso}] prize pot: ${pot['prizepot_usd']:,}")

    leaderboard = fetch_leaderboard(now_iso)
    if leaderboard:
        append_csv(
            LEADERBOARD_CSV,
            leaderboard,
            fieldnames=["timestamp_utc", "rank", "wallet", "username", "hard_cores"],
        )
        pages = -(-len(leaderboard) // PAGE_SIZE_HINT)
        print(f"[{now_iso}] leaderboard: {len(leaderboard)} entries across {pages} page(s)")
    else:
        print(f"[{now_iso}] leaderboard: no entries returned (event may be over, or API changed)")


if __name__ == "__main__":
    main()
