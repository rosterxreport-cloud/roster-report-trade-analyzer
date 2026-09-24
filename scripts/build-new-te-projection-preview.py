#!/usr/bin/env python3
import json,re,unicodedata
from pathlib import Path
import pandas as pd,numpy as np
STATS="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2026.csv"
PBP="https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet"
PBP25="https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.parquet"
SCHED="https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
EXPECTED={"ATL":"GB","GB":"ATL","LAC":"BUF","BUF":"LAC","CAR":"CLE","CLE":"CAR","NYJ":"DET","DET":"NYJ","HOU":"IND","IND":"HOU","NE":"JAX","JAX":"NE","KC":"MIA","MIA":"KC","TEN":"NYG","NYG":"TEN","CIN":"PIT","PIT":"CIN","SEA":"WAS","WAS":"SEA","MIN":"TB","TB":"MIN","LV":"NO","NO":"LV","DAL":"BAL","BAL":"DAL","SF":"ARI","ARI":"SF","LAR":"DEN","DEN":"LAR","PHI":"CHI","CHI":"PHI"}
def key(v):
 v=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
 return re.sub(r"[^a-z0-9]","",re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",v))
def team(v): return {"LA":"LAR","JAC":"JAX","WSH":"WAS"}.get(str(v or "").strip().upper(),str(v or "").strip().upper())
stats=pd.read_csv(STATS,low_memory=False);stats=stats[stats.position.eq("TE")].copy();stats["k"]=stats.player_display_name.map(key)
db=json.loads(Path("players.json").read_text())["half"];ranked={key(p["name"]):p for p in db if p["pos"]=="TE"}
inj={}
try: inj=json.loads(Path("injury-adjustments.json").read_text()).get("players",{})
except: pass
def availability(name):
 x=inj.get(name,inj.get(key(name),{}));s=str(x.get("status","ACTIVE")).upper();a=float(x.get("availability",1) or 0);w=float(x.get("workload",1) or 0)
 if any(z in s for z in ["IR ","IR -","INJURED RESERVE","PUP","NFI","OUT ","INACTIVE","UNAVAILABLE"]): return 0.,s
 if "DOUBTFUL" in s:return min(.25,a*w),s
 return max(0.,min(1.,a*w)),s
# Official Week 3 known TE overrides; automatic injury file remains primary.
MANUAL={"oscardelp":(0.0,"OUT - HAMSTRING"),"charliekolar":(0.0,"OUT - FOREARM"),"davidnjoku":(0.0,"IR")}
cols=["game_id","season_type","posteam","defteam","pass_attempt","complete_pass","yardline_100","receiver_player_id","receiving_yards","air_yards"]
pbp=pd.read_parquet(PBP,columns=cols);pbp=pbp[pbp.season_type.eq("REG")].copy()
# Team passing volume
pa=pbp[pbp.pass_attempt.fillna(0).eq(1)];games=pa.groupby("posteam").game_id.nunique();atts=pa.groupby("posteam").pass_attempt.sum();team_pa={team(t):float(atts[t])/max(1,float(games[t])) for t in atts.index}
# TE-specific defense using receiver IDs mapped from player stats.
idpos=dict(zip(stats.player_id.astype(str),stats.position));pbp["rpos"]=pbp.receiver_player_id.astype(str).map(idpos)
te=pbp[pbp.rpos.eq("TE")].groupby("defteam").agg(yards=("receiving_yards","sum"),targets=("pass_attempt","sum")).reset_index();te["ypt"]=te.yards/te.targets.replace(0,np.nan)
te["bad"]=te.ypt.rank(pct=True).fillna(.5);defmap={team(r.defteam):.90+.20*float(r.bad) for _,r in te.iterrows()}
# 2025+2026 scoring opportunity rates by player ID.
def opp(frame):
 x=frame[frame.receiver_player_id.notna()].copy();x["rz"]=(pd.to_numeric(x.yardline_100,errors="coerce")<=20).astype(float);x["ez"]=(pd.to_numeric(x.yardline_100,errors="coerce")<=10).astype(float)
 return x.groupby("receiver_player_id").agg(rz=("rz","sum"),ez=("ez","sum"),n=("receiver_player_id","count"))
try: p25=pd.read_parquet(PBP25,columns=cols);p25=p25[p25.season_type.eq("REG")];o25=opp(p25)
except: o25=pd.DataFrame()
o26=opp(pbp)
rows=[]
for _,r in stats.iterrows():
 k=r.k
 if k not in ranked: continue
 p=ranked[k];g=max(1.,float(r.get("games",0) or 0));tm=team(p["team"]);op=EXPECTED.get(tm)
 targets=float(r.get("targets",0) or 0)/g;rec=float(r.get("receptions",0) or 0)/g;yd=float(r.get("receiving_yards",0) or 0)/g;td=float(r.get("receiving_tds",0) or 0)/g
 share=float(r.get("target_share",np.nan));airshare=float(r.get("air_yards_share",np.nan));air=float(r.get("receiving_air_yards",0) or 0)/g
 adot=air/max(1.,targets);catch=rec/max(.1,targets);ypr=yd/max(.1,rec)
 pr=min(60,int(p["posRank"]));role_share=max(.08,min(.24,.235-(pr-1)*.003))
 share=role_share if pd.isna(share) else .45*share+.55*role_share
 tp=max(2.,min(10.,share*team_pa.get(tm,32.5)))
 cr=max(.52,min(.78,.45*catch+.55*.68));receptions=tp*cr
 role_ypr=max(8.5,min(12.5,11.8-(pr-1)*.045));pypr=.40*ypr+.60*role_ypr;yards=receptions*pypr
 pid=str(r.get("player_id",""));rz=ez=0.
 if pid in o26.index: rz=float(o26.loc[pid,"rz"])/g;ez=float(o26.loc[pid,"ez"])/g
 if not o25.empty and pid in o25.index:
  g25=max(1.,float(o25.loc[pid,"n"])/max(1,float(o25.loc[pid,"n"])/16));rz=.65*(float(o25.loc[pid,"rz"])/16)+.35*rz;ez=.65*(float(o25.loc[pid,"ez"])/16)+.35*ez
 role_td=max(.06,min(.45,.38-(pr-1)*.006));ptd=max(.04,min(.55,.25*td+.45*role_td+.20*rz*.12+.10*ez*.18))
 wf,status=MANUAL.get(k,availability(p["name"]));mm=float(defmap.get(op,1.0))
 std=(yards*.1+ptd*6)*mm*wf;half=std+receptions*.5*mm*wf;ppr=std+receptions*mm*wf
 rows.append({"player":p["name"],"team":p["team"],"opponent":op,"targets":round(tp,1),"receptions":round(receptions,1),"recYds":round(yards,1),"TD":round(ptd,2),"targetShare":round(share,3),"airYards":round(air,1),"airYardsShare":None if pd.isna(airshare) else round(float(airshare),3),"aDOT":round(adot,1),"rzTargets":round(rz,1),"endzoneTargets":round(ez,1),"defenseMultiplier":round(mm,3),"availabilityStatus":status,"weekAvailability":wf,"standard":round(std,1),"halfPPR":round(half,1),"fullPPR":round(ppr,1),"projectionSource":"2026 usage + 2025 scoring opportunity + role stabilization"})
rows.sort(key=lambda x:x["halfPPR"],reverse=True)
Path("data/new-te-projection-preview.json").write_text(json.dumps(rows,indent=2))
print(json.dumps(rows[:30],indent=2))
