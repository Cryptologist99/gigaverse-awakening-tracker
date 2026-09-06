#!/usr/bin/env python3
"""
Daily digest of live giga.market floor prices for the Energy Value calculator's
Potion Making comparison. Runs server-side (Pi cron) because giga.market's API
does not allow cross-origin browser fetches from this site — energy.html reads
the static JSON this writes instead of hitting giga.market directly.

Recipe assumptions (per project owner, not independently verified for Lil/Mid Oil):
  craft cost = Dust x1 (Lil) / x2 (Mid) / Shard x1 (Big) — same pattern for potions and oils.
  energy cost = potions 2/4/8 (Lil/Mid/Big); oils always 2.

  data/potion_prices.json — {generatedAt, ethUsdRate, potion:{lil,mid,big}, oil:{lil,mid,big}, craftCost:{dust,shard}}
  each tier entry: {priceEth, priceUsd, n} where n = how many of the 7 same-tier items had a live ask.
"""
import datetime as dt
import json
import os

import requests

from track_supply import APP_VERSION, DATA_DIR

ORDERBOOK_URL = "https://giga.market/api/orderbook/{}"
ETH_PRICE_URL = "https://giga.market/api/eth-price"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
    "Accept": "application/json",
    "X-App-Version": APP_VERSION,
    "Referer": "https://giga.market/supply",
}
TIMEOUT_S = 30

OUT = DATA_DIR / "potion_prices.json"

JUICE_IDS = {
    "lil": ["153", "150", "301", "152", "151", "300", "307"],
    "mid": ["157", "154", "305", "156", "155", "304", "303"],
    "big": ["149", "130", "302", "132", "131", "299", "306"],
}
OIL_IDS = {
    "lil": ["823", "818", "973", "822", "824", "821", "819"],
    "mid": ["941", "936", "962", "940", "942", "939", "937"],
    "big": ["948", "943", "972", "947", "949", "946", "944"],
}
DUST_IDS = ["73", "74", "75", "76", "77", "78", "79"]
SHARD_IDS = ["80", "81", "82", "83", "84", "85", "86"]


def fetch_floor(doc_id):
    r = requests.get(ORDERBOOK_URL.format(doc_id), headers=HEADERS, timeout=TIMEOUT_S)
    r.raise_for_status()
    asks = r.json().get("asks") or []
    return min((a["price"] for a in asks if a.get("price")), default=None)


def fetch_eth_usd():
    r = requests.get(ETH_PRICE_URL, headers=HEADERS, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json().get("price")


def avg_group(doc_ids, eth_usd):
    floors = []
    for doc_id in doc_ids:
        try:
            f = fetch_floor(doc_id)
        except Exception as e:
            print(f"  {doc_id} ERROR: {e}")
            continue
        if f is not None:
            floors.append(f)
    if not floors:
        return {"priceEth": None, "priceUsd": None, "n": 0}
    avg_eth = sum(floors) / len(floors)
    return {"priceEth": round(avg_eth, 8), "priceUsd": round(avg_eth * eth_usd, 4), "n": len(floors)}


def main():
    eth_usd = fetch_eth_usd()
    print(f"ETH/USD: {eth_usd}")

    out = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ethUsdRate": eth_usd,
        "potion": {}, "oil": {}, "craftCost": {},
    }
    for tier, ids in JUICE_IDS.items():
        print(f"potion {tier}...")
        out["potion"][tier] = avg_group(ids, eth_usd)
    for tier, ids in OIL_IDS.items():
        print(f"oil {tier}...")
        out["oil"][tier] = avg_group(ids, eth_usd)
    print("dust...")
    out["craftCost"]["dust"] = avg_group(DUST_IDS, eth_usd)
    print("shard...")
    out["craftCost"]["shard"] = avg_group(SHARD_IDS, eth_usd)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
