#!/usr/bin/env python3
import json,re,unicodedata
from pathlib import Path
import pandas as pd, numpy as np
STATS="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2026.csv"
PBP="https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet"
SCHED="https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
# Week 3 2026 official NFL schedule cross-check. Kept projection-only.
EXPECTED_WEEK3={"ATL":"GB","GB":"ATL","LAC":"BUF","BUF":"LAC","CAR":"CLE","CLE":"CAR","NYJ":"DET","DET":"NYJ","HOU":"IND","IND":"HOU","NE":"JAX","JAX":"NE","KC":"MIA","MIA":"KC","TEN":"NYG","NYG":"TEN","CIN":"PIT","PIT":"CIN","SEA":"WAS","WAS":"SEA","TB":"NO","NO":"TB","LV":"DEN","DEN":"LV","DAL":"BAL","BAL":"DAL","SF":"ARI","ARI":"SF","LAR":"MIN","MIN":"LAR","PHI":"CHI","CHI":"PHI"}
def key(v):
 v=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
 return re.sub(r"[^a-z0-9]","",re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",v))
def n(r,c):
 try:return max(0.,float(r.get(c,0) or 0))
 except:return 0.
# Current 2026 RB production.
stats=pd.read_csv(STATS,low_memory=False);stats=stats[stats.position.eq("RB")].copy();stats["k"]=stats.player_display_name.map(key)
# Current defense from 2026 PBP: run EPA/success/YPC/explosives, RB receiving,
# and red-zone rushing TD rate. Blend 65% current / 35% neutral because Week 3
# is still a small defensive sample.
cols=["season_type","posteam","defteam","play_type","rush_attempt","pass_attempt","yards_gained","epa","success","touchdown","yardline_100","receiver_player_id","receiving_yards"]
try:
 pbp=pd.read_parquet(PBP,columns=cols)
except Exception as e:
 print("Defense PBP column subset unavailable; loading full 2026 PBP:",e)
 pbp=pd.read_parquet(PBP)
pbp=pbp[pbp.season_type.eq("REG")].copy()
rush=pbp[pd.to_numeric(pbp.rush_attempt,errors="coerce").fillna(0).eq(1)].copy()
rush["explosive"]=(pd.to_numeric(rush.yards_gained,errors="coerce").fillna(0)>=10).astype(float)
rush["rz"]=(pd.to_numeric(rush.yardline_100,errors="coerce")<=20).fillna(False)
rush["rztd"]=((pd.to_numeric(rush.touchdown,errors="coerce").fillna(0)==1)&rush.rz).astype(float)
dg=rush.groupby("defteam").agg(run_epa=("epa","mean"),run_success=("success","mean"),ypc=("yards_gained","mean"),explosive=("explosive","mean"),rztd=("rztd","mean")).reset_index()
# nflverse PBP does not expose receiver_position directly. Join receiver IDs to
# the current player table so RB receiving defense is still measured accurately.
idpos=dict(zip(stats.player_id.astype(str),stats.position)) if "player_id" in stats.columns else {}
pbp["receiver_position"]=pbp.receiver_player_id.astype(str).map(idpos)
rbrec=pbp[(pbp.play_type.eq("pass"))&(pbp.receiver_position.eq("RB"))].groupby("defteam").agg(rb_rec_yards=("receiving_yards","sum"),rb_targets=("pass_attempt","sum")).reset_index()
dg=dg.merge(rbrec,on="defteam",how="left");dg["rb_rec_ypt"]=dg.rb_rec_yards/dg.rb_targets.replace(0,np.nan)
metrics=["run_epa","run_success","ypc","explosive","rztd","rb_rec_ypt"]
for m in metrics:
 s=pd.to_numeric(dg[m],errors="coerce");dg[m+"_badpct"]=s.rank(pct=True).fillna(.5)
dg["def_bad"]=dg[[m+"_badpct" for m in metrics]].mean(axis=1)
dg["matchup_mult"]=.35+(.65*(.88+.24*dg.def_bad))
defmap=dict(zip(dg.defteam,dg.matchup_mult))
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
db=json.loads(Path("players.json").read_text())["half"];ranked={key(p["name"]):p for p in db if p["pos"]=="RB"};rows=[];projected=set()
for _,r in stats.iterrows():
 k=r.k
 if k not in ranked or n(r,"games")<1:continue
 p=ranked[k];projected.add(k);g=max(1.,n(r,"games"));c=n(r,"carries")/g;t=n(r,"targets")/g;rec=n(r,"receptions")/g
 ypc=n(r,"rushing_yards")/max(1.,n(r,"carries"));ypr=n(r,"receiving_yards")/max(1.,n(r,"receptions"));td=(n(r,"rushing_tds")+n(r,"receiving_tds"))/g
 strength=max(.65,min(1.20,float(p["analyticsScore"])/75.));value=max(.72,min(1.16,float(p["value"])/80.))
 # Two games of usage should inform the projection, not become the projection.
 # Regress volume toward a rank-derived role baseline, with current usage at 60%.
 role_carries=max(6.0,min(19.0,20.0-(min(60,int(p["posRank"]))-1)*0.30))
 role_targets=max(1.5,min(6.5,6.2-(min(60,int(p["posRank"]))-1)*0.09))
 cp=.60*c+.40*role_carries;tp=.60*t+.40*role_targets
 # Efficiency is also regressed to sustainable RB baselines.
 adj_ypc=.55*ypc+.45*4.35;adj_ypr=.55*ypr+.45*7.5
 ry=cp*max(3.5,min(5.8,adj_ypc*(.88+.07*strength+.05*value)))
 catch_rate=(rec/max(.1,t)) if t>0 else .65
 adj_catch=.65*catch_rate+.35*.72;rp=min(tp,tp*max(.50,min(.88,adj_catch)))
 rey=rp*max(5.5,min(10.5,adj_ypr*(.90+.05*strength+.05*value)))
 # TD expectation: observed scoring is noisy, so combine current TD/game with
 # rank/role and projected opportunity. This avoids a pile-up at a hard ceiling.
 role_td=max(.12,min(.72,.74-(min(60,int(p["posRank"]))-1)*.0105))
 opportunity_td=max(.10,min(.78,.018*cp+.010*tp))
 tdp=max(.06,min(.88,.25*td+.45*role_td+.30*opportunity_td))
 base=ry/10+rey/10+rp*.5+tdp*6
 player_team=team(p["team"]);opponent=opp.get(player_team)
 if not opponent:
  print(f"WARNING: no upcoming opponent mapped for {p['name']} ({p['team']})")
 mm=float(defmap.get(opponent,1.0));weekly=base*mm
 # Apply each remaining opponent separately for ROS instead of extrapolating
 # the next matchup. Bye weeks naturally disappear because they are not games.
 remaining_opps=schedule_by_team.get(player_team,[])
 ros_mults=[float(defmap.get(o,1.0)) for o in remaining_opps]
 ros_points=sum(base*m for m in ros_mults)
 left=len(remaining_opps)
 ros_ppg=(ros_points/left) if left else 0.0
 rows.append({"rank":p["posRank"],"player":p["name"],"team":p["team"],"opponent":opponent,"defenseMultiplier":round(mm,3),"carries":round(cp,1),"targets":round(tp,1),"receptions":round(rp,1),"rushYds":round(ry,1),"recYds":round(rey,1),"TD":round(tdp,2),"baselineHalfPPR":round(base,1),"weeklyStandard":round((ry/10+rey/10+tdp*6)*mm,1),"weeklyHalfPPR":round(weekly,1),"weeklyPPR":round((ry/10+rey/10+rp+tdp*6)*mm,1),"ROSgames":left,"ROSScheduleMultiplier":round(sum(ros_mults)/left,3) if left else 1.0,"ROSHalfPPRperGame":round(ros_ppg,1),"ROSpoints":round(ros_points,1)})
# Every ranked RB gets a projection. If current nflverse stats are unavailable,
# use the locked ranking/role baseline rather than silently dropping the player.
for k,p in ranked.items():
 if k in projected: continue
 pr=min(60,int(p["posRank"]));strength=max(.65,min(1.20,float(p["analyticsScore"])/75.));value=max(.72,min(1.16,float(p["value"])/80.))
 cp=max(6.0,min(19.0,20.0-(pr-1)*0.30));tp=max(1.5,min(6.5,6.2-(pr-1)*0.09))
 ry=cp*4.35*(.88+.07*strength+.05*value);rp=tp*.72;rey=rp*7.5*(.90+.05*strength+.05*value)
 role_td=max(.12,min(.72,.74-(pr-1)*.0105));opportunity_td=max(.10,min(.78,.018*cp+.010*tp));tdp=max(.06,min(.88,.70*role_td+.30*opportunity_td))
 base=ry/10+rey/10+rp*.5+tdp*6;player_team=team(p["team"]);opponent=opp.get(player_team);mm=float(defmap.get(opponent,1.0));weekly=base*mm
 remaining_opps=schedule_by_team.get(player_team,[]);ros_mults=[float(defmap.get(o,1.0)) for o in remaining_opps];left=len(remaining_opps);ros_points=sum(base*m for m in ros_mults);ros_ppg=ros_points/left if left else 0.0
 rows.append({"rank":p["posRank"],"player":p["name"],"team":p["team"],"opponent":opponent,"defenseMultiplier":round(mm,3),"carries":round(cp,1),"targets":round(tp,1),"receptions":round(rp,1),"rushYds":round(ry,1),"recYds":round(rey,1),"TD":round(tdp,2),"baselineHalfPPR":round(base,1),"weeklyHalfPPR":round(weekly,1),"ROSgames":left,"ROSScheduleMultiplier":round(sum(ros_mults)/left,3) if left else 1.0,"ROSHalfPPRperGame":round(ros_ppg,1),"ROSpoints":round(ros_points,1),"projectionSource":"ranking-role fallback"})
rows.sort(key=lambda x:x["weeklyHalfPPR"],reverse=True)
Path("data/new-rb-projection-preview.json").write_text(json.dumps(rows,indent=2))
print(json.dumps(rows[:25],indent=2))
