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

    prev_map = wmap(prev) if prev else {}
    players = []
    for r in sorted(rows_by_ts[cur], key=lambda r: int(r["rank"])):
        w = (r["wallet"] or "").lower()
        p = prev_map.get(w)
        amt, rank = int(r["hard_cores"]), int(r["rank"])
        players.append({
            "rank": rank,
            "name": r["username"] or "",
            "hc": amt,
            "hcDelta": (amt - p["amount"]) if p else None,
            "rankDelta": (p["rank"] - rank) if p else None,
            "isNew": p is None,
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

if __name__ == "__main__":
    main()
