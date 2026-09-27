#!/usr/bin/env python3
"""QB v4: v1 architecture + richer passing signal, zero sack-derived inputs."""
import pandas as pd,numpy as np
from pathlib import Path
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv"
d=pd.read_csv(URL,low_memory=False);d=d[(d.position=="QB")&(d.season_type=="REG")].copy()
d["actual"]=d.passing_yards/25+4*d.passing_tds-2*d.passing_interceptions+d.rushing_yards/10+6*d.rushing_tds
d["ypa"]=d.passing_yards/d.attempts.replace(0,np.nan);d["comp_rate"]=d.completions/d.attempts.replace(0,np.nan)
d["td_rate"]=d.passing_tds/d.attempts.replace(0,np.nan);d["int_rate"]=d.passing_interceptions/d.attempts.replace(0,np.nan)
def z(s):
 s=pd.to_numeric(s,errors="coerce");sd=s.std()
 return (s-s.mean())/(sd if pd.notna(sd) and sd else 1)
rows=[]
for wk in sorted(d.week.unique()):
 if wk<=2:continue
 h=d[d.week<wk];c=d[d.week==wk]
 feats=[]
 for pid,g in h.groupby("player_id"):
  g=g.sort_values("week");l3=g.tail(3)
  def avg(x): return g[x].mean()
  def a3(x): return l3[x].mean()
  feats.append(dict(player_id=pid,
   att=avg("attempts"),att3=a3("attempts"),rush=avg("carries"),rush3=a3("carries"),
   hist_ypa=avg("ypa"),cpoe=avg("passing_cpoe"),epa=avg("passing_epa"),cr=avg("comp_rate"),
   tdr=avg("td_rate"),intr=avg("int_rate"),py3=a3("passing_yards"),ptd3=a3("passing_tds"),
   fp3=a3("actual")))
 m=c.merge(pd.DataFrame(feats),on="player_id",how="inner")
 if len(m)<2:continue
 for x in ["att","att3","rush","rush3","hist_ypa","cpoe","epa","cr","tdr","intr","py3","ptd3","fp3"]:m[x+"z"]=z(m[x])
 m["pass_eff"]=(m.hist_ypaz+m.cpoez+m.epaz+m.crz)/4
 m["pass_prod"]=(m.py3z+m.ptd3z-m.intrz)/3
 for recent in [.25,.5,.75]:
  V=(1-recent)*m.attz+recent*m.att3z;R=(1-recent)*m.rushz+recent*m.rush3z
  for vw in [.25,.30,.35]:
   for rw in [.20,.25,.30]:
    for ew in [.10,.15,.20]:
     for pw in [.10,.15,.20,.25]:
      for fw in [.10,.15,.20,.25]:
       if vw+rw+ew+pw+fw>1.01:continue
       score=vw*V+rw*R+ew*m.pass_eff+pw*m.pass_prod+fw*m.fp3z
       base=h.actual.mean();scale=h.actual.std();pred=base+score*scale*.45
       for a,p in zip(m.actual,pred):rows.append((recent,vw,rw,ew,pw,fw,a,p))
o=pd.DataFrame(rows,columns=["recent","volume","rush","pass_eff","pass_prod","form","actual","pred"])
res=o.groupby(["recent","volume","rush","pass_eff","pass_prod","form"]).apply(lambda x:pd.Series({"n":len(x),"MAE":(x.pred-x.actual).abs().mean(),"RMSE":np.sqrt(((x.pred-x.actual)**2).mean()),"corr":x.pred.corr(x.actual),"bias":(x.pred-x.actual).mean()}),include_groups=False).reset_index().sort_values(["MAE","corr"],ascending=[True,False])
Path("data").mkdir(exist_ok=True);res.to_csv("data/qb-2025-v4-summary.csv",index=False);print(res.head(40).to_string(index=False))
