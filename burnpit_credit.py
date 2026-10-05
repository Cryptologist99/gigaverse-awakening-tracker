"""
One-time Burn Pit payout. The Burn Pit closed 2026-10-05T18:00Z and its 46.2M HC
(154 items x 300k) landed in player accounts afterwards — the 17:59 UTC snapshot is
pre-credit, and a live pull at 19:49 UTC already included it. Any gain measured across
that instant is mostly the payout, not organic growth, so rate/average builders skip
snapshot pairs that span it.

CREDIT_AT only has to fall between the last pre-credit snapshot (17:59) and the first
post-credit one (the Pi snapshots twice daily, next at 05:59 UTC).
"""
BURN_PIT_CREDIT_AT = "2026-10-05T18:30:00Z"
BURN_PIT_CREDIT_HC = 46_200_000


def spans_credit(ts_a, ts_b):
    """True if the pair (ts_a earlier, ts_b later) straddles the credit. Timestamps are
    the CSV's fixed-width 'YYYY-MM-DDTHH:MM:SSZ', so string comparison is chronological."""
    return ts_a < BURN_PIT_CREDIT_AT <= ts_b
