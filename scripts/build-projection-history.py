#!/usr/bin/env python3
"""Build model-ready projection history from the v10 analytics audit workbook.

Usage:
    python scripts/build-projection-history.py \
      Roster_Report_Trade_Analyzer_Top_250_v10_Analytics_Audit.xlsx \
      projection-history.json

The output intentionally contains historical Roster Report ratings and current
v10 model components only. It does NOT pretend those ratings are raw football
stats. Raw QB/RB/WR/TE features are added by the separate feature pipeline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import openpyxl

SEASON_WEIGHTS = {"2025": 0.50, "2024": 0.30, "2023": 0.20}


def reliability(games):
    if games is None:
        return 0.0
    return min(max(float(games), 0.0) / 12.0, 1.0)


def sheet_records(ws):
    headers = [cell.value for cell in ws[1]]
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not any(v is not None for v in row):
            continue
        yield dict(zip(headers, row))


def build_history(workbook_path: Path):
    wb = openpyxl.load_workbook(workbook_path, data_only=True)

    # Half-PPR is used only for identity and the scoring-neutral model
    # components that are duplicated across the three public boards.
    current = {}
    for row in sheet_records(wb["Half-PPR"]):
        name = row.get("Player")
        if not name:
            continue
        current[name] = row

    history = {}
    for row in sheet_records(wb["History Detail"]):
        name = row.get("Player")
        if not name:
            continue
        history[name] = {
            "threeYearRating": row.get("3Yr Rating"),
            "seasons": {
                "2025": {
                    "rating": row.get("2025 Rating"),
                    "games": row.get("2025 G"),
                    "reliability": row.get("2025 Rel"),
                },
                "2024": {
                    "rating": row.get("2024 Rating"),
                    "games": row.get("2024 G"),
                    "reliability": row.get("2024 Rel"),
                },
                "2023": {
                    "rating": row.get("2023 Rating"),
                    "games": row.get("2023 G"),
                    "reliability": row.get("2023 Rel"),
                },
            },
            "treatment": "main-history",
        }

    # v10 re-audited the Top-250 extension against the same raw-history rules.
    for row in sheet_records(wb["Extension Analytics Audit"]):
        name = row.get("Player")
        if not name:
            continue
        history[name] = {
            "threeYearRating": row.get("3Yr Analytics"),
            "seasons": {
                season: {
                    "rating": row.get(f"{season} Rating"),
                    "games": row.get(f"{season} G"),
                    "reliability": reliability(row.get(f"{season} G")),
                }
                for season in ("2025", "2024", "2023")
            },
            "treatment": row.get("Treatment") or "extension-audit",
        }

    players = []
    for name, row in current.items():
        players.append(
            {
                "name": name,
                "team": row.get("Team"),
                "pos": row.get("Pos"),
                "rookie": row.get("Rookie Pathway") == "Yes",
                "modelRank": row.get("Model Rank"),
                "baseTradeValue": row.get("Final Score"),
                "awRank": row.get("AW Rank"),
                "analyticsRating": row.get("Analytics Rating"),
                "analyticsScore": row.get("Analytics Score"),
                "scarcityScore": row.get("Scarcity Score"),
                "marketScore": row.get("Market/Trade Score"),
                "draftPick": row.get("2026 Draft Pick"),
                "draftCapitalScore": row.get("Draft Capital Score"),
                "analyticsWindow": row.get("Analytics Window"),
                "history": history.get(name),
            }
        )

    return {
        "version": "phase2-v0.1",
        "source": workbook_path.name,
        "seasonWeights": SEASON_WEIGHTS,
        "partialSeasonRule": (
            "season weight * min(games / 12, 1), then renormalize observed seasons"
        ),
        "coverage": {
            "players": len(players),
            "withHistoricalRating": sum(1 for player in players if player["history"]),
            "withoutHistoricalRating": sum(1 for player in players if not player["history"]),
        },
        "players": players,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    payload = build_history(args.workbook)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"Wrote {args.output}: {payload['coverage']['withHistoricalRating']}/"
        f"{payload['coverage']['players']} players have historical ratings"
    )


if __name__ == "__main__":
    main()
