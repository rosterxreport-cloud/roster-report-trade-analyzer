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
games=[("PHI","JAX"),("CIN","MIA"),("LV","NE"),("MIN","NO"),("CLE","NYJ"),("IND","PIT"),("HOU","TEN"),("NYG","WAS"),("CHI","GB"),("DEN","LAC"),("DET","ARI"),("SF","SEA"),("BAL","ATL"),("BUF","LA")]
opponents={a:b for a,b in games};opponents.update({b:a for a,b in games})
last=last[last.recent_team.isin(opponents)].copy()
last=last[last.prior_opp>=1].copy()
# NFL official October 11 Week 5 inactives: filter prior to team volume allocation.
inactive_players = (
 "Saquon Barkley", "DeVonta Smith", "Marquise Brown", "Colbie Young",
 "Caleb Douglas", "Kaytron Allen", "Jalen Nailor", "Jordan Addison",
 "Breece Hall", "Adonai Mitchell", "Ashton Dulin", "Darius Slayton",
 "Rico Dowdle", "Devin Singletary", "Stefon Diggs", "Kyle Monangai",
 "Caleb Williams", "Lamar Jackson", "Nick Singleton"
)
last=last[~last.player_display_name.isin(inactive_players)].copy()

last=last.sort_values("prior_opp",ascending=False)
# Keep the primary Week 4 quarterback for each team.
q4=w[(w.position=="QB") & (w.week==4)].sort_values("attempts",ascending=False)
starter_ids=set(q4.drop_duplicates("recent_team").player_id)
last=last[(last.position!="QB") | last.player_id.isin(starter_ids)].copy()
# Structural v4 baseline, with player-specific observed usage.
pred=last.apply(project,axis=1)
last=pd.concat([last.reset_index(drop=True),pred.reset_index(drop=True)],axis=1)
# Smooth QB rushing touchdowns using observed 2026 QB touchdown frequency.
qh=w[w.position=="QB"]
qr=float(qh.rushing_tds.sum())/max(float(qh.carries.sum()),1.)
for i in last.index[last.position=="QB"]:
 h=qh[qh.player_id==last.at[i,"player_id"]]
 n=float(h.carries.sum())
 rate=(float(h.rushing_tds.sum())+20*qr)/(n+20)
 last.at[i,"pred_rush_td"]=min(float(last.at[i,"pred_carries"])*rate,0.75)
# Reduce small-sample touchdown spikes for secondary backs.
rb=(last.position=="RB")&last.player_display_name.ne("Javonte Williams")
carries=last.loc[rb,"pred_carries"].clip(lower=0)
raw=last.loc[rb,"pred_rush_td"]/carries.clip(lower=1)
last.loc[rb,"pred_rush_td"]=carries*(.75*.025+.25*raw).clip(upper=.06)
# Restrict fringe-player roles before redistributing to regular contributors.
caps={"Jonathan Mingo":0.6,"KaVontae Turpin":2.0,"Luke Schoonmaker":1.5,"Brevyn Spann-Ford":1.0,"Hunter Luepke":1.2,"Tyler Goodson":1.0}
for name,cap in caps.items():
 m=last.player_display_name.eq(name)
 if m.any():
  factor=(cap/last.loc[m,"pred_targets"].clip(lower=.001)).clip(upper=1)
  for field in ["pred_targets","pred_rec","pred_rec_yds","pred_rec_td"]:last.loc[m,field]*=factor
for name,cap in {"Tyler Goodson":3.,"Hunter Luepke":1.}.items():
 m=last.player_display_name.eq(name)
 if m.any():
  factor=(cap/last.loc[m,"pred_carries"].clip(lower=.001)).clip(upper=1)
  for field in ["pred_carries","pred_rush_yds","pred_rush_td"]:last.loc[m,field]*=factor
# Allocate team volume from projected QB attempts and historical team rush volume.
for team in opponents:
 mask=(last.recent_team==team)&last.position.isin(["RB","WR","TE"])
 qb=(last.recent_team==team)&(last.position=="QB")
 attempts=float(last.loc[qb,"pred_att"].max()) if qb.any() else float(last.loc[mask,"pre_team_pass"].median())
 qb_rush=float(last.loc[qb,"pred_carries"].max()) if qb.any() else 0.
 history=last.loc[mask,"pre_team_carries"].dropna()
 rush_budget=max(0.,float(history.iloc[0])-qb_rush) if len(history) else float(last.loc[mask,"pred_carries"].sum())
 for volume,budget,fields in [
  ("pred_targets",attempts,["pred_targets","pred_rec","pred_rec_yds","pred_rec_td"]),
  ("pred_carries",rush_budget,["pred_carries","pred_rush_yds","pred_rush_td"])
 ]:
  total=float(last.loc[mask,volume].sum())
  if total>budget and total>0:
   factor=budget/total
   for field in fields:last.loc[mask,field]*=factor
  elif total<budget:
   eligible=mask&((last.pred_targets>=2.5) if volume=="pred_targets" else ((last.position=="RB")&(last.pred_carries>=5)))
   weight=float(last.loc[eligible,volume].sum())
   if weight>0:
    factor=1+(budget-total)/weight
    for field in fields:last.loc[eligible,field]*=factor
# Reallocate backfield carries using actual Weeks 2-4 RB carry shares.
# Apply AFTER team-volume normalization so lead-back usage is not erased.
for team in opponents:
 backs=(last.recent_team==team)&last.position.eq("RB")
 recent=w[(w.recent_team==team)&w.week.between(2,4)&w.position.eq("RB")]
 observed=recent.groupby("player_id").carries.sum()
 denom=float(observed.sum())
 total=float(last.loc[backs,"pred_carries"].sum())
 if denom<=0 or total<=0:continue
 weights=last.loc[backs,"player_id"].map(observed).fillna(0).astype(float)
 if float(weights.sum())<=0:continue
 for idx,weight in weights.items():
  old=float(last.at[idx,"pred_carries"])
  new=total*float(weight)/float(weights.sum())
  if old>0:
   factor=new/old
   for field in ["pred_carries","pred_rush_yds","pred_rush_td"]:
    last.at[idx,field]*=factor
  else:
   last.at[idx,"pred_carries"]=new
   # Zero historical carries means efficiency is unknown; avoid inventing it.
last["Opponent"]=last.recent_team.map(opponents)
last["Total_xTD"]=last.pred_rush_td+last.pred_rec_td
last["PPR"]=last.apply(score,axis=1)
last["Half_PPR"]=last.PPR-.5*last.pred_rec
last["Standard"]=last.PPR-last.pred_rec
last["Pass_Att"]=last.pred_att;last["Pass_Yds"]=last.pred_pass_yds;last["Pass_TD"]=last.pred_pass_td
last["INT"]=last.pred_int;last["Rush_Att"]=last.pred_carries;last["Rush_Yds"]=last.pred_rush_yds
last["Rush_TD"]=last.pred_rush_td;last["Targets"]=last.pred_targets;last["Receptions"]=last.pred_rec
last["Rec_Yds"]=last.pred_rec_yds;last["Rec_TD"]=last.pred_rec_td
last=last[(last.position=="QB")|(last.prior_opp>=1)].copy()
last=last.rename(columns={"player_display_name":"Player","recent_team":"Team","position":"Position"})
out=last[["Player","Team","Opponent","Position","Rush_TD","Rec_TD","Total_xTD"]].sort_values("Total_xTD",ascending=False).round(3)
Path("data/projections").mkdir(parents=True,exist_ok=True)
out.to_csv("data/projections/2026_week5_league_v4_touchdowns.csv",index=False)
print(out.head(30).to_string(index=False))
