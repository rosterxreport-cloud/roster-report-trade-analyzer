#!/usr/bin/env python3
# Leakage-safe QB v2: richer opportunity + rate + recency features, rolling ridge fit.
import pandas as pd,numpy as np
from pathlib import Path
from sklearn.linear_model import Ridge
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv"
d=pd.read_csv(URL,low_memory=False);d=d[(d.position=="QB")&(d.season_type=="REG")].copy()
d["actual"]=d.passing_yards/25+4*d.passing_tds-2*d.passing_interceptions+d.rushing_yards/10+6*d.rushing_tds
d["dropbacks"]=d.attempts + (d["sacks_suffered"] if "sacks_suffered" in d.columns else (d["sacks"] if "sacks" in d.columns else 0))
d["pass_td_rate"]=d.passing_tds/d.attempts.replace(0,np.nan)
d["int_rate"]=d.passing_interceptions/d.attempts.replace(0,np.nan)
d["ypa"]=d.passing_yards/d.attempts.replace(0,np.nan)
d["rush_ypc"]=d.rushing_yards/d.carries.replace(0,np.nan)
features=["attempts","dropbacks","carries","passing_epa","passing_cpoe","pass_td_rate","int_rate","ypa","rush_ypc","actual"]
rows=[]
for wk in sorted(d.week.unique()):
 if wk<5:continue
 trainrows=[];testrows=[]
 for pid,g in d[d.week<=wk].groupby("player_id"):
  g=g.sort_values("week")
  for target in g.week:
   if target<3 or target>wk:continue
   h=g[g.week<target]
   if len(h)<2:continue
   r={"player_id":pid,"week":target}
   for f in features:
    r[f+"_season"]=h[f].mean()
    r[f+"_l3"]=h.tail(3)[f].mean()
    r[f+"_ewm"]=h[f].ewm(alpha=.5,adjust=False).mean().iloc[-1]
   cur=g[g.week==target]
   if cur.empty:continue
   r["y"]=cur.actual.iloc[0]
   (testrows if target==wk else trainrows).append(r)
 if not trainrows or not testrows:continue
 tr=pd.DataFrame(trainrows);te=pd.DataFrame(testrows)
 Xcols=[c for c in tr if c not in ["player_id","week","y"]]
 med=tr[Xcols].median();X=tr[Xcols].fillna(med);Xt=te[Xcols].fillna(med)
 mu=X.mean();sd=X.std().replace(0,1);X=(X-mu)/sd;Xt=(Xt-mu)/sd
 for alpha in [1,3,10,30,100]:
  model=Ridge(alpha=alpha).fit(X,tr.y);p=model.predict(Xt)
  for (_,r),pred in zip(te.iterrows(),p):rows.append({"week":wk,"player_id":r.player_id,"alpha":alpha,"actual":r.y,"pred":pred})
o=pd.DataFrame(rows)
res=o.groupby("alpha").apply(lambda x:pd.Series({"n":len(x),"MAE":(x.pred-x.actual).abs().mean(),"RMSE":np.sqrt(((x.pred-x.actual)**2).mean()),"corr":x.pred.corr(x.actual),"bias":(x.pred-x.actual).mean()}),include_groups=False).reset_index().sort_values("MAE")
Path("data").mkdir(exist_ok=True);res.to_csv("data/qb-2025-v2-ridge-summary.csv",index=False);o.to_csv("data/qb-2025-v2-ridge-detail.csv",index=False);print(res.to_string(index=False))
