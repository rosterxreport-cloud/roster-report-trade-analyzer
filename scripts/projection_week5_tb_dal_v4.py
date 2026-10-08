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
pred=last.apply(project,axis=1)
last=pd.concat([last.reset_index(drop=True),pred.reset_index(drop=True)],axis=1)
# Role-aware corrections to known small-sample failure modes.
# Rookie QB: do not treat a partial first-month player sample as a full game.
# Daniels played all 63 Week 4 offensive snaps and completed 19/27 for 148,
# rushing for 55. Blend his start's attempts with a 30-attempt starter prior.
qb=last.Player_display_name.eq("Jalon Daniels") if "Player_display_name" in last else last.player_display_name.eq("Jalon Daniels")
if qb.any():
 attempts=.65*27+.35*30
 last.loc[qb,"pred_att"]=attempts
 last.loc[qb,"pred_comp"]=attempts*(.65*(19/27)+.35*.63)
 last.loc[qb,"pred_pass_yds"]=attempts*(.55*(148/27)+.45*7.0)
 last.loc[qb,"pred_pass_td"]=attempts*.040
 last.loc[qb,"pred_int"]=attempts*.026
 last.loc[qb,"pred_carries"]=7.0
 last.loc[qb,"pred_rush_yds"]=.60*55+.40*(7*4.7)
 last.loc[qb,"pred_rush_td"]=7*.035
# RB touchdown regression: low-carry backs cannot inherit a 1-TD/3-carry rate.
# Shrink the observed per-carry TD rate toward a 2.5% prior and cap at 6%.
# Explicitly preserve the user-approved Javonte Williams forecast.
rb=(last.position=="RB") & (last.player_display_name!="Javonte Williams")
if rb.any():
 carries=last.loc[rb,"pred_carries"].clip(lower=0)
 raw_rate=last.loc[rb,"pred_rush_td"] / carries.clip(lower=1)
 regressed_rate=(.75*.025+.25*raw_rate).clip(upper=.06)
 last.loc[rb,"pred_rush_td"]=carries*regressed_rate
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
# Constrain fringe depth-chart roles before scoring.
caps={"Jonathan Mingo":0.6,"KaVontae Turpin":2.0,"Luke Schoonmaker":1.5,"Brevyn Spann-Ford":1.0,"Hunter Luepke":1.2,"Tyler Goodson":1.0}
for name,cap in caps.items():
 m=last.player_display_name.eq(name)
 if m.any():
  k=(cap/last.loc[m,"pred_targets"].clip(lower=.001)).clip(upper=1)
  for col in ["pred_targets","pred_rec","pred_rec_yds","pred_rec_td"]:last.loc[m,col]*=k
for name,cap in {"Tyler Goodson":3.0,"Hunter Luepke":1.0}.items():
 m=last.player_display_name.eq(name)
 if m.any():
  k=(cap/last.loc[m,"pred_carries"].clip(lower=.001)).clip(upper=1)
  for col in ["pred_carries","pred_rush_yds","pred_rush_td"]:last.loc[m,col]*=k
# Keep team-level opportunities within plausible weekly budgets.
for team, target_budget, rush_budget in [("DAL",39.0,25.0),("TB",27.0,25.0)]:
 mask=(last.recent_team==team)&last.position.isin(["RB","WR","TE"])
 target_sum=last.loc[mask,"pred_targets"].sum()
 if target_sum>target_budget:
  factor=target_budget/target_sum
  last.loc[mask,["pred_targets","pred_rec","pred_rec_yds","pred_rec_td"]]*=factor
 rush_sum=last.loc[mask,"pred_carries"].sum()
 if rush_sum>rush_budget:
  factor=rush_budget/rush_sum
  last.loc[mask,["pred_carries","pred_rush_yds","pred_rush_td"]]*=factor
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
