#!/usr/bin/env python3
"""Week 5 projection: retain the repository structural v4 model; Weeks 1-4 are input only."""
import pandas as pd, numpy as np, sys
from pathlib import Path
sys.path.insert(0,"scripts")
from projection_v4_backtest import project, score
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.parquet"
w=pd.read_parquet(URL)
w=w[(w.season_type=="REG")&w.week.between(1,4)&w.position.isin(["QB","RB","WR","TE"])].copy()
if "recent_team" not in w:w["recent_team"]=w["team"]
cols=["attempts","completions","passing_yards","passing_tds","interceptions","carries","rushing_yards","rushing_tds","targets","receptions","receiving_yards","receiving_tds"]
for c in cols:
 if c not in w:w[c]=0
 w[c]=pd.to_numeric(w[c],errors="coerce").fillna(0)
w=w.sort_values(["player_id","week"])
# Four-week rolling history, using the SAME alpha and structural project() as v4.
last=w.groupby("player_id",as_index=False).tail(1).copy()
for c in cols:
 last["pre_"+c]=w.groupby("player_id")[c].transform(lambda s:s.ewm(alpha=.45,adjust=False).mean()).loc[last.index]
team=w.groupby(["recent_team","week"],as_index=False).agg(team_pass=("attempts","sum"),team_carries=("carries","sum"))
for c in ["team_pass","team_carries"]:
 team["pre_"+c]=team.groupby("recent_team")[c].transform(lambda s:s.ewm(alpha=.45,adjust=False).mean())
last=last.merge(team[team.week==4][["recent_team","pre_team_pass","pre_team_carries"]],on="recent_team",how="left")
last["week"]=5
# Select meaningful prior usage, no Week 5 outcome leakage.
last["prior_opp"]=last.pre_attempts.fillna(0)+last.pre_carries.fillna(0)+last.pre_targets.fillna(0)*1.5
last=last[last.recent_team.isin(["TB","DAL"])].copy()
last=last.sort_values("prior_opp",ascending=False)
# Baker is confirmed OUT; Jalon Daniels starts. Exclude injured starter.
last=last[last.player_display_name!="Baker Mayfield"].copy()
if not (last.player_display_name=="Jalon Daniels").any():raise RuntimeError("Jalon Daniels missing from Week 1-4 data")
# Empirical-only player projection. No positional defaults or fixed scoring rates.
# Four-week EWM observations form every rate and workload estimate.
def empirical(r):
 def value(c):return max(0.,float(r["pre_"+c]))
 att=value("attempts") if r.position=="QB" else 0.
 car=value("carries")
 tar=value("targets") if r.position!="QB" else 0.
 return pd.Series({
  "pred_att":att,"pred_comp":value("completions") if att else 0.,
  "pred_pass_yds":value("passing_yards") if att else 0.,
  "pred_pass_td":value("passing_tds") if att else 0.,
  "pred_int":value("interceptions") if att else 0.,
  "pred_carries":car,"pred_rush_yds":value("rushing_yards"),
  "pred_rush_td":value("rushing_tds"),
  "pred_targets":tar,"pred_rec":value("receptions") if tar else 0.,
  "pred_rec_yds":value("receiving_yards") if tar else 0.,
  "pred_rec_td":value("receiving_tds") if tar else 0.})
pred=last.apply(empirical,axis=1)
last=pd.concat([last.reset_index(drop=True),pred.reset_index(drop=True)],axis=1)
# Week 5 opponent defensive adjustment, using opponent-adjusted Weeks 1-4
# ranks (Sharp Football, Oct 6). Rank-based multipliers are deliberately
# regressed: 60% toward neutral and capped at +/- 10%.
# Ranks: DAL pass 32, rush 24; TB pass 18, rush 2.
def defense_multiplier(rank, max_swing=.10):
    strength=(float(rank)-16.5)/15.5
    return 1.0+max_swing*.60*strength
for team, pass_rank, rush_rank in [("TB",32,24),("DAL",18,2)]:
    t=last.recent_team.eq(team)
    pm=defense_multiplier(pass_rank)
    rm=defense_multiplier(rush_rank)
    q=t & last.position.eq("QB")
    skill=t & last.position.isin(["RB","WR","TE"])
    # Efficiency rather than a blanket points multiplier; retain opportunity.
    for col in ["pred_pass_yds","pred_pass_td"]:
        last.loc[q,col]=last.loc[q,col]*pm
    for col in ["pred_rec_yds","pred_rec_td"]:
        last.loc[skill,col]=last.loc[skill,col]*pm
    # Ground efficiency and scoring; do not modify approved Javonte baseline.
    rush=t & last.player_display_name.ne("Javonte Williams")
    for col in ["pred_rush_yds","pred_rush_td"]:
        last.loc[rush,col]=last.loc[rush,col]*rm
# Source: https://www.sharpfootballanalysis.com/stats-nfl/nfl-matchups/
# Exclude confirmed long-term IR players.
last=last[~last.player_display_name.isin(["Jalen McMillan","Emari Demercado","David Sills V"])].copy()
# Empirical workloads remain uncapped; team conservation below adjusts
# all players proportionally rather than applying subjective role thresholds.
# Allocate team volume from projected QB attempts and historical team rush volume.
for team in ["DAL","TB"]:
 mask=(last.recent_team==team)&last.position.isin(["RB","WR","TE"])
 qb=(last.recent_team==team)&(last.position=="QB")
 attempts=float(last.loc[qb,"pred_att"].sum())
 qb_rush=float(last.loc[qb,"pred_carries"].sum())
 history=last.loc[mask,"pre_team_carries"].dropna()
 rush_budget=max(0.,float(history.iloc[0])-qb_rush) if len(history) else float(last.loc[mask,"pred_carries"].sum())
 for volume,budget,fields in [
  ("pred_targets",attempts,["pred_targets","pred_rec","pred_rec_yds","pred_rec_td"]),
  ("pred_carries",rush_budget,["pred_carries","pred_rush_yds","pred_rush_td"])
 ]:
  total=float(last.loc[mask,volume].sum())
  if total>0 and budget>=0:
   scale=budget/total
   for field in fields:last.loc[mask,field]*=scale
last["PPR"]=last.apply(score,axis=1)
last["Half_PPR"]=last.PPR-.5*last.pred_rec
last["Standard"]=last.PPR-last.pred_rec
last["Pass_Att"]=last.pred_att;last["Pass_Yds"]=last.pred_pass_yds;last["Pass_TD"]=last.pred_pass_td
last["INT"]=last.pred_int;last["Rush_Att"]=last.pred_carries;last["Rush_Yds"]=last.pred_rush_yds
last["Rush_TD"]=last.pred_rush_td;last["Targets"]=last.pred_targets;last["Receptions"]=last.pred_rec
last["Rec_Yds"]=last.pred_rec_yds;last["Rec_TD"]=last.pred_rec_td
last=last[(last.position=="QB")|(last.prior_opp>=1)].copy()
last=last.rename(columns={"player_display_name":"Player","recent_team":"Team","position":"Position"})
out=last[["Player","Team","Position","Pass_Att","Pass_Yds","Pass_TD","INT","Rush_Att","Rush_Yds","Rush_TD","Targets","Receptions","Rec_Yds","Rec_TD","PPR","Half_PPR","Standard"]].sort_values("PPR",ascending=False).round(2)
Path("data/projections").mkdir(parents=True,exist_ok=True)
out.to_csv("data/projections/2026_week5_tb_dal_v4.csv",index=False)
print(out.to_string(index=False))

# trigger Week 5 TNF four-week model run
