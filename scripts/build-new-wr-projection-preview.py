#!/usr/bin/env python3
import json,re,unicodedata
from pathlib import Path
import pandas as pd, numpy as np
STATS="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2026.csv"
PBP="https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet"
SCHED="https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
EXPECTED_WEEK3={"ATL":"GB","GB":"ATL","LAC":"BUF","BUF":"LAC","CAR":"CLE","CLE":"CAR","NYJ":"DET","DET":"NYJ","HOU":"IND","IND":"HOU","NE":"JAX","JAX":"NE","KC":"MIA","MIA":"KC","TEN":"NYG","NYG":"TEN","CIN":"PIT","PIT":"CIN","SEA":"WAS","WAS":"SEA","TB":"NO","NO":"TB","LV":"DEN","DEN":"LV","DAL":"BAL","BAL":"DAL","SF":"ARI","ARI":"SF","LAR":"MIN","MIN":"LAR","PHI":"CHI","CHI":"PHI"}
def key(v):
 v=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
 return re.sub(r"[^a-z0-9]","",re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",v))
def n(r,c):
 try:return max(0.,float(r.get(c,0) or 0))
 except:return 0.
stats=pd.read_csv(STATS,low_memory=False);stats=stats[stats.position.eq("WR")].copy();stats["k"]=stats.player_display_name.map(key)
cols=["season_type","posteam","defteam","play_type","pass_attempt","complete_pass","yards_gained","epa","success","touchdown","yardline_100","receiver_player_id","receiving_yards"]
try: pbp=pd.read_parquet(PBP,columns=cols)
except Exception: pbp=pd.read_parquet(PBP)
pbp=pbp[pbp.season_type.eq("REG")].copy();pas=pbp[pd.to_numeric(pbp.pass_attempt,errors="coerce").fillna(0).eq(1)].copy()
pas["explosive"]=((pd.to_numeric(pas.complete_pass,errors="coerce").fillna(0)==1)&(pd.to_numeric(pas.yards_gained,errors="coerce").fillna(0)>=20)).astype(float)
pas["rz"]=(pd.to_numeric(pas.yardline_100,errors="coerce")<=20).fillna(False);pas["rztd"]=((pd.to_numeric(pas.touchdown,errors="coerce").fillna(0)==1)&pas.rz).astype(float)
dg=pas.groupby("defteam").agg(pass_epa=("epa","mean"),pass_success=("success","mean"),explosive=("explosive","mean"),rztd=("rztd","mean")).reset_index()
idpos=dict(zip(stats.player_id.astype(str),stats.position)) if "player_id" in stats.columns else {};pbp["receiver_position"]=pbp.receiver_player_id.astype(str).map(idpos)
wr=pbp[(pbp.play_type.eq("pass"))&(pbp.receiver_position.eq("WR"))].groupby("defteam").agg(wr_yards=("receiving_yards","sum"),wr_targets=("pass_attempt","sum")).reset_index()
dg=dg.merge(wr,on="defteam",how="left");dg["wr_ypt"]=dg.wr_yards/dg.wr_targets.replace(0,np.nan)
metrics=["pass_epa","pass_success","explosive","rztd","wr_ypt"]
for m in metrics:
 s=pd.to_numeric(dg[m],errors="coerce");dg[m+"_badpct"]=s.rank(pct=True).fillna(.5)
dg["def_bad"]=dg[[m+"_badpct" for m in metrics]].mean(axis=1);dg["matchup_mult"]=.35+(.65*(.88+.24*dg.def_bad));defmap=dict(zip(dg.defteam,dg.matchup_mult))
# Upcoming opponent.
sch=pd.read_csv(SCHED,low_memory=False)
played = sch["result"].notna() if "result" in sch.columns else sch["home_score"].notna()
future=sch[(sch.season.eq(2026))&(~played)].sort_values("week")
# IMPORTANT: "this week" must mean the league's next chronological week,
# not each team's first unplayed game. This prevents stale/postponed rows or
# schedule quirks from assigning different NFL weeks to different players.
next_week=int(future["week"].min())
this_week=future[future["week"].eq(next_week)].copy()
# Normalize the few common abbreviation variants before matching rankings,
# schedules and nflverse defensive PBP.
TEAM_ALIAS={"LA":"LAR","JAC":"JAX","WSH":"WAS"}
def team(v):
 v=str(v or "").strip().upper()
 return TEAM_ALIAS.get(v,v)
# Use the verified official Week 3 slate as the authoritative weekly schedule.
# The nflverse schedule remains the source for the full remaining ROS schedule.
if next_week == 3:
 opp=dict(EXPECTED_WEEK3)
else:
 opp={}
 for _,gm in this_week.iterrows():
  h,a=team(gm.home_team),team(gm.away_team)
  opp[h]=a;opp[a]=h
schedule_by_team={}
for _,gm in future.iterrows():
 h,a=team(gm.home_team),team(gm.away_team)
 schedule_by_team.setdefault(h,[]).append(a)
 schedule_by_team.setdefault(a,[]).append(h)
print(f"Projection week: {next_week}; mapped teams: {len(opp)}")
if len(opp) != 32:
 raise SystemExit(f"Expected 32 team opponent mappings for Week {next_week}, got {len(opp)}")
# Normalize defensive keys too, so every mapped opponent can receive its defense.
defmap={team(k):v for k,v in defmap.items()}

defmap={team(k):v for k,v in defmap.items()}
db=json.loads(Path("players.json").read_text())["half"];ranked={key(p["name"]):p for p in db if p["pos"]=="WR"};rows=[];projected=set()
def emit(p,t,rec,ypr,td,source):
 pr=min(100,int(p["posRank"]));strength=max(.65,min(1.20,float(p["analyticsScore"])/75.));value=max(.72,min(1.16,float(p["value"])/80.));role_targets=max(2.,min(10.5,10.5-(pr-1)*.09));tp=.62*t+.38*role_targets if source!="ranking-role fallback" else role_targets
 catch=(rec/max(.1,t)) if t>0 else .65;rp=tp*max(.45,min(.82,.65*catch+.35*.65));adj_ypr=.58*ypr+.42*12.;rey=rp*max(8.,min(17.,adj_ypr*(.90+.06*strength+.04*value)))
 role_td=max(.08,min(.62,.62-(pr-1)*.006));opp_td=max(.06,min(.65,.025*tp+.008*rey));tdp=max(.04,min(.78,.25*td+.45*role_td+.30*opp_td));base=rey/10+rp*.5+tdp*6
 pt=team(p["team"]);opponent=opp.get(pt);mm=float(defmap.get(opponent,1.0));weekly=base*mm;ros_opps=schedule_by_team.get(pt,[]);mults=[float(defmap.get(o,1.0)) for o in ros_opps];left=len(ros_opps);ros=sum(base*m for m in mults);ppg=ros/left if left else 0
 rows.append({"rank":p["posRank"],"player":p["name"],"team":p["team"],"opponent":opponent,"defenseMultiplier":round(mm,3),"targets":round(tp,1),"receptions":round(rp,1),"recYds":round(rey,1),"TD":round(tdp,2),"baselineHalfPPR":round(base,1),"weeklyHalfPPR":round(weekly,1),"ROSgames":left,"ROSScheduleMultiplier":round(sum(mults)/left,3) if left else 1.0,"ROSHalfPPRperGame":round(ppg,1),"ROSpoints":round(ros,1),"projectionSource":source})
for _,r in stats.iterrows():
 k=r["k"]
 if k not in ranked: continue
 projected.add(k);g=max(1.,n(r,"games"));emit(ranked[k],n(r,"targets")/g,n(r,"receptions")/g,n(r,"receiving_yards")/max(1.,n(r,"receptions")),n(r,"receiving_tds")/g,"2026 production + ranking role")
for k,p in ranked.items():
 if k not in projected: emit(p,0,0,12,0,"ranking-role fallback")
rows.sort(key=lambda x:x["weeklyHalfPPR"],reverse=True)
Path("data/new-wr-projection-preview.json").write_text(json.dumps(rows,indent=2));print(json.dumps(rows[:25],indent=2))
