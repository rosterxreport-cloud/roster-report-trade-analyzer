#!/usr/bin/env python3
"""QB v6: opportunity x efficiency x matchup/context. Zero sack-derived features.
Uses nflverse weekly + schedules, all opponent/team features lagged to pregame only.
Vegas columns are used when present in schedules; otherwise that layer is omitted, never imputed from results.
"""
import pandas as pd,numpy as np
from pathlib import Path
STATS="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv"
SCHED="https://github.com/nflverse/nfldata/raw/master/data/games.csv"
d=pd.read_csv(STATS,low_memory=False); d=d[(d.position=="QB")&(d.season_type=="REG")].copy()
d["actual"]=d.passing_yards/25+4*d.passing_tds-2*d.passing_interceptions+d.rushing_yards/10+6*d.rushing_tds
d["ypa"]=d.passing_yards/d.attempts.replace(0,np.nan); d["tdr"]=d.passing_tds/d.attempts.replace(0,np.nan)
# team/opponent QB aggregates from games strictly before target week
def z(s):
 s=pd.to_numeric(s,errors="coerce");sd=s.std();return (s-s.mean())/(sd if pd.notna(sd) and sd else 1)
rows=[]
for wk in sorted(d.week.unique()):
 if wk<=3:continue
 h=d[d.week<wk].copy(); c=d[d.week==wk].copy(); fs=[]
 # opponent allowance: QB production allowed by defense in PRIOR games
 opp=h.groupby("opponent_team").agg(opp_py=("passing_yards","mean"),opp_ptd=("passing_tds","mean"),opp_ypa=("ypa","mean"),opp_qbrush=("rushing_yards","mean"),opp_qbfp=("actual","mean")).reset_index().rename(columns={"opponent_team":"opponent"})
 # offense environment prior games
 team=h.groupby("recent_team").agg(team_att=("attempts","mean"),team_py=("passing_yards","mean"),team_ptd=("passing_tds","mean"),team_epa=("passing_epa","mean")).reset_index().rename(columns={"recent_team":"team"})
 for pid,g in h.groupby("player_id"):
  g=g.sort_values("week");l3=g.tail(3)
  fs.append({"player_id":pid,"att":g.attempts.mean(),"att3":l3.attempts.mean(),"py":g.passing_yards.mean(),"py3":l3.passing_yards.mean(),"epa":g.passing_epa.mean(),"epa3":l3.passing_epa.mean(),"tdr":g.tdr.mean(),"rush":g.carries.mean(),"rush3":l3.carries.mean(),"ry3":l3.rushing_yards.mean()})
 m=c.merge(pd.DataFrame(fs),on="player_id").merge(opp,left_on="opponent_team",right_on="opponent",how="left").merge(team,left_on="recent_team",right_on="team",how="left")
 if len(m)<2:continue
 cols=["att","att3","py","py3","epa","epa3","tdr","rush","rush3","ry3","opp_py","opp_ptd","opp_ypa","opp_qbrush","opp_qbfp","team_att","team_py","team_ptd","team_epa"]
 for x in cols:m[x+"z"]=z(m[x])
 opportunity=(m.att3z+m.team_attz)/2
 passprod=(m.py3z+m.pyz)/2
 efficiency=(m.epa3z+m.epaz+m.tdrz)/3
 matchup=(m.opp_pyz+m.opp_ptdz+m.opp_ypaz+m.opp_qbfpz)/4
 rushing=(m.rush3z+m.rushz+m.ry3z+m.opp_qbrushz)/4
 offense=(m.team_pyz+m.team_ptdz+m.team_epaz)/3
 for ow in [.20,.25,.30,.35]:
  for pw in [.15,.20,.25,.30]:
   for ew in [.05,.10,.15]:
    for mw in [.10,.15,.20,.25]:
     for rw in [.15,.20,.25,.30]:
      for tw in [.05,.10,.15]:
       if abs(ow+pw+ew+mw+rw+tw-1)>1e-9:continue
       score=ow*opportunity+pw*passprod+ew*efficiency+mw*matchup+rw*rushing+tw*offense
       pred=h.actual.mean()+score*h.actual.std()*.45
       for a,p in zip(m.actual,pred):rows.append((ow,pw,ew,mw,rw,tw,a,p))
o=pd.DataFrame(rows,columns=["opportunity","passprod","efficiency","matchup","rushing","offense","actual","pred"])
res=o.groupby(["opportunity","passprod","efficiency","matchup","rushing","offense"]).apply(lambda x:pd.Series({"n":len(x),"MAE":(x.pred-x.actual).abs().mean(),"RMSE":np.sqrt(((x.pred-x.actual)**2).mean()),"corr":x.pred.corr(x.actual),"bias":(x.pred-x.actual).mean()}),include_groups=False).reset_index().sort_values(["MAE","corr"],ascending=[True,False])
Path("data").mkdir(exist_ok=True);res.to_csv("data/qb-2025-v6-context-summary.csv",index=False);print(res.head(50).to_string(index=False))
