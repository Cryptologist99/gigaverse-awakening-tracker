#!/usr/bin/env python3
"""
Live market context for the Burn Pit tracker: circulating supply (from
Gigaverse's own item indexer, CORS-open) and giga.market floor price (CORS-
blocked from the browser, so fetched here) for each of the 154 Burn Pit
items. burn_pit.html reads this alongside the manually-captured
data/burn_pit.json to compute the worst-case ("if everyone burns everything")
HC/unit rate and cost-per-HC at both the current and worst-case rate.

  GET https://gigaverse.io/api/indexer/gameitems
    -> per item MINT_COUNT_CID / BURN_COUNT_CID; circulating supply = mint - burn.
  GET https://giga.market/api/orderbook/{docId} -> asks (ascending); floor = min ask.
  GET https://giga.market/api/eth-price -> ETH/USD.

  data/burn_pit_market.json — {generatedAt, ethUsdRate, items: {itemId: {totalSupply, floorEth, floorUsd}}}
"""
import datetime as dt
import json

import requests

from track_supply import APP_VERSION, DATA_DIR

GAMEITEMS_URL = "https://gigaverse.io/api/indexer/gameitems"
ORDERBOOK_URL = "https://giga.market/api/orderbook/{}"
ETH_PRICE_URL = "https://giga.market/api/eth-price"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
    "Accept": "application/json",
    "X-App-Version": APP_VERSION,
    "Referer": "https://giga.market/supply",
}
TIMEOUT_S = 30

IN_BURNPIT = DATA_DIR / "burn_pit.json"
OUT = DATA_DIR / "burn_pit_market.json"


def fetch_supply_by_id():
    r = requests.get(GAMEITEMS_URL, timeout=TIMEOUT_S)
    r.raise_for_status()
    out = {}
    for e in r.json().get("entities", []):
        doc_id = e.get("docId")
        mint, burn = e.get("MINT_COUNT_CID"), e.get("BURN_COUNT_CID")
        if doc_id is not None and mint is not None:
            out[str(doc_id)] = max(0, mint - (burn or 0))
    return out


def fetch_floor(doc_id):
    r = requests.get(ORDERBOOK_URL.format(doc_id), headers=HEADERS, timeout=TIMEOUT_S)
    r.raise_for_status()
    asks = r.json().get("asks") or []
    return min((a["price"] for a in asks if a.get("price")), default=None)


def fetch_eth_usd():
    r = requests.get(ETH_PRICE_URL, headers=HEADERS, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json().get("price")


def main():
    with IN_BURNPIT.open(encoding="utf-8") as f:
        burnpit = json.load(f)
    item_ids = [str(it["itemId"]) for it in burnpit["items"]]

    eth_usd = fetch_eth_usd()
    print(f"ETH/USD: {eth_usd}")
    supply_by_id = fetch_supply_by_id()
    print(f"fetched supply for {len(supply_by_id)} items from gameitems indexer")

    items = {}
    for doc_id in item_ids:
        try:
            floor_eth = fetch_floor(doc_id)
        except Exception as e:
            print(f"  {doc_id} ERROR: {e}")
            floor_eth = None
        floor_usd = round(floor_eth * eth_usd, 6) if floor_eth and eth_usd else None
        items[doc_id] = {
            "totalSupply": supply_by_id.get(doc_id),
            "floorEth": floor_eth,
            "floorUsd": floor_usd,
        }

    out = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ethUsdRate": eth_usd,
        "items": items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT.name}: {len(items)} items")


if __name__ == "__main__":
    main()
