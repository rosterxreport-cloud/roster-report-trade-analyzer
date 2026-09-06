#!/usr/bin/env python3
"""Build raw 2023-2025 projection features from nflverse.

Requires:
    pip install nflreadpy polars

This script is intentionally source-first: it preserves raw/counting stats and
stable rates in a season-level feature table. Projection assumptions (2026 role,
team context, regression, injuries) belong downstream in projection-engine.js.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import nflreadpy as nfl
import polars as pl

SEASONS = [2023, 2024, 2025]
SKILL_POSITIONS = ["QB", "RB", "WR", "TE"]

# Fields used by the first projection model. select_existing() makes the
# pipeline resilient when nflverse adds/removes unrelated columns.
PLAYER_FIELDS = [
    "player_id", "player_display_name", "player_name", "position", "team",
    "season", "games", "completions", "attempts", "passing_yards",
    "passing_tds", "interceptions", "sacks_suffered", "passing_epa",
    "carries", "rushing_yards", "rushing_tds", "rushing_epa",
    "rushing_first_downs", "targets", "receptions", "receiving_yards",
    "receiving_tds", "receiving_air_yards", "receiving_yards_after_catch",
    "receiving_first_downs", "receiving_epa", "target_share",
    "air_yards_share", "wopr", "racr", "fantasy_points", "fantasy_points_ppr",
]

TEAM_FIELDS = [
    "team", "season", "games", "attempts", "passing_yards", "passing_tds",
    "interceptions", "carries", "rushing_yards", "rushing_tds",
]


def select_existing(df: pl.DataFrame, names: list[str]) -> pl.DataFrame:
    existing = [name for name in names if name in df.columns]
    return df.select(existing)


def safe_div(num: str, den: str, alias: str) -> pl.Expr:
    return (
        pl.when(pl.col(den).fill_null(0) > 0)
        .then(pl.col(num).fill_null(0) / pl.col(den))
        .otherwise(None)
        .alias(alias)
    )


def add_player_rates(df: pl.DataFrame) -> pl.DataFrame:
    expressions = []
    cols = set(df.columns)

    def add(num, den, alias):
        if num in cols and den in cols:
            expressions.append(safe_div(num, den, alias))

    add("completions", "attempts", "completion_rate")
    add("passing_yards", "attempts", "pass_yards_per_attempt")
    add("passing_tds", "attempts", "pass_td_rate")
    add("interceptions", "attempts", "interception_rate")
    add("carries", "games", "carries_per_game")
    add("rushing_yards", "carries", "yards_per_carry")
    add("rushing_tds", "carries", "rush_td_per_attempt")
    add("targets", "games", "targets_per_game")
    add("receptions", "targets", "catch_rate")
    add("receiving_yards", "targets", "yards_per_target")
    add("receiving_tds", "targets", "rec_td_per_target")
    add("receiving_air_yards", "targets", "air_yards_per_target")
    add("receiving_yards_after_catch", "receptions", "yac_per_reception")
    add("receiving_first_downs", "targets", "receiving_first_down_rate")
    add("rushing_first_downs", "carries", "rushing_first_down_rate")

    return df.with_columns(expressions) if expressions else df


def build_player_features() -> pl.DataFrame:
    # Regular-season summary avoids double-counting weekly rows and gives us a
    # stable player-season grain for historical weighting/backtests.
    df = nfl.load_player_stats(SEASONS, summary_level="reg")
    df = select_existing(df, PLAYER_FIELDS)

    if "position" in df.columns:
        df = df.filter(pl.col("position").is_in(SKILL_POSITIONS))

    if "player_display_name" not in df.columns and "player_name" in df.columns:
        df = df.with_columns(pl.col("player_name").alias("player_display_name"))

    return add_player_rates(df).sort(["season", "position", "player_display_name"])


def build_team_features() -> pl.DataFrame:
    df = nfl.load_team_stats(SEASONS, summary_level="reg")
    df = select_existing(df, TEAM_FIELDS)
    cols = set(df.columns)
    exprs = []

    if {"passing_yards", "attempts"}.issubset(cols):
        exprs.append(safe_div("passing_yards", "attempts", "pass_yards_per_attempt"))
    if {"passing_tds", "attempts"}.issubset(cols):
        exprs.append(safe_div("passing_tds", "attempts", "pass_td_rate"))
    if {"interceptions", "attempts"}.issubset(cols):
        exprs.append(safe_div("interceptions", "attempts", "interception_rate"))
    if {"rushing_yards", "carries"}.issubset(cols):
        exprs.append(safe_div("rushing_yards", "carries", "rush_yards_per_carry"))
    if {"rushing_tds", "carries"}.issubset(cols):
        exprs.append(safe_div("rushing_tds", "carries", "rush_td_rate"))
    if {"attempts", "carries"}.issubset(cols):
        exprs.extend([
            (pl.col("attempts").fill_null(0) + pl.col("carries").fill_null(0)).alias("offensive_opportunities"),
            (
                pl.col("attempts").fill_null(0)
                / (pl.col("attempts").fill_null(0) + pl.col("carries").fill_null(0))
            ).alias("pass_rate_proxy"),
        ])

    if exprs:
        df = df.with_columns(exprs)
    return df.sort(["season", "team"])


def build_current_roster() -> pl.DataFrame:
    # Current-season roster identity map. Projection roles remain a separate,
    # explicitly editable assumption layer.
    df = nfl.load_rosters(2026)
    keep = [
        "gsis_id", "full_name", "first_name", "last_name", "position",
        "team", "status", "depth_chart_position", "depth_chart_order",
        "years_exp", "rookie_year", "birth_date",
    ]
    df = select_existing(df, keep)
    if "position" in df.columns:
        df = df.filter(pl.col("position").is_in(SKILL_POSITIONS))
    return df.sort(["team", "position", "full_name"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("data/projections"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    players = build_player_features()
    teams = build_team_features()
    rosters = build_current_roster()

    players.write_parquet(args.out_dir / "player_features_2023_2025.parquet")
    players.write_csv(args.out_dir / "player_features_2023_2025.csv")
    teams.write_csv(args.out_dir / "team_features_2023_2025.csv")
    rosters.write_csv(args.out_dir / "rosters_2026.csv")

    print(f"Player-season rows: {players.height}")
    print(f"Team-season rows: {teams.height}")
    print(f"2026 roster rows: {rosters.height}")
    print(f"Wrote projection source data to {args.out_dir}")


if __name__ == "__main__":
    main()
