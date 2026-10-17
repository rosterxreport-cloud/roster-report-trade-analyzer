#!/usr/bin/env python3
"""Week 6 projection: retain the repository structural v4 model; Weeks 1-5 are input only."""
import pandas as pd, numpy as np, sys
from pathlib import Path
sys.path.insert(0,"scripts")
from projection_v4_backtest import project, score
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.parquet"
w=pd.read_parquet(URL)
w=w[(w.season_type=="REG")&w.week.between(1,5)&w.position.isin(["QB","RB","WR","TE"])].copy()
if "recent_team" not in w:w["recent_team"]=w["team"]
cols=["attempts","completions","passing_yards","passing_tds","interceptions","carries","rushing_yards","rushing_tds","targets","receptions","receiving_yards","receiving_tds"]
if "interceptions" not in w and "passing_interceptions" in w: w["interceptions"]=w["passing_interceptions"]
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
last=last.merge(team[team.week==5][["recent_team","pre_team_pass","pre_team_carries"]],on="recent_team",how="left")
last["week"]=6
# Select meaningful prior usage, no Week 6 outcome leakage.
last["prior_opp"]=last.pre_attempts.fillna(0)+last.pre_carries.fillna(0)+last.pre_targets.fillna(0)*1.5
games=[("HOU","JAX"),("TEN","IND"),("CAR","PHI"),("PIT","TB"),("BAL","CLE"),("NO","NYG"),("CHI","ATL"),("NYJ","NE"),("ARI","LA"),("LAC","KC"),("BUF","LV"),("DAL","GB"),("WAS","SF")]
opponents={a:b for a,b in games};opponents.update({b:a for a,b in games})
last=last[last.recent_team.isin(opponents)].copy()
last=last[last.prior_opp>=1].copy()
# Consistent low-usage role gate. Weekly player stats do not include snap shares;
# use observed opportunities, never label this as a measured snap percentage.
recent_usage=w[w.week.between(3,5)].copy()
recent_usage["opportunities"]=recent_usage.carries+recent_usage.targets+recent_usage.attempts
role=recent_usage.groupby("player_id").agg(
 role_games=("week","nunique"),
 role_opportunities=("opportunities","sum"),
 role_active_weeks=("opportunities",lambda x:int((x>=3).sum())),
 role_targets=("targets","sum"),
 role_carries=("carries","sum")
).reset_index()
last=last.merge(role,on="player_id",how="left")
# Players with a consistently tiny role should not accumulate substantial
# projections simply from team volume scaling. Preserve newly elevated roles
# only when at least one recent week shows meaningful opportunity.
fringe=(last.position.ne("QB") & last.role_games.ge(2)
        & last.role_opportunities.le(6)
        & last.role_active_weeks.eq(0))
last=last[~fringe].copy()

# Actual PFR offensive snap share, Weeks 3-5 (nflverse).
# Fail closed if the dataset/schema is unavailable rather than silently reverting
# to opportunities-only and mislabeling the output as snap-validated.
snap_url="https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_2026.parquet"
snaps=pd.read_parquet(snap_url)
required={"season","week","team","player","offense_pct","offense_snaps"}
missing=required-set(snaps.columns)
if missing:raise RuntimeError(f"Snap data missing required columns: {sorted(missing)}")
snaps=snaps[(snaps.season==2026)&snaps.week.between(3,5)].copy()
snaps["offense_pct"]=pd.to_numeric(snaps.offense_pct,errors="coerce")
snaps["offense_snaps"]=pd.to_numeric(snaps.offense_snaps,errors="coerce")
# PFR uses percentage units 0-100; convert only if needed.
if snaps.offense_pct.dropna().median()>1:snaps["offense_pct"]/=100
snaps["snap_name"]=snaps.player.astype(str).str.lower().str.replace(r"[^a-z0-9]","",regex=True)
last["snap_name"]=last.player_display_name.astype(str).str.lower().str.replace(r"[^a-z0-9]","",regex=True)
# Resolve common source naming differences before matching.
# Prefer team-constrained exact matches; never match on surname alone.
aliases={
 "ajbrown":"ajbrown","brianthomasjr":"brianthomas",
 "deebosamuelsr":"deebosamuel","michaelpenixjr":"michaelpenix",
 "haroldfanninjr":"haroldfannin","brianrobinson":"brianrobinsonjr",
 "olliegordonii":"olliegordon","chrisrodriguezjr":"chrisrodriguez",
 "marvinmimsjr":"marvinmims","michaelpittman":"michaelpittmanjr",
 "jord mason":"jordanmason"
}
# Only apply an alias when the corresponding team/player actually exists
# in the snap dataset; otherwise leave the record visibly unmatched.
snap_keys=set(zip(snaps.team,snaps.snap_name))
for idx in last.index:
 key=last.at[idx,"snap_name"];team_code=last.at[idx,"recent_team"]
 candidate=aliases.get(key)
 if candidate and (team_code,candidate) in snap_keys:
  last.at[idx,"snap_name"]=candidate
