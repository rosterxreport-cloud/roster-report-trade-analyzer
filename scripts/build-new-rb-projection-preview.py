#!/usr/bin/env python3
import json,re,unicodedata
from pathlib import Path
import pandas as pd
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2026.csv"
def key(v):
 v=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
 return re.sub(r"[^a-z0-9]","",re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",v))
def n(r,c):
 try:return max(0.,float(r.get(c,0) or 0))
 except:return 0.
stats=pd.read_csv(URL,low_memory=False);stats=stats[stats.position.eq("RB")].copy();stats["k"]=stats.player_display_name.map(key)
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
 half=ry/10+rey/10+rp*.5+tdp*6;left=max(0,17-int(g))
 rows.append({"rank":p["posRank"],"player":p["name"],"team":p["team"],"carries":round(cp,1),"targets":round(tp,1),"receptions":round(rp,1),"rushYds":round(ry,1),"recYds":round(rey,1),"TD":round(tdp,2),"halfPPR":round(half,1),"ROSgames":left,"ROSpoints":round(half*left,1)})
rows.sort(key=lambda x:x["halfPPR"],reverse=True);Path("data/new-rb-projection-preview.json").write_text(json.dumps(rows,indent=2)+"\n");print(json.dumps(rows[:25],indent=2))
