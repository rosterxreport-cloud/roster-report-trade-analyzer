#!/usr/bin/env python3
"""Build raw 2023-2025 projection features from nflverse.

Primary source:
  https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv.gz

The script uses pandas only. This avoids requiring nflreadpy/polars and makes the
projection data build portable across local machines, GitHub Actions, and hosted
notebooks. Projection assumptions (2026 role, team context, regression, injuries)
belong downstream in projection-engine.js.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

SEASONS = [2023, 2024, 2025]
SKILL_POSITIONS = ["QB", "RB", "WR", "TE"]
PLAYER_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "player_stats/player_stats.csv.gz"
)

PLAYER_FIELDS = [
    "player_id", "player_display_name", "player_name", "position",
    "position_group", "recent_team", "team", "season", "season_type",
    "games", "completions", "attempts", "passing_yards",
    "passing_yards_after_catch", "passing_tds", "interceptions",
    "sacks_suffered", "sack_yards", "passing_epa", "dakota",
    "carries", "rushing_yards", "rushing_tds", "rushing_epa",
    "rushing_first_downs", "rushing_fumbles_lost", "targets", "receptions",
    "receiving_yards", "receiving_tds", "receiving_air_yards",
    "receiving_yards_after_catch", "receiving_first_downs", "receiving_epa",
    "receiving_fumbles_lost", "target_share", "air_yards_share", "wopr",
    "racr", "fantasy_points", "fantasy_points_ppr",
]


def select_existing(df: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    return df[[name for name in names if name in df.columns]].copy()


def safe_div(df: pd.DataFrame, num: str, den: str, alias: str) -> None:
    if num not in df.columns or den not in df.columns:
        return
    denom = pd.to_numeric(df[den], errors="coerce")
    numer = pd.to_numeric(df[num], errors="coerce")
    df[alias] = numer.div(denom.where(denom > 0))


def add_player_rates(df: pd.DataFrame) -> pd.DataFrame:
    pairs = [
        ("completions", "attempts", "completion_rate"),
        ("passing_yards", "attempts", "pass_yards_per_attempt"),
        ("passing_yards_after_catch", "passing_yards", "pass_yac_share"),
        ("passing_tds", "attempts", "pass_td_rate"),
        ("interceptions", "attempts", "interception_rate"),
        ("sacks_suffered", "attempts", "sacks_per_attempt"),
        ("carries", "games", "carries_per_game"),
        ("rushing_yards", "carries", "yards_per_carry"),
        ("rushing_tds", "carries", "rush_td_per_attempt"),
        ("rushing_first_downs", "carries", "rushing_first_down_rate"),
        ("targets", "games", "targets_per_game"),
        ("receptions", "targets", "catch_rate"),
        ("receiving_yards", "targets", "yards_per_target"),
        ("receiving_tds", "targets", "rec_td_per_target"),
        ("receiving_air_yards", "targets", "air_yards_per_target"),
        ("receiving_yards_after_catch", "receptions", "yac_per_reception"),
        ("receiving_first_downs", "targets", "receiving_first_down_rate"),
    ]
    for num, den, alias in pairs:
        safe_div(df, num, den, alias)
    if "fantasy_points_ppr" in df.columns and "games" in df.columns:
        safe_div(df, "fantasy_points_ppr", "games", "ppr_per_game")
    if "passing_epa" in df.columns and "attempts" in df.columns:
        safe_div(df, "passing_epa", "attempts", "passing_epa_per_attempt")
    if "rushing_epa" in df.columns and "carries" in df.columns:
        safe_div(df, "rushing_epa", "carries", "rushing_epa_per_attempt")
    if "receiving_epa" in df.columns and "targets" in df.columns:
        safe_div(df, "receiving_epa", "targets", "receiving_epa_per_target")
    return df


def load_player_stats(source: str) -> pd.DataFrame:
    df = pd.read_csv(source, compression="infer", low_memory=False)
    if "season_type" in df.columns:
        df = df[df["season_type"].eq("REG")]
    if "season" in df.columns:
        df = df[df["season"].isin(SEASONS)]
    position_col = "position" if "position" in df.columns else "position_group"
    if position_col in df.columns:
        df = df[df[position_col].isin(SKILL_POSITIONS)]
        if "position" not in df.columns:
            df["position"] = df[position_col]
    if "player_display_name" not in df.columns and "player_name" in df.columns:
        df["player_display_name"] = df["player_name"]
    if "team" not in df.columns and "recent_team" in df.columns:
        df["team"] = df["recent_team"]
    return add_player_rates(select_existing(df, PLAYER_FIELDS + [
        "completion_rate", "pass_yards_per_attempt", "pass_yac_share",
        "pass_td_rate", "interception_rate", "sacks_per_attempt",
        "carries_per_game", "yards_per_carry", "rush_td_per_attempt",
        "rushing_first_down_rate", "targets_per_game", "catch_rate",
        "yards_per_target", "rec_td_per_target", "air_yards_per_target",
        "yac_per_reception", "receiving_first_down_rate", "ppr_per_game",
        "passing_epa_per_attempt", "rushing_epa_per_attempt",
        "receiving_epa_per_target",
    ]))


def build_team_features(players: pd.DataFrame) -> pd.DataFrame:
    # Aggregate team environment directly from the same player-stat release so
    # the player and team layers always reconcile to the same source snapshot.
    df = players.copy()
    numeric = [
        c for c in ["attempts", "passing_yards", "passing_tds", "interceptions",
                    "carries", "rushing_yards", "rushing_tds", "targets"]
        if c in df.columns
    ]
    team = df.groupby(["season", "team"], dropna=False)[numeric].sum(min_count=1).reset_index()
    safe_div(team, "passing_yards", "attempts", "pass_yards_per_attempt")
    safe_div(team, "passing_tds", "attempts", "pass_td_rate")
    safe_div(team, "interceptions", "attempts", "interception_rate")
    safe_div(team, "rushing_yards", "carries", "rush_yards_per_carry")
    safe_div(team, "rushing_tds", "carries", "rush_td_rate")
    if "attempts" in team.columns and "carries" in team.columns:
        team["offensive_opportunities"] = team["attempts"].fillna(0) + team["carries"].fillna(0)
        denom = team["offensive_opportunities"].where(team["offensive_opportunities"] > 0)
        team["pass_rate_proxy"] = team["attempts"].fillna(0) / denom
    return team.sort_values(["season", "team"])


def build_position_training_tables(players: pd.DataFrame, out_dir: Path) -> None:
    # These tables deliberately preserve inputs and next-year outcomes side by
    # side. The training target is next-season production, preventing us from
    # merely fitting same-season fantasy points.
    key = "player_id"
    for pos in SKILL_POSITIONS:
        cur = players[players["position"].eq(pos)].copy()
        nxt = cur[[c for c in [key, "season", "games", "fantasy_points_ppr"] if c in cur.columns]].copy()
        nxt["season"] = nxt["season"] - 1
        rename = {"games": "next_games", "fantasy_points_ppr": "next_fantasy_points_ppr"}
        nxt = nxt.rename(columns=rename)
        train = cur.merge(nxt, on=[key, "season"], how="left")
        if "next_fantasy_points_ppr" in train.columns:
            train["next_ppr_per_game"] = train["next_fantasy_points_ppr"] / train["next_games"].where(train["next_games"] > 0)
        train.to_csv(out_dir / f"training_{pos.lower()}_next_season.csv", index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=PLAYER_STATS_URL,
                        help="nflverse player_stats csv.gz URL or local file")
    parser.add_argument("--out-dir", type=Path, default=Path("data/projections"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    players = load_player_stats(args.source)
    teams = build_team_features(players)

    players = players.sort_values(["season", "position", "player_display_name"])
    players.to_csv(args.out_dir / "player_features_2023_2025.csv", index=False)
    teams.to_csv(args.out_dir / "team_features_2023_2025.csv", index=False)
    build_position_training_tables(players, args.out_dir)

    print(f"Player-season rows: {len(players)}")
    print(f"Team-season rows: {len(teams)}")
    print("Training tables: QB, RB, WR, TE")
    print(f"Wrote projection source data to {args.out_dir}")


if __name__ == "__main__":
    main()
