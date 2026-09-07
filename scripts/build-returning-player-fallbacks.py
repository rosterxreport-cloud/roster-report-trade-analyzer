#!/usr/bin/env python3
"""Recover 2026 projections for returning players without a usable 2025 sample.

The main 2026 context pipeline intentionally requires 2025 history for its normal
veteran pathway. This fallback searches 2024 then 2023 NFL data for current
players who otherwise land in manual_role_required. It produces explicit role and
efficiency overrides with reduced confidence; it never treats a missing season as
zero production.

True rookies/players with no NFL history remain on the college/rookie pathway.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

TEAM_ALIASES = {"LAR":"LA", "STL":"LA", "JAC":"JAX", "WSH":"WAS", "OAK":"LV", "SD":"LAC"}
CONFIDENCE_BY_HISTORY_SEASON = {2024: 0.72, 2023: 0.50}


def norm_name(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", text.lower())
    return re.sub(r"[^a-z0-9]", "", text)


def norm_team(value):
    if pd.isna(value): return None
    team = str(value).strip().upper()
    return TEAM_ALIASES.get(team, team)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--roles", type=Path, default=Path("data/projections/player_role_context_2026.csv"))
    parser.add_argument("--features", type=Path, default=Path("data/projections/player_features_2023_2025.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/projections/returning_player_fallbacks_2026.csv"))
    args = parser.parse_args()

    roles = pd.read_csv(args.roles)
    # Some upstream projection-only transforms rebuild/drop helper keys. Recreate them
    # here from the canonical player name instead of assuming the helper column exists.
    if "name_key" not in roles.columns:
        roles["name_key"] = roles["name"].map(norm_name)

    features = pd.read_csv(args.features)
    features["name_key"] = features["player_display_name"].fillna(features.get("player_name", "")).map(norm_name)
    features["team_key"] = features["team"].map(norm_team)

    unresolved = roles[roles["needs_rookie_or_manual_role"]].copy()
    team_totals = features.groupby(["season", "team_key"], dropna=False).agg(
        team_targets=("targets", "sum"), team_carries=("carries", "sum"), team_attempts=("attempts", "sum")
    ).reset_index()

    rows = []
    for _, current in unresolved.iterrows():
        key = current["name_key"]
        prior = features[(features["name_key"] == key) & (features["season"].isin([2024, 2023]))].sort_values("season", ascending=False)
        if prior.empty:
            continue
        p = prior.iloc[0]
        season = int(p["season"])
        conf = CONFIDENCE_BY_HISTORY_SEASON[season] * min(max(float(p.get("games", 0) or 0) / 12.0, 0), 1)
        source_team = p.get("team_key")
        totals = team_totals[(team_totals["season"] == season) & (team_totals["team_key"] == source_team)]
        totals = totals.iloc[0] if not totals.empty else None

        def share(num, den_name):
            if totals is None: return np.nan
            num_val = pd.to_numeric(p.get(num), errors="coerce")
            den_val = pd.to_numeric(totals.get(den_name), errors="coerce")
            return num_val / den_val if pd.notna(num_val) and pd.notna(den_val) and den_val > 0 else np.nan

        changed = norm_team(current.get("team_2026")) != source_team
        if changed:
            conf *= 0.80

        rows.append({
            "name": current["name"], "name_key": key, "position": current["position"],
            "team_2026": current.get("team_2026"), "history_season": season,
            "history_team": p.get("team"), "history_games": p.get("games"),
            "changed_team_since_history": changed, "fallback_confidence": conf,
            "role_target_share_2026": share("targets", "team_targets") * (0.90 if changed else 1.0),
            "role_carry_share_2026": share("carries", "team_carries") * (0.90 if changed else 1.0),
            "role_qb_attempt_share_2026": share("attempts", "team_attempts") * (0.90 if changed else 1.0),
            "catch_rate": p.get("catch_rate"), "yards_per_target": p.get("yards_per_target"),
            "rec_td_per_target": p.get("rec_td_per_target"), "yards_per_carry": p.get("yards_per_carry"),
            "pass_yards_per_attempt": p.get("pass_yards_per_attempt"), "pass_td_rate": p.get("pass_td_rate"),
            "interception_rate": p.get("interception_rate"), "rush_td_per_attempt": p.get("rush_td_per_attempt"),
            "carries_per_game": p.get("carries_per_game"), "targets_per_game": p.get("targets_per_game"),
            "attempts_per_game": p.get("attempts_per_game"),
            "fallback_path": "prior_nfl_history"
        })

    out = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"Returning-player fallbacks recovered: {len(out)}")
    if len(out):
        print(out[["name","position","history_season","fallback_confidence"]].to_dict("records"))
    print(f"Still requiring rookie/college path: {len(unresolved) - len(out)}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
