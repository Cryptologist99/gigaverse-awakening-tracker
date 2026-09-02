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


def build_price_series():
    # per-day totals per group, then trailing 7-day volume-weighted price
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
        series.append({
            "date": date,
            "silverPriceEth": round(roll["silver"][1] / roll["silver"][0], 6) if roll["silver"][0] else None,
            "goldPriceEth": round(roll["gold"][1] / roll["gold"][0], 6) if roll["gold"][0] else None,
        })
    return series


def main():
    supply_series = build_supply_series()
    price_series = build_price_series()

    cur_supply = supply_series[-1] if supply_series else {}
    cur_price = price_series[-1] if price_series else {}

    out = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rollDays": ROLL_DAYS,
        "current": {
            "silver": {
                "supply": cur_supply.get("silverSupply"), "holders": cur_supply.get("silverHolders"),
                "priceEth": cur_price.get("silverPriceEth"),
            },
            "gold": {
                "supply": cur_supply.get("goldSupply"), "holders": cur_supply.get("goldHolders"),
                "priceEth": cur_price.get("goldPriceEth"),
            },
            "supplyAsOf": supply_series[-1]["date"] if supply_series else None,
            "priceAsOf": price_series[-1]["date"] if price_series else None,
        },
        "supplySeries": supply_series,
        "priceSeries": price_series,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT.name}: {len(supply_series)} supply pts, {len(price_series)} price pts")


if __name__ == "__main__":
    main()
