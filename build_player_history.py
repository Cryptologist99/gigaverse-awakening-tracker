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

from burnpit_credit import BURN_PIT_CREDIT_AT, spans_credit

DATA = Path(__file__).parent / "data"
LB = DATA / "leaderboard_history.csv"
OUT = DATA / "player_daily_history.json"

# 2026-08-29 has ~2x the row count of a normal day (looks like duplicate/retry snapshot
# runs, not one clean snapshot) and isn't reliable — skip it entirely so it can't corrupt
# a day's gained value or the following day's diff.
EXCLUDE_DATES = {"2026-08-29"}

def main():
    # username -> {date: hc}; CSV rows are chronological (append-only), so the last
    # write for a given date is that date's last snapshot.
    by_name = {}
    last_ts = {}  # date -> that date's last snapshot timestamp (shared across players)
    with LB.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = r["username"]
            if not name:
                continue
            date = r["timestamp_utc"][:10]
            if date in EXCLUDE_DATES:
                continue
            try:
                hc = int(r["hard_cores"])
            except ValueError:
                continue
            by_name.setdefault(name, {})[date] = hc
            last_ts[date] = r["timestamp_utc"]

    all_dates = sorted({d for dates in by_name.values() for d in dates})
    date_index = {d: i for i, d in enumerate(all_dates)}

    players = {}
    credit_dates = set()  # dates whose gain would span the one-time Burn Pit payout
    starts = {}  # name -> first-appearance date, so the client can flag a gap on a
                 # player's very first plotted bar too (e.g. joined 8/28, first real bar
                 # is 8/30 because 8/29 is excluded — that's a 2-day span, not one day).
    for name, by_date in by_name.items():
        series = [None] * len(all_dates)
        sorted_dates = sorted(by_date.keys())
        starts[name] = sorted_dates[0]
        for i, d in enumerate(sorted_dates):
            if i == 0:
                continue  # first day this player appears has no prior value to diff against
            prev_d = sorted_dates[i - 1]
            if spans_credit(last_ts[prev_d], last_ts[d]):
                # Mostly the one-time Burn Pit payout, not organic gain — leave it out
                # (null) and let the client mark the day instead of charting a huge bar.
                credit_dates.add(d)
                continue
            gain = by_date[d] - by_date[prev_d]
            series[date_index[d]] = gain
        players[name] = series

    out = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dates": all_dates,
        "starts": starts,
        "burnPit": {"creditAt": BURN_PIT_CREDIT_AT, "creditDates": sorted(credit_dates)},
        "players": players,
    }
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT.name}: {len(players)} players, {len(all_dates)} dates")

if __name__ == "__main__":
    main()
