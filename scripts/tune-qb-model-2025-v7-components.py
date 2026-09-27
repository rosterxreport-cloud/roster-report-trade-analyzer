#!/usr/bin/env python3
"""QB v7 component model: project stat line, then fantasy points. Zero sack-derived features."""
import pandas as pd,numpy as np
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv"
d=pd.read_csv(URL,low_memory=False);d=d[(d.position=="QB")&(d.season_type=="REG")].copy()
TEAM="recent_team" if "recent_team" in d.columns else "team"
d["ypa"]=d.passing_yards/d.attempts.replace(0,np.nan);d["comp_rate"]=d.completions/d.attempts.replace(0,np.nan)
d["ptd_rate"]=d.passing_tds/d.attempts.replace(0,np.nan);d["int_rate"]=d.passing_interceptions/d.attempts.replace(0,np.nan)
d["rypc"]=d.rushing_yards/d.carries.replace(0,np.nan);d["rtd_rate"]=d.rushing_tds/d.carries.replace(0,np.nan)
d["actual_fp"]=d.passing_yards/25+4*d.passing_tds-2*d.passing_interceptions+d.rushing_yards/10+6*d.rushing_tds
BASE=["attempts","comp_rate","ypa","passing_epa","passing_cpoe","ptd_rate","int_rate","carries","rypc","rtd_rate","passing_yards","passing_tds","rushing_yards","rushing_tds"]
targets=["attempts","comp_rate","ypa","ptd_rate","int_rate","carries","rypc","rtd_rate"]
predrows=[]
for wk in sorted(d.week.unique()):
 if wk<6:continue
 train=[];test=[]
 for pid,g in d[d.week<=wk].groupby("player_id"):
  g=g.sort_values("week")
  for targetwk in g.week:
   if targetwk<4 or targetwk>wk:continue
   hist=g[g.week<targetwk];cur=g[g.week==targetwk]
   if len(hist)<3 or cur.empty:continue
   l3=hist.tail(3);r={"player_id":pid,"week":targetwk}
   for x in BASE:
    r[x+"_season"]=hist[x].mean();r[x+"_l3"]=l3[x].mean();r[x+"_ewm"]=hist[x].ewm(alpha=.5,adjust=False).mean().iloc[-1]
   # prior opponent QB allowance only
   prior=d[d.week<targetwk]
   opp=cur.opponent_team.iloc[0]
   od=prior[prior.opponent_team==opp]
   r["opp_py"]=od.passing_yards.mean();r["opp_ptd"]=od.passing_tds.mean();r["opp_qbrush"]=od.rushing_yards.mean()
   for y in targets:r["y_"+y]=cur[y].iloc[0]
   r["actual_fp"]=cur.actual_fp.iloc[0]
   (test if targetwk==wk else train).append(r)
 if not train or not test:continue
 tr=pd.DataFrame(train);te=pd.DataFrame(test);features=[c for c in tr if c not in ["player_id","week","actual_fp"] and not c.startswith("y_")]
 med=tr[features].median();X=tr[features].fillna(med);Xt=te[features].fillna(med)
 P={}
 for y in targets:
  model=HistGradientBoostingRegressor(max_depth=3,learning_rate=.05,max_iter=150,l2_regularization=5,random_state=7)
  model.fit(X,tr["y_"+y].fillna(tr["y_"+y].median()));P[y]=model.predict(Xt)
 att=np.clip(P["attempts"],0,None);cr=np.clip(P["comp_rate"],0,1);ypa=np.clip(P["ypa"],0,15)
 ptdr=np.clip(P["ptd_rate"],0,.2);intr=np.clip(P["int_rate"],0,.15);car=np.clip(P["carries"],0,None);rypc=np.clip(P["rypc"],-2,15);rtdr=np.clip(P["rtd_rate"],0,.5)
 py=att*ypa;ptd=att*ptdr;ints=att*intr;ry=car*rypc;rtd=car*rtdr
 fp=py/25+4*ptd-2*ints+ry/10+6*rtd
 for i,(_,r) in enumerate(te.iterrows()):predrows.append({"week":wk,"player_id":r.player_id,"actual":r.actual_fp,"pred":fp[i],"att_pred":att[i],"py_pred":py[i],"ptd_pred":ptd[i],"int_pred":ints[i],"car_pred":car[i],"ry_pred":ry[i],"rtd_pred":rtd[i]})
o=pd.DataFrame(predrows)
summary=pd.DataFrame([{"n":len(o),"MAE":mean_absolute_error(o.actual,o.pred),"RMSE":np.sqrt(((o.pred-o.actual)**2).mean()),"corr":o.pred.corr(o.actual),"bias":(o.pred-o.actual).mean()}])
Path("data").mkdir(exist_ok=True);o.to_csv("data/qb-2025-v7-components-detail.csv",index=False);summary.to_csv("data/qb-2025-v7-components-summary.csv",index=False);print(summary.to_string(index=False))
