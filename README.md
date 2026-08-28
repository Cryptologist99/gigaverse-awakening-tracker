# Gigaverse "The Awakening" Tracker

Snapshots two live, public Gigaverse endpoints on a schedule and keeps a
running history in this repo — no need to keep any window open on your
machine. It runs on GitHub's own servers.

- **Prize pot (USD)** — `GET https://gigaverse.io/api/itempools/public`
- **Leaderboard (Hard Cores)** — `GET https://gigaverse.io/api/leaderboard/id/8?page=N`

Both are unauthenticated public endpoints used by the game client itself —
confirmed by watching the game's own network traffic.

## Setup (5 minutes)

1. Create a new GitHub repo (public or private — Actions works on private
   repos too, with a monthly free-minutes allowance).
2. Upload these files, preserving the folder structure exactly:
   ```
   track_awakening.py
   requirements.txt
   .github/workflows/track.yml
   ```
3. Go to the repo's **Settings → Actions → General → Workflow permissions**,
   and set it to **"Read and write permissions"**. This is required so the
   workflow can commit new snapshot data back into the repo.
4. Done. The workflow now runs automatically on the schedule in `track.yml`
   (twice a day: 1:59 PM and 1:59 AM US Eastern, DST-adjusted). You can also
   trigger a run any time from the **Actions** tab → "Track Gigaverse
   Awakening" → **Run workflow**.

Every run appends new rows to:
- `data/pot_history.csv` — one row per run: timestamp, prize pot in USD
- `data/leaderboard_history.csv` — one row per (run × player): timestamp,
  rank, wallet, username, hard cores

Both files just keep growing, so over time you build a full time series.

## Adjusting the schedule

Edit the `cron` lines in `.github/workflows/track.yml`. Cron is in UTC and
does **not** follow daylight saving.

The default runs **twice a day at 1:59 PM and 1:59 AM US Eastern**, year-round.
Because GitHub cron is UTC-only, this is done by scheduling the UTC times for
both EDT and EST offsets, and a small `gate` job only lets the run proceed when
it's actually the intended hour in `America/New_York` (off-schedule DST
duplicates are skipped). If you don't care about DST precision, you can replace
all four cron lines with a single UTC line and delete the `gate` job.

| Cadence | Cron |
|---|---|
| Every 15 min | `*/15 * * * *` |
| Every hour | `5 * * * *` |
| Every 6 hours | `0 */6 * * *` |
| Once a day at 09:00 UTC | `0 9 * * *` |

GitHub Actions doesn't guarantee cron fires at the exact minute during
platform load — expect it within a few minutes of the scheduled time.

## Loading the data (Python + pandas example)

```python
import pandas as pd

pot = pd.read_csv("data/pot_history.csv", parse_dates=["timestamp_utc"])
pot.plot(x="timestamp_utc", y="prizepot_usd")

lb = pd.read_csv("data/leaderboard_history.csv", parse_dates=["timestamp_utc"])
# rank history for one player over time:
lb[lb["username"] == "cryptologist"].plot(x="timestamp_utc", y="rank")
```

## Notes

- `LEADERBOARD_ID = 8` in `track_awakening.py` is specific to *The
  Awakening*. If Gigaverse launches a new event with a new leaderboard,
  update that constant.
- The script stops paginating once it hits a short/empty page, with a
  safety cap of 60 pages so an API hiccup on Gigaverse's end can't loop
  forever.
- The default hourly cadence is plenty for tracking trends without
  hammering their API. There's also a small delay between leaderboard
  page requests.
