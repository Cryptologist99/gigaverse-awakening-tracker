#!/usr/bin/env python3
"""
Daily ETH/USD price history, via CoinGecko's public market_chart endpoint
(free tier caps historical queries at 365 days back — older ring-price dates
will simply have no USD conversion available).

Full history is returned in one call, so this file is rewritten each run,
same pattern as track_ring_prices.py.

  data/eth_usd_daily.csv — date,usd
"""
import csv
import datetime as dt

import requests

from track_supply import DATA_DIR

URL = "https://api.coingecko.com/api/v3/coins/ethereum/market_chart"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"}
TIMEOUT_S = 30

OUT_CSV = DATA_DIR / "eth_usd_daily.csv"


def main():
    r = requests.get(URL, params={"vs_currency": "usd", "days": "365", "interval": "daily"},
                      headers=HEADERS, timeout=TIMEOUT_S)
    r.raise_for_status()
    prices = r.json()["prices"]

    # one row per UTC day — CoinGecko sometimes returns two points for "today"; keep the last
    by_date = {}
    for epoch_ms, usd in prices:
        date = dt.datetime.fromtimestamp(epoch_ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")
        by_date[date] = round(usd, 2)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "usd"])
        for date in sorted(by_date):
            w.writerow([date, by_date[date]])
    print(f"wrote {OUT_CSV.name}: {len(by_date)} days")


if __name__ == "__main__":
    main()
