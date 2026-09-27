#!/usr/bin/env python3
"""QB v3: zero sack-derived features; passing-forward leakage-safe backtest."""
import pandas as pd,numpy as np
from pathlib import Path
from sklearn.linear_model import Ridge
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv"
d=pd.read_csv(URL,low_memory=False);d=d[(d.position=="QB")&(d.season_type=="REG")].copy()
d["actual"]=d.passing_yards/25+4*d.passing_tds-2*d.passing_interceptions+d.rushing_yards/10+6*d.rushing_tds
d["pass_td_rate"]=d.passing_tds/d.attempts.replace(0,np.nan)
d["int_rate"]=d.passing_interceptions/d.attempts.replace(0,np.nan)
d["ypa"]=d.passing_yards/d.attempts.replace(0,np.nan)
d["comp_rate"]=d.completions/d.attempts.replace(0,np.nan)
# Explicitly no sacks, sack rate, pressure-to-sack, or dropbacks derived from sacks.
passing=["attempts","completions","passing_yards","passing_tds","passing_interceptions","passing_epa","passing_cpoe","pass_td_rate","int_rate","ypa","comp_rate"]
rushing=["carries","rushing_yards","rushing_tds"]
rows=[]
for wk in sorted(d.week.unique()):
 if wk<5:continue
 train=[];test=[]
 for pid,g in d[d.week<=wk].groupby("player_id"):
  g=g.sort_values("week")
  for target in g.week:
   if target<3 or target>wk:continue
   h=g[g.week<target];cur=g[g.week==target]
   if len(h)<2 or cur.empty:continue
   r={"player_id":pid,"week":target}
   for f in passing+rushing:
    r[f+"_season"]=h[f].mean();r[f+"_l3"]=h.tail(3)[f].mean();r[f+"_ewm"]=h[f].ewm(alpha=.5,adjust=False).mean().iloc[-1]
   r["y"]=cur.actual.iloc[0];(test if target==wk else train).append(r)
 if not train or not test:continue
 tr=pd.DataFrame(train);te=pd.DataFrame(test);cols=[c for c in tr if c not in ["player_id","week","y"]]
 med=tr[cols].median();X=tr[cols].fillna(med);Xt=te[cols].fillna(med);mu=X.mean();sd=X.std().replace(0,1);X=(X-mu)/sd;Xt=(Xt-mu)/sd
 for alpha in [10,30,100,300]:
  m=Ridge(alpha=alpha).fit(X,tr.y);p=m.predict(Xt)
  for (_,r),pred in zip(te.iterrows(),p):rows.append({"week":wk,"player_id":r.player_id,"alpha":alpha,"actual":r.y,"pred":pred})
o=pd.DataFrame(rows);res=o.groupby("alpha").apply(lambda x:pd.Series({"n":len(x),"MAE":(x.pred-x.actual).abs().mean(),"RMSE":np.sqrt(((x.pred-x.actual)**2).mean()),"corr":x.pred.corr(x.actual),"bias":(x.pred-x.actual).mean()}),include_groups=False).reset_index().sort_values("MAE")
Path("data").mkdir(exist_ok=True);res.to_csv("data/qb-2025-v3-nosacks-summary.csv",index=False);o.to_csv("data/qb-2025-v3-nosacks-detail.csv",index=False);print(res.to_string(index=False))
