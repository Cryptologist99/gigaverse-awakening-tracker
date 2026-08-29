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

The default runs **twice a day at 1:59 AM and 1:59 PM US Eastern** via fixed UTC
crons (`59 5` and `59 17`). The Awakening event runs entirely within US Daylight
Time (EDT), so those UTC times land exactly on 1:59 Eastern for the whole event.
There is deliberately **no DST gate**: GitHub often delays scheduled runs (by
minutes, sometimes hours), and a gate that checked the wall-clock hour at run
time would skip a delayed run entirely. Running unconditionally means a late run
still records its snapshot. (If you extend this past the Nov 2 DST change and
want to hold 1:59 Eastern exactly, shift the PM/AM crons to `59 18` / `59 6`.)

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

## Web app: payout calculator (`index.html`)

`index.html` is a self-contained calculator that estimates what a holder's Hard
Cores are worth as a share of the prize pot. Enter a **minimum box cost**, **your
HC**, the **prize pot**, and a **projected total HC**; it computes value per box,
your payout, your share, and — from the *real* leaderboard distribution — how many
boxes exist and how much HC is wasted (whole-boxes-only model, remainder wasted).

**Data, three tiers (auto):**
1. **Live** — on load it fetches the Gigaverse API directly (pot + all leaderboard
   pages) and shows a live badge plus the event countdown. CORS is open, so this
   works from any static host.
2. **Repo snapshot** — if the live API is unreachable, it falls back to the
   accumulating CSVs in `data/` (same-origin), using the most recent snapshot.
3. **Built-in snapshot** — a copy baked into the page so it always renders even
   offline.

**Host it on GitHub Pages:** Settings → Pages → Source = *Deploy from a branch*,
Branch = `main` / `/ (root)`. The page is then served at
`https://<user>.github.io/gigaverse-awakening-tracker/`. A `.nojekyll` file is
included so Pages serves the folder as-is. Note: a Pages site is **public**, and
it serves everything in the repo (including `data/`), even when the repo is
private — enable it only if you're fine with that.

## Analysis: HC value model

`analysis/hc_value_model.py` estimates what each Hard Core (HC) is worth as a
share of the prize pot, assuming HC convert into fixed-cost boxes that pay out
cash and the pot is split in proportion to boxes opened. It reads the latest
snapshot from `data/` (or any past one via `--timestamp`).

```bash
python analysis/hc_value_model.py                     # latest snapshot, Model B, 500 HC box
python analysis/hc_value_model.py --box-cost 1000     # different box cost
python analysis/hc_value_model.py --model A           # proportional (every eligible HC counts)
python analysis/hc_value_model.py --sweep 250 500 1000 2500   # box-cost sensitivity table
python analysis/hc_value_model.py --examples 500 10000 100000 # payouts for specific HC amounts
```

- **Model B (default)** — whole boxes only: `spent = floor(HC / box_cost) * box_cost`;
  HC below the next whole box is wasted. Value per HC = `pot / sum(spent)`.
- **Model A** — proportional: every eligible HC counts. Value per HC = `pot / sum(eligible HC)`.
- Players below one box cost are gated out. Lower box cost → more players and HC
  included → the pot is split over more HC → lower value per HC.

Results are a point-in-time estimate; the pot and HC pool both move as the event
runs, so re-run against newer snapshots (or `--timestamp`) to see the trend.

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
