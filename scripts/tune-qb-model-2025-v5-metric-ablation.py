#!/usr/bin/env python3
"""QB v5: leakage-safe passing metric ablation on top of v1. Zero sack-derived data."""
import pandas as pd,numpy as np,itertools
from pathlib import Path
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv"
d=pd.read_csv(URL,low_memory=False);d=d[(d.position=="QB")&(d.season_type=="REG")].copy()
d["actual"]=d.passing_yards/25+4*d.passing_tds-2*d.passing_interceptions+d.rushing_yards/10+6*d.rushing_tds
d["ypa_hist"]=d.passing_yards/d.attempts.replace(0,np.nan)
d["comp_rate_hist"]=d.completions/d.attempts.replace(0,np.nan)
d["td_rate_hist"]=d.passing_tds/d.attempts.replace(0,np.nan)
d["int_rate_hist"]=d.passing_interceptions/d.attempts.replace(0,np.nan)
METRICS=["passing_cpoe","passing_epa","ypa_hist","comp_rate_hist","td_rate_hist","int_rate_hist","passing_yards","passing_tds"]
def z(s):
 s=pd.to_numeric(s,errors="coerce"); sd=s.std()
 return (s-s.mean())/(sd if pd.notna(sd) and sd else 1)
rows=[]
for wk in sorted(d.week.unique()):
 if wk<=2:continue
 h=d[d.week<wk]; c=d[d.week==wk]; fs=[]
 for pid,g in h.groupby("player_id"):
  g=g.sort_values("week");l3=g.tail(3)
  r={"player_id":pid,"att":g.attempts.mean(),"att3":l3.attempts.mean(),"rush":g.carries.mean(),"rush3":l3.carries.mean(),"fp3":l3.actual.mean()}
  for x in METRICS:
   r[x+"_s"]=g[x].mean();r[x+"_l3"]=l3[x].mean()
  fs.append(r)
 m=c.merge(pd.DataFrame(fs),on="player_id",how="inner")
 if len(m)<2:continue
 cols=["att","att3","rush","rush3","fp3"]+[x+s for x in METRICS for s in ["_s","_l3"]]
 for x in cols:m[x+"z"]=z(m[x])
 V=.5*m.attz+.5*m.att3z;R=.5*m.rushz+.5*m.rush3z
 # preserve v1 core proportions, reserve 5-20% for passing signal
 for k in [1,2,3]:
  for combo in itertools.combinations(METRICS,k):
   for pw in [.05,.10,.15,.20]:
    core=1-pw
    base_score=core*(.30*V+.30*R+.30*m.fp3z)/.90
    signals=[]
    for x in combo:
     sig=.5*m[x+"_s"+"z"]+.5*m[x+"_l3"+"z"]
     if x=="int_rate_hist":sig=-sig
     signals.append(sig)
    ps=sum(signals)/len(signals)
    score=base_score+pw*ps
    pred=h.actual.mean()+score*h.actual.std()*.45
    name="+".join(combo)
    for a,p in zip(m.actual,pred):rows.append((name,pw,a,p))
o=pd.DataFrame(rows,columns=["metrics","pass_weight","actual","pred"])
res=o.groupby(["metrics","pass_weight"]).apply(lambda x:pd.Series({"n":len(x),"MAE":(x.pred-x.actual).abs().mean(),"RMSE":np.sqrt(((x.pred-x.actual)**2).mean()),"corr":x.pred.corr(x.actual),"bias":(x.pred-x.actual).mean()}),include_groups=False).reset_index().sort_values(["MAE","corr"],ascending=[True,False])
Path("data").mkdir(exist_ok=True);res.to_csv("data/qb-2025-v5-metric-ablation.csv",index=False)
# single-metric ranking for interpretability
single=res[~res.metrics.str.contains("\\+")].sort_values(["MAE","corr"],ascending=[True,False])
single.to_csv("data/qb-2025-v5-single-metrics.csv",index=False)
print("TOP COMBINATIONS");print(res.head(40).to_string(index=False));print("\nSINGLE METRICS");print(single.to_string(index=False))
