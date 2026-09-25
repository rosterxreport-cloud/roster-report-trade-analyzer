#!/usr/bin/env python3
"""Leakage-safe weekly backtest scaffold for 2026 Weeks 1-2.
Builds immutable point-in-time input cuts and actual scoring outputs.
Projection formulas are intentionally not refit here.
"""
import pandas as pd, numpy as np, json
from pathlib import Path
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.csv"
OUT=Path("data/backtests"); OUT.mkdir(parents=True,exist_ok=True)
df=pd.read_csv(URL,low_memory=False)
df=df[(df.season_type=="REG") & (df.position.isin(["QB","RB","WR","TE"]))].copy()
def num(c): return pd.to_numeric(df[c],errors="coerce").fillna(0) if c in df else 0
# Actual fantasy scoring from raw box-score stats.
df["std_actual"]=num("passing_yards")*.04+num("passing_tds")*4-num("passing_interceptions")*2+num("rushing_yards")*.1+num("rushing_tds")*6+num("receiving_yards")*.1+num("receiving_tds")*6+num("fumbles_lost")*-2
df["half_actual"]=df["std_actual"]+num("receptions")*.5
df["ppr_actual"]=df["std_actual"]+num("receptions")
keep=[c for c in ["season","week","player_id","player_display_name","position","recent_team","completions","attempts","passing_yards","passing_tds","interceptions","carries","rushing_yards","rushing_tds","targets","receptions","receiving_yards","receiving_tds","target_share","air_yards_share","receiving_air_yards","std_actual","half_actual","ppr_actual"] if c in df]
for week in [1,2]:
 actual=df[df.week.eq(week)][keep].copy()
 actual.to_csv(OUT/f"week{week}_actuals.csv",index=False)
 # Cutoff state: Week 1 has no 2026 game results; Week 2 may use Week 1 only.
 prior=df[df.week.lt(week)][keep].copy()
 prior.to_csv(OUT/f"week{week}_prior_2026.csv",index=False)
manifest={"season":2026,"weeks":[1,2],"rules":{"week1":"No 2026 regular-season results permitted as inputs.","week2":"Only Week 1 2026 regular-season results permitted as current-season inputs.","frozen_model":"Use current weekly formulas/weights; do not refit on Weeks 1-2.","actual_scoring":"4-point pass TD; -2 INT; 0.04/pass yd; 0.1 rush/rec yd; 6 rush/rec TD; -2 lost fumble; reception premium 0/.5/1."},"rows":{f"week{w}":int((df.week==w).sum()) for w in [1,2]}}
(OUT/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
print(json.dumps(manifest,indent=2))
