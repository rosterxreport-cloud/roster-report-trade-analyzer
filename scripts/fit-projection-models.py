#!/usr/bin/env python3
"""Fit auditable next-season Roster Report projection models.

Each position is challenged against a simple persistence baseline: last season's
PPR points per game. Candidate ridge models may use the full feature set or a
smaller opportunity/role feature set, and may be conservatively blended with the
baseline. A challenger is promoted only when its holdout RMSE beats persistence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ALPHAS = [0.1, 1.0, 10.0, 50.0, 100.0, 300.0]
BLEND_WEIGHTS = [0.25, 0.50, 0.75, 1.00]

FEATURES = {
    "QB": [
        "games", "attempts", "completion_rate", "pass_yards_per_attempt",
        "pass_yac_share", "pass_td_rate", "interception_rate",
        "sacks_per_attempt", "passing_epa_per_attempt", "carries_per_game",
        "yards_per_carry", "rush_td_per_attempt", "rushing_epa_per_attempt",
        "ppr_per_game",
    ],
    "RB": [
        "games", "carries_per_game", "yards_per_carry", "rush_td_per_attempt",
        "rushing_first_down_rate", "rushing_epa_per_attempt", "targets_per_game",
        "target_share", "catch_rate", "yards_per_target", "rec_td_per_target",
        "receiving_first_down_rate", "receiving_epa_per_target", "ppr_per_game",
    ],
    "WR": [
        "games", "targets_per_game", "target_share", "air_yards_share", "wopr",
        "catch_rate", "yards_per_target", "air_yards_per_target",
        "yac_per_reception", "rec_td_per_target", "receiving_first_down_rate",
        "receiving_epa_per_target", "ppr_per_game",
    ],
    "TE": [
        "games", "targets_per_game", "target_share", "air_yards_share", "wopr",
        "catch_rate", "yards_per_target", "air_yards_per_target",
        "yac_per_reception", "rec_td_per_target", "receiving_first_down_rate",
        "receiving_epa_per_target", "ppr_per_game",
    ],
}

OPPORTUNITY_FEATURES = {
    "QB": ["games", "attempts", "passing_epa_per_attempt", "carries_per_game",
           "rush_td_per_attempt", "ppr_per_game"],
    "RB": ["games", "carries_per_game", "targets_per_game", "target_share",
           "rush_td_per_attempt", "ppr_per_game"],
    "WR": ["games", "targets_per_game", "target_share", "air_yards_share",
           "wopr", "ppr_per_game"],
    "TE": ["games", "targets_per_game", "target_share", "air_yards_share",
           "wopr", "ppr_per_game"],
}


def standardize_fit(df: pd.DataFrame, features: list[str]):
    x = df[features].apply(pd.to_numeric, errors="coerce")
    means = x.mean()
    stds = x.std(ddof=0).replace(0, 1).fillna(1)
    x = x.fillna(means).fillna(0)
    return (x - means) / stds, means, stds


def standardize_apply(df: pd.DataFrame, features, means, stds):
    x = df[features].apply(pd.to_numeric, errors="coerce")
    x = x.fillna(means).fillna(0)
    return (x - means) / stds


def ridge_fit(x: np.ndarray, y: np.ndarray, alpha: float):
    x1 = np.column_stack([np.ones(len(x)), x])
    penalty = np.eye(x1.shape[1]) * alpha
    penalty[0, 0] = 0
    return np.linalg.pinv(x1.T @ x1 + penalty) @ x1.T @ y


def ridge_predict(x: np.ndarray, beta: np.ndarray):
    return np.column_stack([np.ones(len(x)), x]) @ beta


def metrics(y, p):
    err = p - y
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    corr = float(np.corrcoef(y, p)[0, 1]) if len(y) > 1 and np.std(y) > 0 and np.std(p) > 0 else None
    return {"n": int(len(y)), "mae": mae, "rmse": rmse, "correlation": corr}


def candidate_prediction(train, valid, features, alpha):
    xtr, means, stds = standardize_fit(train, features)
    xva = standardize_apply(valid, features, means, stds)
    beta = ridge_fit(xtr.to_numpy(float), train["next_ppr_per_game"].to_numpy(float), alpha)
    return ridge_predict(xva.to_numpy(float), beta)


def fit_position(path: Path, pos: str):
    df = pd.read_csv(path)
    df = df[df["next_ppr_per_game"].notna()].copy()
    full = [f for f in FEATURES[pos] if f in df.columns]
    opportunity = [f for f in OPPORTUNITY_FEATURES[pos] if f in df.columns]
    if len(df) < 10 or "ppr_per_game" not in df.columns:
        raise RuntimeError(f"Insufficient {pos} training data")

    train = df[df["season"].eq(2023)]
    valid = df[df["season"].eq(2024)]
    if len(train) < 8 or len(valid) < 5:
        df = df.sort_values(["season", "player_id"])
        cut = max(1, int(len(df) * 0.75))
        train, valid = df.iloc[:cut], df.iloc[cut:]

    yva = valid["next_ppr_per_game"].to_numpy(float)
    baseline_pred = valid["ppr_per_game"].to_numpy(float)
    baseline_metrics = metrics(yva, baseline_pred)

    trials = []
    for feature_set_name, features in [("full", full), ("opportunity", opportunity)]:
        if not features:
            continue
        for alpha in ALPHAS:
            ridge = candidate_prediction(train, valid, features, alpha)
            for blend_weight in BLEND_WEIGHTS:
                pred = (1 - blend_weight) * baseline_pred + blend_weight * ridge
                m = metrics(yva, pred)
                trials.append({
                    "feature_set": feature_set_name,
                    "features": features,
                    "alpha": alpha,
                    "blend_weight": blend_weight,
                    "metrics": m,
                })

    best = min(trials, key=lambda x: (x["metrics"]["rmse"], x["metrics"]["mae"]))
    promoted = best["metrics"]["rmse"] < baseline_metrics["rmse"]

    if not promoted:
        return {
            "position": pos,
            "target": "next_ppr_per_game",
            "selected_model": "persistence_baseline",
            "training_seasons": [2023, 2024],
            "baseline_metrics": baseline_metrics,
            "holdout_metrics": baseline_metrics,
            "challenger_metrics": best["metrics"],
            "challenger": {k: best[k] for k in ["feature_set", "features", "alpha", "blend_weight"]},
            "promoted": False,
        }

    selected_features = best["features"]
    xall, means, stds = standardize_fit(df, selected_features)
    yall = df["next_ppr_per_game"].to_numpy(float)
    beta = ridge_fit(xall.to_numpy(float), yall, best["alpha"])
    ridge_fit_pred = ridge_predict(xall.to_numpy(float), beta)
    baseline_all = df["ppr_per_game"].to_numpy(float)
    blended_fit = (1 - best["blend_weight"]) * baseline_all + best["blend_weight"] * ridge_fit_pred

    coef = {name: float(value) for name, value in zip(selected_features, beta[1:])}
    ranked = sorted(coef.items(), key=lambda kv: abs(kv[1]), reverse=True)
    return {
        "position": pos,
        "target": "next_ppr_per_game",
        "selected_model": "baseline_blended_ridge",
        "feature_set": best["feature_set"],
        "training_seasons": [2023, 2024],
        "best_alpha": best["alpha"],
        "blend_weight": best["blend_weight"],
        "features": selected_features,
        "intercept": float(beta[0]),
        "coefficients_standardized": coef,
        "feature_means": {k: float(v) for k, v in means.items()},
        "feature_stds": {k: float(v) for k, v in stds.items()},
        "baseline_metrics": baseline_metrics,
        "holdout_metrics": best["metrics"],
        "refit_metrics": metrics(yall, blended_fit),
        "importance_order": [name for name, _ in ranked],
        "promoted": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/projections"))
    parser.add_argument("--out", type=Path, default=Path("data/projections/model_coefficients_v0_2.json"))
    args = parser.parse_args()

    models = {}
    for pos in ["QB", "RB", "WR", "TE"]:
        path = args.data_dir / f"training_{pos.lower()}_next_season.csv"
        models[pos] = fit_position(path, pos)
        m = models[pos]
        print(pos, "baseline", m["baseline_metrics"])
        print(pos, "selected", m["selected_model"], m["holdout_metrics"])
        if m.get("importance_order"):
            print(pos, "top features", m["importance_order"][:6])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"version": "0.2", "models": models}, indent=2))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
