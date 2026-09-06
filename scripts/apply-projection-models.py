#!/usr/bin/env python3
"""Apply validated next-season models to 2025 features.

Output is a HISTORY-ONLY 2026 PPR/game prior. It is not the final Roster Report
2026 projection: current team, depth-chart role, coaching, availability, rookies,
and team-volume assumptions must be layered on afterward.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

POSITIONS = {"QB", "RB", "WR", "TE"}


def model_predict(row: pd.Series, model: dict) -> float:
    baseline = pd.to_numeric(row.get("ppr_per_game"), errors="coerce")
    if model["selected_model"] == "persistence_baseline":
        return float(baseline) if pd.notna(baseline) else np.nan

    standardized = []
    for feature in model["features"]:
        raw = pd.to_numeric(row.get(feature), errors="coerce")
        if pd.isna(raw):
            raw = model["feature_means"][feature]
        mean = model["feature_means"][feature]
        std = model["feature_stds"][feature] or 1.0
        standardized.append((float(raw) - mean) / std)

    ridge = model["intercept"] + sum(
        model["coefficients_standardized"][feature] * value
        for feature, value in zip(model["features"], standardized)
    )
    if pd.isna(baseline):
        return float(ridge)
    weight = model.get("blend_weight", 1.0)
    return float((1 - weight) * baseline + weight * ridge)


def confidence_from_games(games) -> float:
    # Mirrors the Roster Report partial-season philosophy without turning games
    # played into a talent coefficient. Twelve games reaches full history trust.
    games = pd.to_numeric(games, errors="coerce")
    if pd.isna(games):
        return 0.0
    return float(min(max(games, 0) / 12.0, 1.0))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path,
                        default=Path("data/projections/player_features_2023_2025.csv"))
    parser.add_argument("--models", type=Path,
                        default=Path("data/projections/model_coefficients_v0_3.json"))
    parser.add_argument("--out", type=Path,
                        default=Path("data/projections/history_baseline_2026.csv"))
    args = parser.parse_args()

    players = pd.read_csv(args.features)
    models = json.loads(args.models.read_text())["models"]
    latest = players[players["season"].eq(2025) & players["position"].isin(POSITIONS)].copy()

    latest["history_baseline_ppr_per_game"] = latest.apply(
        lambda row: model_predict(row, models[row["position"]]), axis=1
    )
    latest["history_confidence"] = latest["games"].map(confidence_from_games)
    latest["projection_stage"] = "history_only_baseline"
    latest["projection_season"] = 2026

    keep = [c for c in [
        "player_id", "player_display_name", "player_name", "position", "team",
        "recent_team", "games", "ppr_per_game", "history_baseline_ppr_per_game",
        "history_confidence", "projection_stage", "projection_season",
        "targets_per_game", "target_share", "air_yards_share", "wopr",
        "carries_per_game", "attempts", "passing_epa_per_attempt",
    ] if c in latest.columns]
    output = latest[keep].sort_values(
        ["position", "history_baseline_ppr_per_game"], ascending=[True, False]
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.out, index=False)
    print(f"History-only 2026 baseline rows: {len(output)}")
    for pos in ["QB", "RB", "WR", "TE"]:
        top = output[output["position"].eq(pos)].head(5)
        print(pos, list(zip(top["player_display_name"], top["history_baseline_ppr_per_game"].round(2))))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