snaps=snaps[snaps.offense_pct.between(0,1)]
snap_role=snaps.groupby(["team","snap_name"]).agg(
 snap_games=("week","nunique"),
 avg_snap_share=("offense_pct","mean"),
 recent_snap_share=("offense_pct","last"),
 snap_max=("offense_pct","max")
).reset_index().rename(columns={"team":"recent_team"})
last=last.merge(snap_role,on=["recent_team","snap_name"],how="left",validate="many_to_one")
# Only filter genuinely consistent low participation, not new breakout roles.
# Require 2+ observed games and no recent game above 20% snaps.
tiny=(last.position.ne("QB") & last.snap_games.ge(2) &
      last.avg_snap_share.lt(.15) & last.snap_max.lt(.20))
last=last[~tiny].copy()
# Do not let unmapped players quietly receive a high-volume projection.
last["Snap_Share_3W"]=last.avg_snap_share
last["Snap_Games"]=last.snap_games
# Explicitly mark unmatched snap records for auditing; do not treat as zero snaps.
last["Snap_Data_Status"]=np.where(last.avg_snap_share.notna(),"matched","unmatched")
print("Snap-share coverage:",int(last.avg_snap_share.notna().sum()),"/",len(last))

# Week 6 confirmed outs as of Oct 17; questionable players retained.
# Sunday inactive lists will require a final pre-kickoff update.
inactive_players=("Lamar Jackson","David Montgomery","Tank Dell","Kyle Monangai")
last=last[~last.player_display_name.isin(inactive_players)].copy()

last=last.sort_values("prior_opp",ascending=False)
# Keep the primary Week 5 quarterback for each team.
q5=w[w.position=="QB"].sort_values(["week","attempts"],ascending=[False,False])
starter_ids=set(q5.drop_duplicates("recent_team").player_id)
# Confirmed Week 6 replacement starters from NFL team reports.
for name in ("Tyler Huntley","Caleb Williams"):
 ids=set(w.loc[w.player_display_name.eq(name),"player_id"])
 starter_ids.update(ids)
starter_ids.difference_update(set(w.loc[w.player_display_name.eq("Lamar Jackson"),"player_id"]))
# Exclude secondary quarterbacks after accounting for replacement starters.
starter_ids.discard(next(iter(set(w.loc[w.player_display_name.eq("Athan Kaliakmanis"),"player_id"])),None))
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
# Constrain projected team RB workload to historical team carries.
# Avoid allocating all missing quarterback carries to one running back.
for t in opponents:
 m=(last.recent_team==t)&last.position.eq("RB")
 if not m.any():continue
 hist=last.loc[m,"pre_team_carries"].dropna()
 if hist.empty:continue
 budget=float(hist.iloc[0])
 total=float(last.loc[m,"pred_carries"].sum())
 if total>budget and total>0:
  ratio=budget/total
  for f in ("pred_carries","pred_rush_yds","pred_rush_td"):
   last.loc[m,f]*=ratio
# Reallocate backfield carries using actual Weeks 3-5 RB carry shares.
# Apply AFTER team-volume normalization so lead-back usage is not erased.
for team in opponents:
 backs=(last.recent_team==team)&last.position.eq("RB")
 recent=w[(w.recent_team==team)&w.week.between(3,5)&w.position.eq("RB")]
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
# Bound implausible individual RB volume after team-share reallocation.
for idx in last.index[last.position.eq("RB")]:
 volume=float(last.at[idx,"pred_carries"])
 if volume>25:
  factor=25/volume
  for field in ("pred_carries","pred_rush_yds","pred_rush_td"):
   last.at[idx,field]*=factor
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
out.to_csv("data/projections/2026_week6_league_v4_touchdowns.csv",index=False)
full=last[["Player","Team","Opponent","Position","Pass_Att","Pass_Yds","Pass_TD","INT","Rush_Att","Rush_Yds","Rush_TD","Targets","Receptions","Rec_Yds","Rec_TD","Total_xTD","Standard","Half_PPR","PPR","Snap_Share_3W","Snap_Games","Snap_Data_Status"]].copy()
full=full.sort_values(["Position","PPR"],ascending=[True,False]).round(2)
full.to_csv("data/projections/2026_week6_league_v4_full.csv",index=False)
assert len(full)>=150, f"Unusually low Week 6 coverage: {len(full)}"
assert not full.PPR.isna().any(), "Missing projected points"
assert not full.Team.isin(["SEA","DEN"]).any(), "Completed Thursday teams must not be published"
print("Full projections:",len(full),"players")
print(out.head(30).to_string(index=False))
