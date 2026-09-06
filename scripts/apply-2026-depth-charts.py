#!/usr/bin/env python3
"""Merge the latest nflverse 2026 depth-chart snapshot into player role context.

Depth charts are used as role evidence, not as a direct target/carry-share model.
They can raise/lower role confidence and explicitly flag non-starting QBs or
unmatched players for review. Historical opportunity remains the point-estimate
prior until a dedicated 2026 role model is calibrated.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

DEPTH_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "depth_charts/depth_charts_2026.csv"
)
TEAM_ALIASES = {"LAR":"LA","STL":"LA","JAC":"JAX","WSH":"WAS","OAK":"LV","SD":"LAC"}


def norm_name(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", text)
    return re.sub(r"[^a-z0-9]", "", text)


def norm_team(value):
    if pd.isna(value): return None
    team = str(value).strip().upper()
    return TEAM_ALIASES.get(team, team)


def latest_depth(source):
    depth = pd.read_csv(source, low_memory=False)
    if "dt" not in depth.columns:
        raise RuntimeError(f"Unexpected depth-chart schema: {list(depth.columns)}")
    depth["dt_parsed"] = pd.to_datetime(depth["dt"], errors="coerce", utc=True)
    newest = depth["dt_parsed"].max()
    if pd.isna(newest):
        raise RuntimeError("Depth chart contains no valid timestamps")
    depth = depth[depth["dt_parsed"].eq(newest)].copy()
    depth["name_key"] = depth["player_name"].map(norm_name)
    depth["team_key_2026"] = depth["team"].map(norm_team)
    depth["pos_rank"] = pd.to_numeric(depth["pos_rank"], errors="coerce")
    # A player can appear in more than one formation slot. Retain the strongest
    # listed rank and preserve all position abbreviations for diagnostics.
    agg = depth.groupby(["name_key","team_key_2026"], dropna=False).agg(
        depth_snapshot=("dt", "first"),
        depth_player_name=("player_name", "first"),
        depth_gsis_id=("gsis_id", "first"),
        depth_pos_group=("pos_grp", "first"),
        depth_pos=("pos_abb", lambda s: "/".join(sorted(set(str(x) for x in s.dropna())))),
        depth_rank=("pos_rank", "min"),
    ).reset_index()
    return agg, newest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--roles", type=Path, default=Path("data/projections/player_role_context_2026.csv"))
    parser.add_argument("--source", default=DEPTH_URL)
    parser.add_argument("--out", type=Path, default=Path("data/projections/player_role_context_2026.csv"))
    args = parser.parse_args()

    roles = pd.read_csv(args.roles)
    depth, newest = latest_depth(args.source)
    if "team_key_2026" not in roles.columns:
        roles["team_key_2026"] = roles["team_2026"].map(norm_team)
    if "name_key" not in roles.columns:
        roles["name_key"] = roles["name"].map(norm_name)

    merged = roles.merge(depth, on=["name_key","team_key_2026"], how="left")
    merged["depth_matched"] = merged["depth_rank"].notna()
    merged["depth_starter"] = merged["depth_rank"].eq(1)
    merged["depth_backup"] = merged["depth_rank"].gt(1)

    # Depth evidence modifies confidence, not historical opportunity shares.
    confidence = pd.to_numeric(merged["role_confidence"], errors="coerce").fillna(0)
    confidence = np.where(merged["depth_starter"], np.maximum(confidence, 0.85), confidence)
    confidence = np.where(merged["depth_backup"], np.minimum(confidence, 0.55), confidence)
    merged["role_confidence"] = np.clip(confidence, 0, 1)

    # QB depth status is sufficiently decisive to gate a season-long starter
    # projection. Non-QBs can rotate, so they are only confidence-adjusted.
    qb = merged["position"].eq("QB")
    merged["qb_depth_starter_confirmed"] = qb & merged["depth_starter"]
    merged["qb_depth_backup_flag"] = qb & merged["depth_backup"]
    merged.loc[merged["qb_depth_backup_flag"], "needs_rookie_or_manual_role"] = True
    merged.loc[merged["qb_depth_backup_flag"], "role_confidence"] = 0.0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.out, index=False)
    print(f"Depth snapshot: {newest}")
    print(f"Depth rows in latest snapshot: {len(depth)}")
    print(f"Fantasy players matched: {int(merged['depth_matched'].sum())}/{len(merged)}")
    print(f"Depth starters: {int(merged['depth_starter'].sum())}")
    print(f"QB starters confirmed: {int(merged['qb_depth_starter_confirmed'].sum())}")
    print(f"QB backups gated: {int(merged['qb_depth_backup_flag'].sum())}")
    print(f"Unmatched fantasy players: {int((~merged['depth_matched']).sum())}")
    print(f"Wrote {args.out}")

if __name__ == "__main__":
    main()
