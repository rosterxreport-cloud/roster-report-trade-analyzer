#!/usr/bin/env python3
import json,re,unicodedata
from pathlib import Path
import pandas as pd, numpy as np
STATS="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2026.csv"
PBP="https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet"
SCHED="https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
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
opp={}
for _,g in future.iterrows():
 opp.setdefault(str(g.home_team),str(g.away_team));opp.setdefault(str(g.away_team),str(g.home_team))
db=json.loads(Path("players.json").read_text())["half"];ranked={key(p["name"]):p for p in db if p["pos"]=="RB"};rows=[]
for _,r in stats.iterrows():
 k=r.k
 if k not in ranked or n(r,"games")<1:continue
 p=ranked[k];g=max(1.,n(r,"games"));c=n(r,"carries")/g;t=n(r,"targets")/g;rec=n(r,"receptions")/g
 ypc=n(r,"rushing_yards")/max(1.,n(r,"carries"));ypr=n(r,"receiving_yards")/max(1.,n(r,"receptions"));td=(n(r,"rushing_tds")+n(r,"receiving_tds"))/g
 strength=max(.65,min(1.20,float(p["analyticsScore"])/75.));value=max(.72,min(1.16,float(p["value"])/80.))
 cp=c*(.72+.18*strength+.10*value);tp=t*(.72+.18*strength+.10*value)
 ry=cp*max(3.2,min(6.2,ypc*(.82+.10*strength+.08*value)));rp=min(tp,rec*(.78+.12*strength+.10*value))
 rey=rp*max(5.,min(12.,ypr*(.84+.08*strength+.08*value)));tdp=max(.05,min(1.25,td*(.70+.18*strength+.12*value)))
 base=ry/10+rey/10+rp*.5+tdp*6
 opponent=opp.get(p["team"]);mm=float(defmap.get(opponent,1.0));weekly=base*mm
 # ROS keeps the player baseline; schedule-level ROS adjustment comes next,
 # rather than incorrectly applying one opponent to the whole season.
 left=max(0,17-int(g))
 rows.append({"rank":p["posRank"],"player":p["name"],"team":p["team"],"opponent":opponent,"defenseMultiplier":round(mm,3),"carries":round(cp,1),"targets":round(tp,1),"receptions":round(rp,1),"rushYds":round(ry,1),"recYds":round(rey,1),"TD":round(tdp,2),"baselineHalfPPR":round(base,1),"weeklyHalfPPR":round(weekly,1),"ROSgames":left,"ROSpointsBaseline":round(base*left,1)})
rows.sort(key=lambda x:x["weeklyHalfPPR"],reverse=True)
Path("data/new-rb-projection-preview.json").write_text(json.dumps(rows,indent=2))
print(json.dumps(rows[:25],indent=2))
