#!/usr/bin/env python3
import pandas as pd,numpy as np
from pathlib import Path
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv"
d=pd.read_csv(URL,low_memory=False);d=d[(d.position=="QB")&(d.season_type=="REG")].copy()
d["actual"]=d.passing_yards/25+4*d.passing_tds-2*d.passing_interceptions+d.rushing_yards/10+6*d.rushing_tds
def z(s):
 s=pd.to_numeric(s,errors="coerce"); sd=s.std()
 return (s-s.mean())/(sd if pd.notna(sd) and sd else 1)
rows=[]
for wk in sorted(d.week.unique()):
 if wk<=2: continue
 h=d[d.week<wk].copy(); c=d[d.week==wk].copy()
 feats=[]
 for pid,g in h.groupby("player_id"):
  g=g.sort_values("week"); last3=g.tail(3)
  feats.append(dict(player_id=pid,
   vol=g.attempts.mean(),vol3=last3.attempts.mean(),rush=g.carries.mean(),rush3=last3.carries.mean(),
   epa=g.passing_epa.mean(),cpoe=g.passing_cpoe.mean(),ypa=g.passing_yards.sum()/max(g.attempts.sum(),1),
   td_rate=g.passing_tds.sum()/max(g.attempts.sum(),1),fp3=last3.actual.mean()))
 m=c.merge(pd.DataFrame(feats),on="player_id",how="inner")
 if len(m)<2:continue
 for col in ["vol","vol3","rush","rush3","epa","cpoe","ypa","td_rate","fp3"]:m[col+"z"]=z(m[col])
 m["adv"]=(m.epaz+m.cpoez+m.ypaz)/3
 # broad architecture sweep, all based only on prior games
 for vw in [.25,.30,.35,.40,.45,.50]:
  for rw in [.15,.20,.25,.30]:
   for aw in [.10,.15,.20,.25,.30]:
    for fw in [0,.10,.20,.30]:
     if vw+rw+aw+fw>1:continue
     for recent in [0,.5,1]:
      V=(1-recent)*m.volz+recent*m.vol3z;R=(1-recent)*m.rushz+recent*m.rush3z
      score=vw*V+rw*R+aw*m.adv+fw*m.fp3z
      # historical calibration only
      scale=h.actual.std();base=h.actual.mean();pred=base+score*scale*.45
      for a,p in zip(m.actual,pred):rows.append((vw,rw,aw,fw,recent,a,p))
o=pd.DataFrame(rows,columns=["volume","rush","advanced","form","recent","actual","pred"])
res=o.groupby(["volume","rush","advanced","form","recent"]).apply(lambda x:pd.Series({"n":len(x),"MAE":(x.pred-x.actual).abs().mean(),"RMSE":np.sqrt(((x.pred-x.actual)**2).mean()),"corr":x.pred.corr(x.actual),"bias":(x.pred-x.actual).mean()}),include_groups=False).reset_index().sort_values(["MAE","corr"],ascending=[True,False])
Path("data").mkdir(exist_ok=True);res.to_csv("data/qb-2025-tuning-sweep.csv",index=False);print(res.head(30).to_string(index=False))
