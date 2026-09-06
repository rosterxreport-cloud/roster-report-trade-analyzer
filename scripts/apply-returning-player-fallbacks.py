#!/usr/bin/env python3
"""Apply validated prior-NFL-history fallbacks to 2026 role context.

Consumes returning_player_fallbacks_2026.csv produced by
build-returning-player-fallbacks.py. A player is rescued from the manual pathway
only when prior NFL history exists and current depth-chart evidence does not flag
a backup QB. True rookies/no-NFL-history players remain manual.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

ROLE_FIELDS = [
    "role_target_share_2026", "role_carry_share_2026", "role_qb_attempt_share_2026"
]
EFF_FIELDS = [
    "catch_rate", "yards_per_target", "rec_td_per_target", "yards_per_carry",
    "pass_yards_per_attempt", "pass_td_rate", "interception_rate",
    "rush_td_per_attempt", "carries_per_game", "targets_per_game", "attempts_per_game"
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--roles", type=Path, default=Path("data/projections/player_role_context_2026.csv"))
    parser.add_argument("--fallbacks", type=Path, default=Path("data/projections/returning_player_fallbacks_2026.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/projections/player_role_context_2026.csv"))
    args = parser.parse_args()

    roles = pd.read_csv(args.roles)
    fb = pd.read_csv(args.fallbacks)
    if fb.empty:
        roles["fallback_history_used"] = False
        roles.to_csv(args.out, index=False)
        print("Returning-player fallbacks applied: 0")
        return

    keep = ["name_key", "position", "history_season", "fallback_confidence", "fallback_path"] + ROLE_FIELDS + EFF_FIELDS
    fb = fb[[c for c in keep if c in fb.columns]].copy()
    rename = {c: f"fallback_{c}" for c in ROLE_FIELDS + EFF_FIELDS if c in fb.columns}
    fb = fb.rename(columns=rename)
    merged = roles.merge(fb, on=["name_key", "position"], how="left")
    eligible = merged["history_season"].notna()
    if "qb_depth_backup_flag" in merged.columns:
        eligible &= ~merged["qb_depth_backup_flag"].fillna(False)

    merged["fallback_history_used"] = eligible
    merged.loc[eligible, "needs_rookie_or_manual_role"] = False
    merged.loc[eligible, "role_confidence"] = merged.loc[eligible, "fallback_confidence"].clip(0, 1)
    merged.loc[eligible, "has_prior_nfl_history_fallback"] = True
    merged.loc[eligible, "history_source_season"] = merged.loc[eligible, "history_season"]

    # Keep fallback data explicitly prefixed so normal 2025 feature columns are
    # never shadowed. The stat builder coalesces these only for rescued players.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.out, index=False)

    used = merged[merged["fallback_history_used"]]
    print(f"Returning-player fallbacks applied: {len(used)}")
    if len(used):
        print(used[["name","position","history_source_season","role_confidence"]].to_dict("records"))
    print(f"Remaining manual pathway: {int(merged['needs_rookie_or_manual_role'].sum())}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
