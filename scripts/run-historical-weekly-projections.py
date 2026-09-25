#!/usr/bin/env python3
"""Historical Week 1-2 fantasy projection runner (baseline only).
Uses frozen point-in-time player priors plus only pre-week 2026 usage.
This first pass creates a reproducible no-leakage baseline for all QB/RB/WR/TE.
"""
import sys
from pathlib import Path
import pandas as pd, numpy as np
import json
PBP="https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet"
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
def injury_factors(week):
 p=OUT/"priors"/f"week{week}_injuries.json"
 if not p.exists():return {}
 try:d=json.loads(p.read_text()).get("players",{})
 except:return {}
 out={}
 for name,x in d.items():
  status=str(x.get("status","") or "").upper()
  a=float(x.get("availability",1) or 0); w=float(x.get("workload",1) or 0)
  if any(z in status for z in ["INJURED RESERVE","IR -","PUP","NFI","OUT ","INACTIVE","UNAVAILABLE"]): factor=0.0
  elif "DOUBTFUL" in status: factor=min(.25,a*w)
  else: factor=max(0.,min(1.,a*w))
  out[key(name)]=(factor,status)
 return out
def defense_multipliers(week):
 # Only plays from weeks before the projected week are eligible. Week 1 is neutral.
 if week==1:return {}
 try:
  pbp=pd.read_parquet(PBP)
  if "week" in pbp: pbp=pbp[(pbp.season_type=="REG")&(pbp.week<week)].copy()
  vals={}
  for d,g in pbp.groupby("defteam"):
   e=pd.to_numeric(g.get("epa"),errors="coerce").mean()
   vals[team(d)]=e
  if not vals:return {}
  s=pd.Series(vals);pct=s.rank(pct=True)
  # Same intentionally modest early-season opponent envelope: +/-12%.
  return {k:.88+.24*float(pct[k]) for k in pct.index}
 except Exception as ex:
  print("Historical defense neutral fallback:",ex);return {}
def project_from_usage(pos,p,ud,td):
 # Historical replay of the current model's early-season opportunity + efficiency structure.
 score=prior_strength(p)
 if pos=="QB":
  att0=max(27.,min(40.,td.get("pass_att_pg",32.5)))
  att=.60*ud.get("attempts",att0)+.40*att0
  ypa=regress(ud.get("passing_yards",att*NEUTRAL["passing_ypa"])/max(1.,ud.get("attempts",att)), "passing_ypa")
  tdr=regress(ud.get("passing_tds",att*NEUTRAL["passing_td_rate"])/max(1.,ud.get("attempts",att)), "passing_td_rate")
  intr=regress(ud.get("passing_interceptions",att*NEUTRAL["interception_rate"])/max(1.,ud.get("attempts",att)), "interception_rate")
  car=.45*ud.get("carries",2.5)+.55*2.5; ry=car*4.5; rtd=car*NEUTRAL["rushing_td_rate"]
  std=att*ypa*.04+att*tdr*4-att*intr*2+ry*.1+rtd*6
  return std,std,std
 if pos=="RB":
  car0=max(4.,min(22.,6.+score*.14));car=.55*ud.get("carries",car0)+.45*car0
  tgt0=max(1.,min(7.,1.+score*.045));tgt=.55*ud.get("targets",tgt0)+.45*tgt0
 elif pos=="WR":
  tgt0=max(2.,min(11.,2.+score*.085));tgt=.55*ud.get("targets",tgt0)+.45*tgt0;car=0
 else:
  tgt0=max(1.5,min(8.,1.5+score*.055));tgt=.55*ud.get("targets",tgt0)+.45*tgt0;car=0
 cr=regress(ud.get("receptions",tgt*NEUTRAL["catch_rate"])/max(1.,ud.get("targets",tgt)),"catch_rate")
 ypt=regress(ud.get("receiving_yards",tgt*NEUTRAL["yards_per_target"])/max(1.,ud.get("targets",tgt)),"yards_per_target")
 rtdr=regress(ud.get("receiving_tds",tgt*NEUTRAL["receiving_td_per_target"])/max(1.,ud.get("targets",tgt)),"receiving_td_per_target")
 rec=tgt*cr;std=tgt*ypt*.1+tgt*rtdr*6
 if pos=="RB":
  ypc=regress(ud.get("rushing_yards",car*NEUTRAL["yards_per_carry"])/max(1.,ud.get("carries",car)),"yards_per_carry")
  rutdr=regress(ud.get("rushing_tds",car*NEUTRAL["rushing_td_rate"])/max(1.,ud.get("carries",car)),"rushing_td_rate")
  std+=car*ypc*.1+car*rutdr*6
 return std,std+.5*rec,std+rec
def actual_usage_points(r):
 return float(r.get("fantasy_points_ppr",0) or 0)
for week in (1,2):
 x=load(week); prior=x["prior"]["half"]; hist=x["stats"].copy(); usage_detail=preweek_usage(hist); team_detail=team_volume(hist); def_mult=defense_multipliers(week); injuries=injury_factors(week)
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
  ud=usage_detail.get(k,{})
  td=team_detail.get(team(p.get("team")),{})
  standard,half,ppr=project_from_usage(pos,p,ud,td)
  mm=float(def_mult.get(x["opponent"].get(team(p.get("team"))),1.0));standard*=mm;half*=mm;ppr*=mm
  af,status=injuries.get(k,(1.0,"NO HISTORICAL ADJUSTMENT"));standard*=af;half*=af;ppr*=af
  rows.append({"player":p["name"],"position":pos,"team":p.get("team"),"opponent":x["opponent"].get(team(p.get("team"))),"standard_projection":round(standard,3),"half_projection":round(half,3),"ppr_projection":round(ppr,3),"backtest_week":week,"runner_stage":"CURRENT_FORMULA_HISTORICAL_REPLAY_V2","availability_factor":round(af,3),"historical_status":status})
 pd.DataFrame(rows).to_csv(OUT/f"week{week}_projections.csv",index=False)
 print(f"Week {week}: wrote {len(rows)} baseline projections")
