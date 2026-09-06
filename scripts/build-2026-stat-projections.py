#!/usr/bin/env python3
"""Generate first context-aware 2026 veteran stat projections.

Produces football counting stats plus PPR, Half PPR and Standard fantasy points.
Rookies/missing-history players and unresolved team-context rows remain explicit
rather than receiving guessed projections.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

GAMES = 17.0
REGRESSION = {
    "catch_rate": 0.30,
    "yards_per_target": 0.35,
    "rec_td_per_target": 0.55,
    "yards_per_carry": 0.35,
    "pass_yards_per_attempt": 0.30,
    "pass_td_rate": 0.45,
    "interception_rate": 0.40,
    "rush_td_per_attempt": 0.35,
}


def numeric(s):
    return pd.to_numeric(s, errors="coerce")


def norm_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", text.lower())
    return re.sub(r"[^a-z0-9]", "", text)


def finite(value):
    try:
        return np.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def regress(value, mean, amount):
    mean = float(mean) if finite(mean) else 0.0
    if not finite(value):
        return mean
    return (1 - amount) * float(value) + amount * mean


def scoring(row, reception_points):
    vals = {k: (float(v) if finite(v) else 0.0) for k, v in row.items()}
    return (
        0.04 * vals.get("projected_passing_yards", 0)
        + 4 * vals.get("projected_passing_tds", 0)
        - 2 * vals.get("projected_interceptions", 0)
        + 0.10 * vals.get("projected_rushing_yards", 0)
        + 6 * vals.get("projected_rushing_tds", 0)
        + reception_points * vals.get("projected_receptions", 0)
        + 0.10 * vals.get("projected_receiving_yards", 0)
        + 6 * vals.get("projected_receiving_tds", 0)
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--roles", type=Path, default=Path("data/projections/player_role_context_2026.csv"))
    parser.add_argument("--features", type=Path, default=Path("data/projections/player_features_2023_2025.csv"))
    parser.add_argument("--history", type=Path, default=Path("data/projections/history_baseline_2026.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/projections/stat_projections_2026.csv"))
    args = parser.parse_args()

    roles = pd.read_csv(args.roles)
    features = pd.read_csv(args.features)
    hist = pd.read_csv(args.history)
    latest = features[features["season"].eq(2025)].copy()
    latest["name_key"] = latest["player_display_name"].fillna(latest.get("player_name", "")).map(norm_name)

    means = {}
    for pos, g in latest.groupby("position"):
        means[pos] = {
            c: float(numeric(g[c]).mean())
            for c in [
                "catch_rate", "yards_per_target", "rec_td_per_target", "yards_per_carry",
                "pass_yards_per_attempt", "pass_td_rate", "interception_rate",
                "rush_td_per_attempt", "rushing_epa_per_attempt"
            ] if c in g.columns and finite(numeric(g[c]).mean())
        }

    feature_keep = [c for c in [
        "name_key", "position", "catch_rate", "yards_per_target", "rec_td_per_target",
        "yards_per_carry", "pass_yards_per_attempt", "pass_td_rate",
        "interception_rate", "rush_td_per_attempt", "carries_per_game",
        "targets_per_game", "attempts_per_game", "rushing_epa_per_attempt"
    ] if c in latest.columns]
    base = roles.merge(latest[feature_keep], on=["name_key", "position"], how="left", suffixes=("", "_eff"))

    if "player_display_name" in hist.columns:
        hist = hist.copy()
        hist["name_key"] = hist["player_display_name"].fillna(hist.get("player_name", "")).map(norm_name)
        base = base.merge(hist[["name_key", "position", "history_baseline_ppr_per_game"]], on=["name_key", "position"], how="left")

    out = []
    for _, r in base.iterrows():
        d = r.to_dict()
        pos = d.get("position")
        m = means.get(pos, {})
        manual = bool(d.get("needs_rookie_or_manual_role", False))
        context_missing = not finite(d.get("projected_pass_attempts")) or not finite(d.get("projected_rush_attempts"))
        status = "manual_role_required" if manual else ("context_missing" if context_missing else "modeled_veteran")

        row = {
            "name": d.get("name"), "team": d.get("team_2026"), "position": pos,
            "rookie": bool(d.get("rookie", False)), "changed_team": bool(d.get("changed_team", False)),
            "role_confidence": d.get("role_confidence"),
            "history_baseline_ppr_per_game": d.get("history_baseline_ppr_per_game"),
            "projection_status": status,
        }
        stat_cols = [
            "projected_pass_attempts", "projected_passing_yards", "projected_passing_tds", "projected_interceptions",
            "projected_rush_attempts", "projected_rushing_yards", "projected_rushing_tds",
            "projected_targets", "projected_receptions", "projected_receiving_yards", "projected_receiving_tds"
        ]
        for c in stat_cols:
            row[c] = np.nan if status != "modeled_veteran" else 0.0

        if status != "modeled_veteran":
            out.append(row)
            continue

        team_pass = float(d["projected_pass_attempts"])
        team_rush = float(d["projected_rush_attempts"])

        if pos == "QB":
            share = d.get("role_qb_attempt_share_2026")
            share = 0.97 if not finite(share) else float(np.clip(share, 0.20, 1.0))
            attempts = team_pass * share
            ypa = regress(d.get("pass_yards_per_attempt"), m.get("pass_yards_per_attempt", 7.0), REGRESSION["pass_yards_per_attempt"])
            td_rate = regress(d.get("pass_td_rate"), m.get("pass_td_rate", 0.045), REGRESSION["pass_td_rate"])
            int_rate = regress(d.get("interception_rate"), m.get("interception_rate", 0.022), REGRESSION["interception_rate"])
            rush_pg = d.get("carries_per_game")
            rush_pg = 3.5 if not finite(rush_pg) else max(0, float(rush_pg))
            ypc = regress(d.get("yards_per_carry"), m.get("yards_per_carry", 4.7), REGRESSION["yards_per_carry"])
            rush_td_rate = regress(d.get("rush_td_per_attempt"), m.get("rush_td_per_attempt", 0.035), REGRESSION["rush_td_per_attempt"])
            row.update({
                "projected_pass_attempts": attempts,
                "projected_passing_yards": attempts * ypa,
                "projected_passing_tds": attempts * td_rate,
                "projected_interceptions": attempts * int_rate,
                "projected_rush_attempts": rush_pg * GAMES,
                "projected_rushing_yards": rush_pg * GAMES * ypc,
                "projected_rushing_tds": rush_pg * GAMES * rush_td_rate,
            })

        elif pos == "RB":
            carry_share = d.get("role_carry_share_2026")
            target_share = d.get("role_target_share_2026")
            carry_share = 0.35 if not finite(carry_share) else float(np.clip(carry_share, 0.01, 0.90))
            target_share = 0.08 if not finite(target_share) else float(np.clip(target_share, 0.005, 0.35))
            carries = team_rush * carry_share
            targets = team_pass * target_share
            ypc = regress(d.get("yards_per_carry"), m.get("yards_per_carry", 4.25), REGRESSION["yards_per_carry"])
            catch = regress(d.get("catch_rate"), m.get("catch_rate", 0.77), REGRESSION["catch_rate"])
            ypt = regress(d.get("yards_per_target"), m.get("yards_per_target", 6.2), REGRESSION["yards_per_target"])
            rec_td = regress(d.get("rec_td_per_target"), m.get("rec_td_per_target", 0.025), REGRESSION["rec_td_per_target"])
            rush_td_rate = regress(d.get("rush_td_per_attempt"), m.get("rush_td_per_attempt", 0.03), REGRESSION["rush_td_per_attempt"])
            row.update({
                "projected_rush_attempts": carries, "projected_rushing_yards": carries * ypc,
                "projected_rushing_tds": carries * rush_td_rate, "projected_targets": targets,
                "projected_receptions": targets * catch, "projected_receiving_yards": targets * ypt,
                "projected_receiving_tds": targets * rec_td,
            })

        elif pos in {"WR", "TE"}:
            target_share = d.get("role_target_share_2026")
            default_share = 0.16 if pos == "WR" else 0.11
            target_share = default_share if not finite(target_share) else float(np.clip(target_share, 0.005, 0.38))
            targets = team_pass * target_share
            catch = regress(d.get("catch_rate"), m.get("catch_rate", 0.64 if pos == "WR" else 0.68), REGRESSION["catch_rate"])
            ypt = regress(d.get("yards_per_target"), m.get("yards_per_target", 8.0 if pos == "WR" else 7.5), REGRESSION["yards_per_target"])
            rec_td = regress(d.get("rec_td_per_target"), m.get("rec_td_per_target", 0.05), REGRESSION["rec_td_per_target"])
            row.update({
                "projected_targets": targets, "projected_receptions": targets * catch,
                "projected_receiving_yards": targets * ypt, "projected_receiving_tds": targets * rec_td,
            })

        row["ppr_points"] = scoring(row, 1.0)
        row["half_ppr_points"] = scoring(row, 0.5)
        row["standard_points"] = scoring(row, 0.0)
        row["ppr_per_game"] = row["ppr_points"] / GAMES
        row["half_ppr_per_game"] = row["half_ppr_points"] / GAMES
        row["standard_per_game"] = row["standard_points"] / GAMES
        out.append(row)

    result = pd.DataFrame(out)
    for fmt in ["ppr_points", "half_ppr_points", "standard_points"]:
        result[fmt.replace("_points", "_overall_rank")] = result[fmt].rank(method="min", ascending=False)
        for pos in ["QB", "RB", "WR", "TE"]:
            mask = result["position"].eq(pos) & result[fmt].notna()
            result.loc[mask, fmt.replace("_points", "_pos_rank")] = result.loc[mask, fmt].rank(method="min", ascending=False)

    numeric_cols = result.select_dtypes(include=[np.number]).columns
    result[numeric_cols] = result[numeric_cols].round(2)
    result = result.sort_values(["projection_status", "half_ppr_points"], ascending=[True, False])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.out, index=False)

    modeled = result[result["projection_status"].eq("modeled_veteran")]
    print(f"Modeled veterans: {len(modeled)}")
    print(f"Manual/rookie rows: {int((result['projection_status'] == 'manual_role_required').sum())}")
    print(f"Context-missing rows: {int((result['projection_status'] == 'context_missing').sum())}")
    missing = result[result["projection_status"].eq("context_missing")][["name", "team", "position"]]
    if len(missing):
        print("Context missing:", missing.to_dict("records"))
    for pos in ["QB", "RB", "WR", "TE"]:
        top = modeled[modeled["position"].eq(pos)].nlargest(5, "half_ppr_points")
        print(pos, list(zip(top["name"], top["half_ppr_points"].round(1))))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
