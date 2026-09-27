#!/usr/bin/env python3
"""Leakage-safe 2025 QB weekly backtest using nflverse data.
Frozen architecture: 40% volume, 25% rushing, 25% advanced passing, 10% reserved.
P2S and third-party XFP are excluded.
"""
import pandas as pd, numpy as np
from pathlib import Path
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv"
d=pd.read_csv(URL,low_memory=False)
d=d[(d.position=="QB") & (d.season_type=="REG")].copy()
# Standard fantasy points: 1/25 pass yd, 4 pass TD, -2 INT, 1/10 rush yd, 6 rush TD.
d["actual_fp"]=d.passing_yards/25+d.passing_tds*4-d.passing_interceptions*2+d.rushing_yards/10+d.rushing_tds*6
# Only prior weeks may inform each projection.
rows=[]
for wk in sorted(d.week.unique()):
 if wk<=1: continue
 hist=d[d.week<wk].copy(); cur=d[d.week==wk].copy()
 agg=hist.groupby("player_id").agg(
   games=("week","nunique"),att=("attempts","mean"),db=("attempts","mean"),
   rush=("carries","mean"),pass_epa=("passing_epa","mean"),cpoe=("passing_cpoe","mean"),
   ypa=("passing_yards","sum"),pass_att=("attempts","sum")
 ).reset_index()
 agg["ypa"]=agg.ypa/agg.pass_att.replace(0,np.nan)
 m=cur.merge(agg,on="player_id",how="inner")
 if len(m)<2: continue
 # Cross-sectional z-scores use only pregame historical aggregates.
 def z(s):
  s=pd.to_numeric(s,errors="coerce");sd=s.std()
  return (s-s.mean())/(sd if pd.notna(sd) and sd else 1)
 m["volume"]=z(m.att)
 m["rushscore"]=z(m.rush)
 m["advanced"]=(z(m.pass_epa)+z(m.cpoe)+z(m.ypa))/3
 m["score"]=.40*m.volume+.25*m.rushscore+.25*m.advanced
 # Translate score into FP using only historical QB scoring distribution through prior week.
 base=hist.actual_fp.mean();scale=hist.actual_fp.std()
 m["projection"]=base+m.score*scale*.45
 for _,r in m.iterrows(): rows.append({"week":int(wk),"player":r.player_display_name,"projection":r.projection,"actual":r.actual_fp})
o=pd.DataFrame(rows);e=o.projection-o.actual;ae=e.abs()
summary=pd.DataFrame([{"n":len(o),"MAE":ae.mean(),"RMSE":np.sqrt((e**2).mean()),"corr":o.projection.corr(o.actual),"bias":e.mean(),"within1":(ae<=1).mean(),"within3":(ae<=3).mean(),"within6":(ae<=6).mean()}])
Path("data").mkdir(exist_ok=True);o.to_csv("data/qb-2025-backtest-detail.csv",index=False);summary.to_csv("data/qb-2025-backtest-summary.csv",index=False)
print(summary.to_string(index=False))

# execute historical validation
