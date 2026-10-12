#!/usr/bin/env python3
"""Evaluate locked Week 5 predictions against finished Week 5 games only."""
import pandas as pd
from pathlib import Path
pred=pd.read_csv("data/projections/2026_week5_league_v4_full.csv")
url="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.parquet"
actual=pd.read_parquet(url)
actual=actual[(actual.week==5)&(actual.season_type=="REG")].copy()
# Finished games only; derive from official nflverse schedules.
schedule=pd.read_csv("https://github.com/nflverse/nfldata/raw/master/data/games.csv")
done=schedule[(schedule.season==2026)&(schedule.week==5)&schedule.home_score.notna()&schedule.away_score.notna()]
teams=set(done.home_team)|set(done.away_team)
if not teams: raise RuntimeError("No finished Week 5 games available from schedule; refusing empty audit")
pred=pred[pred.Team.isin(teams)].copy()
team_col="recent_team" if "recent_team" in actual.columns else "team"
if team_col not in actual.columns: raise RuntimeError("Weekly stats have no team column")
actual["join_name"]=actual.player_display_name.astype(str).str.lower().str.replace(r"[^a-z0-9]","",regex=True)
pred["join_name"]=pred.Player.astype(str).str.lower().str.replace(r"[^a-z0-9]","",regex=True)
actual=actual.sort_values("player_id").drop_duplicates([team_col,"join_name"])
df=pred.merge(actual,how="left",left_on=["Team","join_name"],right_on=[team_col,"join_name"],indicator=True,suffixes=("","_actual"))
stats={"Pass_Yds":"passing_yards","Pass_TD":"passing_tds","INT":"interceptions","Rush_Yds":"rushing_yards","Rush_TD":"rushing_tds","Rec_Yds":"receiving_yards","Rec_TD":"receiving_tds","Receptions":"receptions"}
for key,source in stats.items():df["actual_"+key]=pd.to_numeric(df[source],errors="coerce").fillna(0)
# Apply standard 4-point passing TD fantasy rules.
df["Actual_PPR"]=df.actual_Pass_Yds*.04+df.actual_Pass_TD*4-df.actual_INT*2+df.actual_Rush_Yds*.1+df.actual_Rush_TD*6+df.actual_Rec_Yds*.1+df.actual_Rec_TD*6+df.actual_Receptions
df["Error"]=df.PPR-df.Actual_PPR
# Players absent from weekly data can have zero stats, but only if team played.
df["absent_from_stats"]=df._merge.ne("both")
rows=[]
for pos,g in df.groupby("Position"):
 err=g.Error.abs()
 rows.append({"Position":pos,"Players":len(g),"MAE":round(err.mean(),3),"Within_1":int((err<=1).sum()),"Within_3":int((err<=3).sum()),"Within_5":int((err<=5).sum()),"Pct_Within_1":round(100*(err<=1).mean(),1),"Pct_Within_3":round(100*(err<=3).mean(),1),"Pct_Within_5":round(100*(err<=5).mean(),1),"Missing_Stats":int(g.absent_from_stats.sum())})
out=Path("data/projections");out.mkdir(parents=True,exist_ok=True)
pd.DataFrame(rows).sort_values("Position").to_csv(out/"2026_week5_v4_audit_summary.csv",index=False)
df[["Player","Team","Position","PPR","Actual_PPR","Error","absent_from_stats"]].to_csv(out/"2026_week5_v4_audit_players.csv",index=False)
print("FINISHED_GAMES",len(done),"PROJECTED_PLAYERS",len(df))
print(pd.DataFrame(rows).to_string(index=False))
