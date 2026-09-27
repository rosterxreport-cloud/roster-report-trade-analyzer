#!/usr/bin/env python3
"""QB v8 hybrid: stable component projections + direct v5-style fantasy signal. Zero sack features."""
import pandas as pd,numpy as np
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingRegressor
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv"
d=pd.read_csv(URL,low_memory=False);d=d[(d.position=="QB")&(d.season_type=="REG")].copy()
d["fp"]=d.passing_yards/25+4*d.passing_tds-2*d.passing_interceptions+d.rushing_yards/10+6*d.rushing_tds
d["ypa"]=d.passing_yards/d.attempts.replace(0,np.nan);d["ptdr"]=d.passing_tds/d.attempts.replace(0,np.nan);d["intr"]=d.passing_interceptions/d.attempts.replace(0,np.nan)
BASE=["attempts","passing_yards","passing_epa","ypa","passing_tds","ptdr","passing_interceptions","intr","carries","rushing_yards","rushing_tds","fp"]
rows=[]
for wk in sorted(d.week.unique()):
 if wk<6:continue
 tr=[];te=[]
 for pid,g in d[d.week<=wk].groupby("player_id"):
  g=g.sort_values("week")
  for tw in g.week:
   if tw<4 or tw>wk:continue
   h=g[g.week<tw];cur=g[g.week==tw]
   if len(h)<3 or cur.empty:continue
   l3=h.tail(3);r={"player_id":pid,"week":tw}
   for x in BASE:r[x+"_s"]=h[x].mean();r[x+"_l3"]=l3[x].mean();r[x+"_ewm"]=h[x].ewm(alpha=.5,adjust=False).mean().iloc[-1]
   prior=d[d.week<tw];opp=cur.opponent_team.iloc[0];od=prior[prior.opponent_team==opp]
   r["opp_py"]=od.passing_yards.mean();r["opp_ptd"]=od.passing_tds.mean();r["opp_ry"]=od.rushing_yards.mean()
   r["y_att"]=cur.attempts.iloc[0];r["y_py"]=cur.passing_yards.iloc[0];r["y_car"]=cur.carries.iloc[0];r["y_ry"]=cur.rushing_yards.iloc[0];r["y_fp"]=cur.fp.iloc[0]
   (te if tw==wk else tr).append(r)
 if not tr or not te:continue
 tr=pd.DataFrame(tr);te=pd.DataFrame(te);features=[c for c in tr if c not in ["player_id","week"] and not c.startswith("y_")]
 med=tr[features].median();X=tr[features].fillna(med);Xt=te[features].fillna(med)
 P={}
 for y in ["att","py","car","ry"]:
  m=HistGradientBoostingRegressor(max_depth=3,learning_rate=.04,max_iter=150,l2_regularization=10,random_state=8).fit(X,tr["y_"+y]);P[y]=m.predict(Xt)
 # stable TD/INT rates: shrink player history strongly toward league prior
 lg_ptdr=tr["passing_tds_s"].sum()/tr["attempts_s"].sum();lg_intr=tr["passing_interceptions_s"].sum()/tr["attempts_s"].sum()
 ptdr=(te.ptdr_ewm*te.attempts_s+lg_ptdr*100)/(te.attempts_s+100);intr=(te.intr_ewm*te.attempts_s+lg_intr*150)/(te.attempts_s+150)
 # rushing TD expectation shrunk toward historical per-carry baseline
 lg_rtd=(tr.rushing_tds_s.sum()/tr.carries_s.sum()) if tr.carries_s.sum()>0 else .03
 rtdr=(te.rushing_tds_ewm*0 + lg_rtd) # deliberately highly regressed
 component=np.clip(P["py"],0,None)/25+4*np.clip(P["att"],0,None)*ptdr-2*np.clip(P["att"],0,None)*intr+np.clip(P["ry"],-10,None)/10+6*np.clip(P["car"],0,None)*rtdr
 # direct signal: v5 insight, recent FP + passing yards + EPA + rushing usage
 direct=.45*te.fp_ewm+.25*(te.passing_yards_ewm/25)+.05*te.passing_epa_ewm+ .25*(te.rushing_yards_ewm/10+6*te.rushing_tds_ewm)
 for blend in [.25,.40,.50,.60,.75]:
  pred=blend*component+(1-blend)*direct
  for i,(_,r) in enumerate(te.iterrows()):rows.append({"week":wk,"player_id":r.player_id,"blend_component":blend,"actual":r.y_fp,"pred":pred.iloc[i] if hasattr(pred,"iloc") else pred[i]})
o=pd.DataFrame(rows)
res=o.groupby("blend_component").apply(lambda x:pd.Series({"n":len(x),"MAE":(x.pred-x.actual).abs().mean(),"RMSE":np.sqrt(((x.pred-x.actual)**2).mean()),"corr":x.pred.corr(x.actual),"bias":(x.pred-x.actual).mean()}),include_groups=False).reset_index().sort_values(["MAE","corr"],ascending=[True,False])
Path("data").mkdir(exist_ok=True);res.to_csv("data/qb-2025-v8-hybrid-summary.csv",index=False);o.to_csv("data/qb-2025-v8-hybrid-detail.csv",index=False);print(res.to_string(index=False))
