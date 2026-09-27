#!/usr/bin/env python3
"""QB v10 actual-data-only experiment.
RULE: no constructed proxies. Only directly observed fields in the source feeds.
No sack-derived data. No designed-run data.
Historical backtest uses nflverse direct fields only; Fantasy Points EZATT is reserved for
2026 forward/live testing because the user-provided exports are 2026 Week 1/2, not 2025.
"""
import pandas as pd,numpy as np,itertools
from pathlib import Path
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv"
d=pd.read_csv(URL,low_memory=False);d=d[(d.position=="QB")&(d.season_type=="REG")].copy()
d["actual"]=d.passing_yards/25+4*d.passing_tds-2*d.passing_interceptions+d.rushing_yards/10+6*d.rushing_tds
# Directly observed source columns only. Ratios calculated from observed numerator/denominator are allowed;
# synthetic substitutes for unavailable concepts are not.
d["ypa"]=d.passing_yards/d.attempts.replace(0,np.nan)
d["completion_rate"]=d.completions/d.attempts.replace(0,np.nan)
AVAILABLE=["attempts","passing_yards","passing_epa","passing_cpoe","ypa","completion_rate","carries","rushing_yards"]
def z(s):
 s=pd.to_numeric(s,errors="coerce");sd=s.std()
 return (s-s.mean())/(sd if pd.notna(sd) and sd else 1)
rows=[]
for wk in sorted(d.week.unique()):
 if wk<=2:continue
 h=d[d.week<wk];c=d[d.week==wk];fs=[]
 for pid,g in h.groupby("player_id"):
  g=g.sort_values("week");l3=g.tail(3)
  r={"player_id":pid,"fp3":l3.actual.mean()}
  for x in AVAILABLE:
   r[x+"_s"]=g[x].mean();r[x+"_l3"]=l3[x].mean()
  fs.append(r)
 m=c.merge(pd.DataFrame(fs),on="player_id",how="inner")
 if len(m)<2:continue
 cols=["fp3"]+[x+s for x in AVAILABLE for s in ["_s","_l3"]]
 for x in cols:m[x+"z"]=z(m[x])
 # v5 core, but all candidate additions are direct observed data only.
 V=.5*m.attempts_sz+.5*m.attempts_l3z
 R=.5*m.carries_sz+.5*m.carries_l3z
 base=.30*V+.30*R+.30*m.fp3z
 candidates=["passing_yards","passing_epa","passing_cpoe","ypa","completion_rate","rushing_yards"]
 for k in [1,2,3]:
  for combo in itertools.combinations(candidates,k):
   for w in [.05,.10,.15,.20,.25,.30]:
    core=1-w
    sig=sum(.5*m[x+"_s"+"z"]+.5*m[x+"_l3"+"z"] for x in combo)/len(combo)
    score=core*(base/.90)+w*sig
    pred=h.actual.mean()+score*h.actual.std()*.45
    for a,p in zip(m.actual,pred):rows.append(("+".join(combo),w,a,p))
o=pd.DataFrame(rows,columns=["metrics","weight","actual","pred"])
res=o.groupby(["metrics","weight"]).apply(lambda x:pd.Series({"n":len(x),"MAE":(x.pred-x.actual).abs().mean(),"RMSE":np.sqrt(((x.pred-x.actual)**2).mean()),"corr":x.pred.corr(x.actual),"bias":(x.pred-x.actual).mean()}),include_groups=False).reset_index().sort_values(["MAE","corr"],ascending=[True,False])
Path("data").mkdir(exist_ok=True);res.to_csv("data/qb-2025-v10-actual-data-only.csv",index=False);print(res.head(50).to_string(index=False))
