#!/usr/bin/env python3
"""
Build data/ring_aggregate.json — silver-ring vs gold-ring aggregates for the
site's Supply tab: total supply over time, and a 7-day volume-weighted average
trade price over time (giga.market has no floor-price feed for rings; trade
price = ETH spent / items sold that day, smoothed over a trailing week since
daily volume is thin and spiky).
"""
import csv
import datetime as dt
import json
from pathlib import Path

from track_supply import RINGS, DATA_DIR

SILVER_IDS = {doc_id for doc_id, name in RINGS if not name.startswith("Golden")}
GOLD_IDS = {doc_id for doc_id, name in RINGS if name.startswith("Golden")}

SUPPLY_CSV = DATA_DIR / "ring_supply_history.csv"
PRICE_CSV = DATA_DIR / "ring_price_daily.csv"
FLOOR_CSV = DATA_DIR / "ring_floor_history.csv"
ETH_USD_CSV = DATA_DIR / "eth_usd_daily.csv"
OUT = DATA_DIR / "ring_aggregate.json"

ROLL_DAYS = 7


def group_key(doc_id):
    return "silver" if doc_id in SILVER_IDS else "gold" if doc_id in GOLD_IDS else None


def build_supply_series():
    # latest supply/holders per (doc_id, date); forward-filled per ring across dates
    latest = {}  # doc_id -> date -> (supply, holders)
    with SUPPLY_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            doc_id = r["doc_id"]
            if group_key(doc_id) is None:
                continue
            date = r["timestamp_utc"][:10]
            try:
                supply, holders = int(r["supply"]), int(r["holders"])
            except ValueError:
                continue
            latest.setdefault(doc_id, {})[date] = (supply, holders)

    all_dates = sorted({d for per_ring in latest.values() for d in per_ring})
    ring_ids = sorted(latest.keys())
    carry = {doc_id: None for doc_id in ring_ids}

    series = []
    for date in all_dates:
        totals = {"silver": [0, 0], "gold": [0, 0]}  # [supply, holders]
        counts = {"silver": 0, "gold": 0}
        for doc_id in ring_ids:
            if date in latest[doc_id]:
                carry[doc_id] = latest[doc_id][date]
            if carry[doc_id] is None:
                continue
            g = group_key(doc_id)
            supply, holders = carry[doc_id]
            totals[g][0] += supply
            totals[g][1] += holders
            counts[g] += 1
        series.append({
            "date": date,
            "silverSupply": totals["silver"][0] if counts["silver"] else None,
            "silverHolders": totals["silver"][1] if counts["silver"] else None,
            "goldSupply": totals["gold"][0] if counts["gold"] else None,
            "goldHolders": totals["gold"][1] if counts["gold"] else None,
        })
    return series


def load_eth_usd_history():
    if not ETH_USD_CSV.exists():
        return {}
    with ETH_USD_CSV.open(encoding="utf-8") as f:
        return {r["date"]: float(r["usd"]) for r in csv.DictReader(f)}


def build_price_series(eth_usd_hist):
    # per-day totals per group, then trailing 7-day volume-weighted price.
    # USD uses that SAME day's actual historical ETH/USD rate (not today's) —
    # CoinGecko's free tier only covers the trailing 365 days, so earlier dates
    # (rings launched ~April 2025) are ETH-only.
    day_totals = {}  # date -> {"silver": [items, eth], "gold": [items, eth]}
    with PRICE_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            g = group_key(r["doc_id"])
            if g is None:
                continue
            try:
                items, eth = int(r["volume_items"]), float(r["volume_eth"])
            except ValueError:
                continue
            d = day_totals.setdefault(r["date"], {"silver": [0, 0.0], "gold": [0, 0.0]})
            d[g][0] += items
            d[g][1] += eth

    dates = sorted(day_totals)
    date_epoch = {d: dt.date.fromisoformat(d).toordinal() for d in dates}

    series = []
    for i, date in enumerate(dates):
        window = [d for d in dates if 0 <= date_epoch[date] - date_epoch[d] < ROLL_DAYS]
        roll = {"silver": [0, 0.0], "gold": [0, 0.0]}
        for d in window:
            for g in ("silver", "gold"):
                roll[g][0] += day_totals[d][g][0]
                roll[g][1] += day_totals[d][g][1]
        rate = eth_usd_hist.get(date)
        silver_eth = roll["silver"][1] / roll["silver"][0] if roll["silver"][0] else None
        gold_eth = roll["gold"][1] / roll["gold"][0] if roll["gold"][0] else None
        series.append({
            "date": date,
            "silverPriceEth": round(silver_eth, 6) if silver_eth is not None else None,
            "goldPriceEth": round(gold_eth, 6) if gold_eth is not None else None,
            "silverPriceUsd": round(silver_eth * rate, 4) if silver_eth is not None and rate else None,
            "goldPriceUsd": round(gold_eth * rate, 4) if gold_eth is not None and rate else None,
        })
    return series


