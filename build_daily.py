#!/usr/bin/env python3
"""
Build data/leaderboard_daily.json — a small digest the website reads instead of
the full history CSV.

Anchors on the **1:59 PM US Eastern** daily snapshot (17:59 UTC during EDT, the
event window). The board is that snapshot; each player's daily growth is measured
against the *previous* daily (PM) snapshot. Until two PM snapshots exist, it falls
back to the oldest snapshot we have as the baseline (provisional mode).

No wallets are written to the digest — wallets are only used here to match players
between snapshots. The full CSVs are left untouched for later analysis.
"""
import csv, json, datetime as dt
from pathlib import Path

DATA = Path(__file__).parent / "data"
LB   = DATA / "leaderboard_history.csv"
POT  = DATA / "pot_history.csv"
OUT  = DATA / "leaderboard_daily.json"

def is_pm(ts):
    # ts = "YYYY-MM-DDTHH:MM:SSZ"; 1:59 PM ET (EDT) = 17:59 UTC. Window tolerates delays.
    try:
        return 16 <= int(ts[11:13]) < 20
    except (ValueError, IndexError):
        return False

def main():
    rows_by_ts, order, seen = {}, [], set()
    with LB.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts = r["timestamp_utc"]
            if ts not in seen:
                seen.add(ts); order.append(ts)
            rows_by_ts.setdefault(ts, []).append(r)
    all_ts = sorted(order)
    if not all_ts:
        raise SystemExit("no snapshots yet")

    pm = [t for t in all_ts if is_pm(t)]
    if len(pm) >= 2:
        cur, prev, mode = pm[-1], pm[-2], "daily"
    elif pm:
        cur = pm[-1]
        prev = all_ts[0] if all_ts[0] != cur else None      # oldest snapshot as baseline
        mode = "provisional"
    else:
        cur = all_ts[-1]
        prev = all_ts[0] if len(all_ts) >= 2 else None       # newest vs oldest, provisional
        mode = "provisional"

    pot = {}
    with POT.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try: pot[r["timestamp_utc"]] = round(float(r["prizepot_usd"]), 2)
            except ValueError: pass

    def wmap(ts):
        m = {}
        for r in rows_by_ts.get(ts, []):
            w = (r["wallet"] or "").lower()
            if w:
                m[w] = {"rank": int(r["rank"]), "amount": int(r["hard_cores"])}
        return m

    def meta(ts):
        rs = rows_by_ts.get(ts, [])
        return {"ts": ts, "pot": pot.get(ts),
                "totalHC": sum(int(x["hard_cores"]) for x in rs), "holders": len(rs)}

    # epoch + first-seen (earliest snapshot each wallet appears in), for a real avg/day
    def epoch(ts):
        return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
    first_seen = {}
    for ts in all_ts:
        for r in rows_by_ts[ts]:
            w = (r["wallet"] or "").lower()
            if w and w not in first_seen:
                first_seen[w] = (ts, int(r["hard_cores"]))
    cur_epoch = epoch(cur)

    prev_map = wmap(prev) if prev else {}
    players = []
    for r in sorted(rows_by_ts[cur], key=lambda r: int(r["rank"])):
        w = (r["wallet"] or "").lower()
        p = prev_map.get(w)
        amt, rank = int(r["hard_cores"]), int(r["rank"])
        delta = (amt - p["amount"]) if p else None            # since previous (daily) snapshot
        # avg/day: total growth since first seen ÷ days tracked (needs >= ~half a day of span)
        avg = None
        fs = first_seen.get(w)
        if fs and fs[0] != cur:
            days = (cur_epoch - epoch(fs[0])) / 86400.0
            if days >= 0.5:
                avg = round((amt - fs[1]) / days)
        players.append({
            "rank": rank,
            "name": r["username"] or "",
            "hc": amt,
            "hcDelta": delta,
            "rankDelta": (p["rank"] - rank) if p else None,
            "isNew": p is None,
            "avgPerDay": avg,
        })

    out = {
        "mode": mode,
        "generatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "current": meta(cur),
        "previous": meta(prev) if prev else None,
        "players": players,
    }
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT.name}: {len(players)} players, mode={mode}, cur={cur}, prev={prev}")

    # ---- projection.json: average daily growth of pot & total HC over the last ~3 days ----
    # The HC Estimator reads this so its "Projected final" uses recent momentum instead of a
    # naive event-start-to-now line. Uses the snapshot nearest ~3 days back (or the oldest we
    # have, until 3 days of history exist).
    def total_hc(ts):
        return sum(int(x["hard_cores"]) for x in rows_by_ts.get(ts, []))

    PROJ_WINDOW_DAYS = 3
    EVENT_END = "2026-10-09T18:00:00Z"
    proj = {"asOf": cur, "windowDays": None, "potPerDay": None, "hcPerDay": None,
            "potRef": pot.get(cur), "hcRef": total_hc(cur), "refTs": cur, "eventEnd": EVENT_END}
    target = cur_epoch - PROJ_WINDOW_DAYS * 86400
    past_ts = min(all_ts, key=lambda t: abs(epoch(t) - target))
    days = (cur_epoch - epoch(past_ts)) / 86400.0
    if days >= 0.5:
        proj["windowDays"] = round(days, 2)
        proj["hcPerDay"] = round((total_hc(cur) - total_hc(past_ts)) / days)
        pc, pp = pot.get(cur), pot.get(past_ts)
        if pc is not None and pp is not None:
            proj["potPerDay"] = round((pc - pp) / days, 4)
    with (DATA / "projection.json").open("w", encoding="utf-8") as f:
        json.dump(proj, f, separators=(",", ":"))
    print(f"wrote projection.json: windowDays={proj['windowDays']} potPerDay={proj['potPerDay']} hcPerDay={proj['hcPerDay']}")

if __name__ == "__main__":
    main()
