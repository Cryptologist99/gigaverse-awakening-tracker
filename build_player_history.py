#!/usr/bin/env python3
"""
Build data/player_daily_history.json — a compact per-player daily-HC-gained digest,
used by the leaderboard's per-player chart instead of fetching and parsing the full
(and ever-growing) leaderboard_history.csv client-side. That CSV carries wallets and
every twice-daily snapshot for every player (~20MB now, on track for ~60MB by event
end); this digest is just username + one number per day, no wallets, roughly 20-30x
smaller.

Buckets the twice-daily snapshots down to one end-of-day value per player per UTC
calendar date (last snapshot of the day wins), then diffs consecutive days a player
has data for into a daily-gained series. Series are stored as arrays aligned to a
shared "dates" list (one entry per player per date, null where a player has no data
that day) so date strings aren't repeated per player.
"""
import csv, json, datetime as dt
from pathlib import Path

DATA = Path(__file__).parent / "data"
LB = DATA / "leaderboard_history.csv"
OUT = DATA / "player_daily_history.json"

def main():
    # username -> {date: hc}; CSV rows are chronological (append-only), so the last
    # write for a given date is that date's last snapshot.
    by_name = {}
    with LB.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = r["username"]
            if not name:
                continue
            date = r["timestamp_utc"][:10]
            try:
                hc = int(r["hard_cores"])
            except ValueError:
                continue
            by_name.setdefault(name, {})[date] = hc

    all_dates = sorted({d for dates in by_name.values() for d in dates})
    date_index = {d: i for i, d in enumerate(all_dates)}

    players = {}
    for name, by_date in by_name.items():
        series = [None] * len(all_dates)
        sorted_dates = sorted(by_date.keys())
        for i, d in enumerate(sorted_dates):
            if i == 0:
                continue  # first day this player appears has no prior value to diff against
            gain = by_date[d] - by_date[sorted_dates[i - 1]]
            series[date_index[d]] = gain
        players[name] = series

    out = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dates": all_dates,
        "players": players,
    }
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT.name}: {len(players)} players, {len(all_dates)} dates")

if __name__ == "__main__":
    main()
