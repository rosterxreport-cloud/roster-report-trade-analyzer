#!/usr/bin/env python3
"""Historical Week 1-2 fantasy projection runner.
Uses frozen point-in-time player priors plus only pre-week 2026 usage.
This first pass creates a reproducible no-leakage baseline for all QB/RB/WR/TE.
"""
import sys
from pathlib import Path
import pandas as pd, numpy as np
sys.path.insert(0,str(Path(__file__).parent))
from backtest_point_in_time import load,key,team
OUT=Path("data/backtests")
# Stable position-level PPR baselines used only when a player has no prior-season weekly usage.
POS_BASE={"QB":17.0,"RB":9.5,"WR":8.5,"TE":6.5}
def prior_strength(p):
 # Historical analyticsScore is the cleanest common numeric player-quality signal
 # present in both pinned repository snapshots.
 try:return float(p.get("analyticsScore",50) or 50)
 except:return 50.
def actual_usage_points(r):
 return float(r.get("fantasy_points_ppr",0) or 0)
for week in (1,2):
 x=load(week); prior=x["prior"]["half"]; hist=x["stats"].copy()
 if len(hist):
  hist["k"]=hist.player_display_name.map(key)
  usage=hist.groupby("k",as_index=False).agg(games=("week","nunique"),ppr=("fantasy_points_ppr","mean"))
  um={r.k:r for _,r in usage.iterrows()}
 else: um={}
 rows=[]
 for p in prior:
  pos=p.get("pos")
  if pos not in ("QB","RB","WR","TE"): continue
  k=key(p.get("name")); q=um.get(k)
  score=prior_strength(p)
  # Convert frozen quality prior to a conservative weekly PPR baseline.
  base=POS_BASE[pos]*(0.70+0.006*min(100,max(0,score)))
  # Week 2 may move modestly toward Week 1 usage; Week 1 cannot.
  if q is not None: ppr=.70*base+.30*float(q.ppr)
  else: ppr=base
  # Scoring-format deltas are generated from a conservative expected reception
  # component by position; raw-stat runners will replace this baseline next.
  rec={"QB":0.0,"RB":3.0,"WR":4.5,"TE":3.5}[pos]
  half=ppr-.5*rec; standard=ppr-rec
  rows.append({"player":p["name"],"position":pos,"team":p.get("team"),"opponent":x["opponent"].get(team(p.get("team"))),"standard_projection":round(standard,3),"half_projection":round(half,3),"ppr_projection":round(ppr,3),"backtest_week":week,"runner_stage":"point-in-time baseline"})
 pd.DataFrame(rows).to_csv(OUT/f"week{week}_projections.csv",index=False)
 print(f"Week {week}: wrote {len(rows)} baseline projections")
