#!/usr/bin/env python3
"""Build auditable 2026 team-environment and player-role context.

This layer sits between the history-only player model and final stat projections.
It deliberately separates:
  1) player talent/history priors,
  2) projected 2026 team volume/efficiency,
  3) projected player opportunity/role.

Current team assignments come from players.json. Historical football inputs come
from data/projections/player_features_2023_2025.csv and team_features_2023_2025.csv.
Rookies and players without 2025 NFL history are emitted with explicit missing-
history flags so they can flow through the dedicated rookie/manual-role pathway.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

SEASON_WEIGHTS = {2023: 0.20, 2024: 0.30, 2025: 0.50}
TEAM_REGRESSION = 0.30
TEAM_GAMES = 17.0
POSITIONS = {"QB", "RB", "WR", "TE"}


def norm_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", text.lower())
    return re.sub(r"[^a-z0-9]", "", text)


def weighted(values: dict[int, float]) -> float | None:
    pairs = [(float(v), SEASON_WEIGHTS[s]) for s, v in values.items() if s in SEASON_WEIGHTS and pd.notna(v)]
    if not pairs:
        return None
    den = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / den


def league_regress(value: float | None, league_mean: float, amount: float = TEAM_REGRESSION) -> float:
    if value is None or not np.isfinite(value):
        return float(league_mean)
    return float((1 - amount) * value + amount * league_mean)


def load_current_players(path: Path) -> pd.DataFrame:
    raw = json.loads(path.read_text())
    # Half-PPR list is the canonical player universe; names/teams/positions are
    # shared across scoring formats.
    rows = []
    for p in raw.get("half", []):
        if p.get("pos") not in POSITIONS:
            continue
        rows.append({
            "name": p.get("name"), "team_2026": p.get("team"), "position": p.get("pos"),
            "rookie": bool(p.get("rookie", False)), "trade_value": p.get("value"),
            "aw_rank": p.get("awRank"), "analytics_score": p.get("analyticsScore")
        })
    df = pd.DataFrame(rows)
    df["name_key"] = df["name"].map(norm_name)
    return df.drop_duplicates(["name_key", "position"], keep="first")


def build_team_context(team_hist: pd.DataFrame) -> pd.DataFrame:
    hist = team_hist.copy()
    # Normalize to per-game team volume before combining seasons.
    for c in ["attempts", "carries", "passing_yards", "passing_tds", "interceptions", "rushing_yards", "rushing_tds"]:
        if c in hist.columns:
            hist[f"{c}_per_game"] = pd.to_numeric(hist[c], errors="coerce") / TEAM_GAMES

    metrics = [c for c in [
        "attempts_per_game", "carries_per_game", "pass_yards_per_attempt",
        "pass_td_rate", "interception_rate", "rush_yards_per_carry", "rush_td_rate",
        "pass_rate_proxy", "offensive_opportunities"
    ] if c in hist.columns]

    # Use the 2025 league mean as the regression target when available.
    latest = hist[hist["season"].eq(2025)]
    league = {m: float(pd.to_numeric(latest[m], errors="coerce").mean()) for m in metrics}

    rows = []
    for team, group in hist.groupby("team"):
        row = {"team": team, "projection_season": 2026}
        for metric in metrics:
            values = {
                int(r.season): pd.to_numeric(getattr(r, metric), errors="coerce")
                for r in group[["season", metric]].itertuples(index=False)
            }
            raw = weighted(values)
            row[f"history_{metric}"] = raw
            row[f"projected_{metric}"] = league_regress(raw, league[metric])
        rows.append(row)
    out = pd.DataFrame(rows)

    # Add explicit 17-game totals for downstream reconciliation.
    if "projected_attempts_per_game" in out:
        out["projected_pass_attempts"] = out["projected_attempts_per_game"] * TEAM_GAMES
    if "projected_carries_per_game" in out:
        out["projected_rush_attempts"] = out["projected_carries_per_game"] * TEAM_GAMES
    return out.sort_values("team")


def build_player_context(current: pd.DataFrame, player_hist: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    hist = player_hist.copy()
    hist["name_key"] = hist["player_display_name"].fillna(hist.get("player_name", "")).map(norm_name)
    latest = hist[hist["season"].eq(2025)].copy()

    team_cols = ["team", "projected_pass_attempts", "projected_rush_attempts",
                 "projected_pass_yards_per_attempt", "projected_pass_td_rate",
                 "projected_rush_yards_per_carry", "projected_rush_td_rate"]
    team_lookup = teams[[c for c in team_cols if c in teams.columns]].rename(columns={"team": "team_2026"})

    merged = current.merge(latest, on=["name_key", "position"], how="left", suffixes=("", "_2025"))
    merged = merged.merge(team_lookup, on="team_2026", how="left")

    merged["team_2025"] = merged.get("team", merged.get("recent_team"))
    merged["changed_team"] = merged["team_2025"].notna() & merged["team_2026"].notna() & merged["team_2025"].ne(merged["team_2026"])
    merged["has_2025_history"] = merged["season"].eq(2025)
    merged["needs_rookie_or_manual_role"] = merged["rookie"] | ~merged["has_2025_history"]

    # Historical opportunity shares. These are priors, not hard 2026 assumptions.
    team_hist_2025 = player_hist[player_hist["season"].eq(2025)].groupby("team", dropna=False).agg(
        team_targets=("targets", "sum"),
        team_carries=("carries", "sum"),
        team_attempts=("attempts", "sum")
    ).reset_index().rename(columns={"team": "team_2025"})
    merged = merged.merge(team_hist_2025, on="team_2025", how="left")

    for num, den, name in [
        ("targets", "team_targets", "historical_target_share_team"),
        ("carries", "team_carries", "historical_carry_share_team"),
        ("attempts", "team_attempts", "historical_qb_attempt_share_team")
    ]:
        if num in merged.columns and den in merged.columns:
            denom = pd.to_numeric(merged[den], errors="coerce").replace(0, np.nan)
            merged[name] = pd.to_numeric(merged[num], errors="coerce") / denom

    # Default 2026 role priors retain prior shares, with a small uncertainty haircut
    # on team changers. These columns are intended to be overridden by explicit
    # depth-chart/news inputs later.
    haircut = np.where(merged["changed_team"], 0.92, 1.0)
    for src, dst in [
        ("historical_target_share_team", "role_target_share_2026"),
        ("historical_carry_share_team", "role_carry_share_2026"),
        ("historical_qb_attempt_share_team", "role_qb_attempt_share_2026")
    ]:
        if src in merged.columns:
            merged[dst] = merged[src] * haircut

    # Role confidence is separate from the point estimate.
    games = pd.to_numeric(merged.get("games"), errors="coerce")
    merged["history_confidence"] = (games / 12.0).clip(lower=0, upper=1).fillna(0)
    merged["role_confidence"] = merged["history_confidence"]
    merged.loc[merged["changed_team"], "role_confidence"] *= 0.80
    merged.loc[merged["needs_rookie_or_manual_role"], "role_confidence"] = 0.0

    keep = [c for c in [
        "name", "name_key", "position", "team_2026", "team_2025", "rookie",
        "changed_team", "has_2025_history", "needs_rookie_or_manual_role",
        "games", "ppr_per_game", "targets_per_game", "carries_per_game",
        "attempts_per_game", "target_share", "air_yards_share", "wopr",
        "historical_target_share_team", "historical_carry_share_team",
        "historical_qb_attempt_share_team", "role_target_share_2026",
        "role_carry_share_2026", "role_qb_attempt_share_2026",
        "projected_pass_attempts", "projected_rush_attempts",
        "projected_pass_yards_per_attempt", "projected_pass_td_rate",
        "projected_rush_yards_per_carry", "projected_rush_td_rate",
        "history_confidence", "role_confidence", "trade_value", "aw_rank", "analytics_score"
    ] if c in merged.columns]
    return merged[keep].sort_values(["position", "trade_value"], ascending=[True, False])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--player-features", type=Path, default=Path("data/projections/player_features_2023_2025.csv"))
    parser.add_argument("--team-features", type=Path, default=Path("data/projections/team_features_2023_2025.csv"))
    parser.add_argument("--players", type=Path, default=Path("players.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/projections"))
    args = parser.parse_args()

    player_hist = pd.read_csv(args.player_features)
    team_hist = pd.read_csv(args.team_features)
    current = load_current_players(args.players)

    teams = build_team_context(team_hist)
    players = build_player_context(current, player_hist, teams)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    teams.to_csv(args.out_dir / "team_context_2026.csv", index=False)
    players.to_csv(args.out_dir / "player_role_context_2026.csv", index=False)

    print(f"2026 teams: {len(teams)}")
    print(f"Current fantasy players: {len(players)}")
    print(f"Matched 2025 history: {int(players['has_2025_history'].sum())}")
    print(f"Team changers: {int(players['changed_team'].sum())}")
    print(f"Rookie/manual-role pathway: {int(players['needs_rookie_or_manual_role'].sum())}")
    print("Wrote team_context_2026.csv and player_role_context_2026.csv")


if __name__ == "__main__":
    main()
