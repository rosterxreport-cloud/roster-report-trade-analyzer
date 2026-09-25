#!/usr/bin/env python3
"""Historical Week 1-2 fantasy projection runner (baseline only).
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
# Current-model efficiency regression weights, pinned for historical replay.
REGRESSION_WEIGHTS={"catch_rate":0.30,"yards_per_target":0.35,"receiving_td_per_target":0.55,"yards_per_carry":0.35,"passing_ypa":0.30,"passing_td_rate":0.45,"interception_rate":0.40,"rushing_td_rate":0.35}
NEUTRAL={"catch_rate":0.645,"yards_per_target":7.5,"receiving_td_per_target":0.045,"yards_per_carry":4.3,"passing_ypa":7.15,"passing_td_rate":0.045,"interception_rate":0.022,"rushing_td_rate":0.025}
def regress(observed,metric):
 w=REGRESSION_WEIGHTS[metric]
 try:o=float(observed)
 except:o=NEUTRAL[metric]
 if not np.isfinite(o):o=NEUTRAL[metric]
 return w*o+(1-w)*NEUTRAL[metric]
def prior_strength(p):
 # Historical analyticsScore is the cleanest common numeric player-quality signal
 # present in both pinned repository snapshots.
 try:return float(p.get("analyticsScore",50) or 50)
 except:return 50.
def preweek_usage(stats):
 if stats.empty:return {}
 s=stats.copy();s["k"]=s.player_display_name.map(key)
 # Aggregate only games strictly before the projection week.
 sumcols=[z for z in ["games","attempts","passing_yards","passing_tds","passing_interceptions","carries","rushing_yards","rushing_tds","targets","receptions","receiving_yards","receiving_tds","fantasy_points_ppr"] if z in s]
 g=s.groupby(["k","position","recent_team"],as_index=False)[sumcols].sum()
 out={}
 for _,r in g.iterrows():
  games=max(1.,float(r.get("games",0) or 0))
  out[r.k]={z:float(r.get(z,0) or 0)/games for z in sumcols if z!="games"}
 return out
def team_volume(stats):
 if stats.empty:return {}
 s=stats.copy()
 for z in ["attempts","carries"]:
  if z not in s:s[z]=0
 g=s.groupby("recent_team",as_index=False)[["attempts","carries"]].sum()
 games=s.groupby("recent_team")["week"].nunique().to_dict()
 return {team(r.recent_team):{"pass_att_pg":float(r.attempts)/max(1,games.get(r.recent_team,1)),"carries_pg":float(r.carries)/max(1,games.get(r.recent_team,1))} for _,r in g.iterrows()}
def actual_usage_points(r):
 return float(r.get("fantasy_points_ppr",0) or 0)
for week in (1,2):
 x=load(week); prior=x["prior"]["half"]; hist=x["stats"].copy(); usage_detail=preweek_usage(hist); team_detail=team_volume(hist)
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
  rows.append({"player":p["name"],"position":pos,"team":p.get("team"),"opponent":x["opponent"].get(team(p.get("team"))),"standard_projection":round(standard,3),"half_projection":round(half,3),"ppr_projection":round(ppr,3),"backtest_week":week,"runner_stage":"BASELINE_ONLY_NOT_CURRENT_MODEL"})
 pd.DataFrame(rows).to_csv(OUT/f"week{week}_projections.csv",index=False)
 print(f"Week {week}: wrote {len(rows)} baseline projections")
