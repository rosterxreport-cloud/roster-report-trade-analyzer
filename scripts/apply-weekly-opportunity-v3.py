#!/usr/bin/env python3
"""Predictive Opportunity v3.

Conservative weekly opportunity adjustment. Unlike v2, raw recent targets/carries
cannot dominate the baseline. Role is inferred from participation + market share
and only then translated into a bounded volume adjustment.

Expected input columns (missing columns safely fall back):
name, position, team, projected_targets/projected_rush_attempts/projected_pass_attempts
plus optional: snap_share, route_share, target_share, targets_per_route_run,
first_read_share, team_pass_attempts_pg, carry_share, goal_line_share,
recent_role_trend, injury_opportunity_multiplier, game_environment_multiplier.

No future-week outcomes are used.
"""
import argparse, numpy as np, pandas as pd
from pathlib import Path

def n(v,d=np.nan):
 try:
  x=float(v); return x if np.isfinite(x) else d
 except:return d

def weighted(signals):
 z=[(v,w) for v,w in signals if np.isfinite(v)]
 return sum(v*w for v,w in z)/sum(w for _,w in z) if z else 1.0

def ratio(v,base):
 return v/base if np.isfinite(v) and np.isfinite(base) and base>0 else np.nan

def scale(df,i,r,cols):
 for c in cols:
  if c in df and np.isfinite(n(df.at[i,c])): df.at[i,c]=n(df.at[i,c])*r

def main():
 p=argparse.ArgumentParser();p.add_argument("--stats",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
 a=p.parse_args();df=pd.read_csv(a.stats)
 df["opportunity_v3_multiplier"]=1.0;df["opportunity_v3_confidence"]=0.0
 for i,x in df.iterrows():
  pos=str(x.get("position",""))
  inj=n(x.get("injury_opportunity_multiplier"),1); env=n(x.get("game_environment_multiplier"),1)
  trend=n(x.get("recent_role_trend"),1)
  if pos in ("WR","TE"):
   base=n(x.get("projected_targets"))
   # Neutral reference levels make each metric a relative role signal.
   signals=[
    (ratio(n(x.get("route_share")), .75), .25),
    (ratio(n(x.get("target_share")), .20), .25),
    (ratio(n(x.get("targets_per_route_run")), .22), .15),
    (ratio(n(x.get("first_read_share")), .24), .15),
    (ratio(n(x.get("snap_share")), .75), .10),
    (trend,.10)]
   role=weighted(signals); raw=.72 + .28*role
   # team passing environment modifies role modestly
   tpa=n(x.get("team_pass_attempts_pg")); raw*=np.clip(ratio(tpa,34),.92,1.08) if np.isfinite(tpa) else 1
   raw*=np.clip(inj,.85,1.18)*np.clip(env,.94,1.06)
   mult=float(np.clip(raw,.78,1.28)); cols=["projected_targets","projected_receptions","projected_receiving_yards","projected_receiving_tds"]
  elif pos=="RB":
   signals=[(ratio(n(x.get("snap_share")),.60),.25),(ratio(n(x.get("carry_share")),.55),.35),
            (ratio(n(x.get("target_share")),.10),.15),(ratio(n(x.get("goal_line_share")),.50),.15),(trend,.10)]
   role=weighted(signals);raw=.74+.26*role;raw*=np.clip(inj,.82,1.20)*np.clip(env,.95,1.05)
   mult=float(np.clip(raw,.76,1.30));cols=["projected_rush_attempts","projected_rushing_yards","projected_rushing_tds","projected_targets","projected_receptions","projected_receiving_yards","projected_receiving_tds"]
  elif pos=="QB":
   tpa=n(x.get("team_pass_attempts_pg")); vol=ratio(tpa,34)
   raw=weighted([(vol,.55),(trend,.20),(env,.25)]);raw=.80+.20*raw
   mult=float(np.clip(raw,.88,1.12));cols=["projected_pass_attempts","projected_completions","projected_passing_yards","projected_passing_tds","projected_interceptions"]
  else: continue
  available=sum(np.isfinite(v) for v,w in signals) if pos!="QB" else sum(np.isfinite(v) for v,w in [(vol,.55),(trend,.20),(env,.25)])
  # With sparse data, shrink adjustment heavily toward original projection.
  confidence=min(1.0,available/4.0); mult=1+(mult-1)*confidence
  scale(df,i,mult,cols);df.at[i,"opportunity_v3_multiplier"]=mult;df.at[i,"opportunity_v3_confidence"]=confidence
 df.to_csv(a.out,index=False)
 print("Opportunity v3 applied",len(df),"players")
 print("Mean multiplier",round(float(df.opportunity_v3_multiplier.mean()),3))
if __name__=="__main__":main()