def build_floor_series():
    # giga.market's order book is LIVE only (no floor history API), so this is a
    # forward-filled daily snapshot series that starts accumulating from whenever
    # track_ring_floor.py first ran — it will only grow from here.
    if not FLOOR_CSV.exists():
        return [], None
    latest = {}  # doc_id -> date -> (floor_eth, floor_usd)
    last_rate = None
    with FLOOR_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            doc_id = r["doc_id"]
            if group_key(doc_id) is None:
                continue
            date = r["timestamp_utc"][:10]
            try:
                floor_eth = float(r["floor_eth"])
            except (ValueError, TypeError):
                continue
            floor_usd = float(r["floor_usd"]) if r.get("floor_usd") else None
            latest.setdefault(doc_id, {})[date] = (floor_eth, floor_usd)
            if r.get("eth_usd_rate"):
                last_rate = float(r["eth_usd_rate"])

    all_dates = sorted({d for per_ring in latest.values() for d in per_ring})
    ring_ids = sorted(latest.keys())
    carry = {doc_id: None for doc_id in ring_ids}

    series = []
    for date in all_dates:
        sums = {"silver": [0.0, 0.0, 0], "gold": [0.0, 0.0, 0]}  # [eth, usd, n]
        for doc_id in ring_ids:
            if date in latest[doc_id]:
                carry[doc_id] = latest[doc_id][date]
            if carry[doc_id] is None:
                continue
            g = group_key(doc_id)
            floor_eth, floor_usd = carry[doc_id]
            sums[g][0] += floor_eth
            sums[g][2] += 1
            if floor_usd is not None:
                sums[g][1] += floor_usd
        series.append({
            "date": date,
            "silverFloorEth": round(sums["silver"][0] / sums["silver"][2], 8) if sums["silver"][2] else None,
            "silverFloorUsd": round(sums["silver"][1] / sums["silver"][2], 4) if sums["silver"][2] else None,
            "goldFloorEth": round(sums["gold"][0] / sums["gold"][2], 8) if sums["gold"][2] else None,
            "goldFloorUsd": round(sums["gold"][1] / sums["gold"][2], 4) if sums["gold"][2] else None,
        })
    return series, last_rate


def main():
    eth_usd_hist = load_eth_usd_history()
    supply_series = build_supply_series()
    price_series = build_price_series(eth_usd_hist)
    floor_series, floor_eth_usd_rate = build_floor_series()

    cur_supply = supply_series[-1] if supply_series else {}
    prev_supply = supply_series[-2] if len(supply_series) > 1 else {}
    cur_price = price_series[-1] if price_series else {}
    cur_floor = floor_series[-1] if floor_series else {}
    latest_rate = floor_eth_usd_rate or (eth_usd_hist.get(max(eth_usd_hist)) if eth_usd_hist else None)

    def delta(cur, prev):
        return cur - prev if cur is not None and prev is not None else None

    out = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rollDays": ROLL_DAYS,
        "ethUsdRate": latest_rate,
        "current": {
            "silver": {
                "supply": cur_supply.get("silverSupply"), "holders": cur_supply.get("silverHolders"),
                "supplyDelta": delta(cur_supply.get("silverSupply"), prev_supply.get("silverSupply")),
                "tradePriceEth": cur_price.get("silverPriceEth"), "tradePriceUsd": cur_price.get("silverPriceUsd"),
                "floorEth": cur_floor.get("silverFloorEth"), "floorUsd": cur_floor.get("silverFloorUsd"),
            },
            "gold": {
                "supply": cur_supply.get("goldSupply"), "holders": cur_supply.get("goldHolders"),
                "supplyDelta": delta(cur_supply.get("goldSupply"), prev_supply.get("goldSupply")),
                "tradePriceEth": cur_price.get("goldPriceEth"), "tradePriceUsd": cur_price.get("goldPriceUsd"),
                "floorEth": cur_floor.get("goldFloorEth"), "floorUsd": cur_floor.get("goldFloorUsd"),
            },
            "supplyAsOf": supply_series[-1]["date"] if supply_series else None,
            "supplyDeltaFrom": prev_supply.get("date"),
            "tradePriceAsOf": price_series[-1]["date"] if price_series else None,
            "floorAsOf": floor_series[-1]["date"] if floor_series else None,
        },
        "supplySeries": supply_series,
        "tradePriceSeries": price_series,
        "floorSeries": floor_series,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT.name}: {len(supply_series)} supply pts, {len(price_series)} trade-price pts, {len(floor_series)} floor pts")


if __name__ == "__main__":
    main()
