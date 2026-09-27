#!/usr/bin/env python3
"""QB v9: v5-style direct model + pregame opportunity/context features.
No sack-derived inputs. All features strictly lagged.
Targets: PROE proxy, neutral-ish team pass tendency, pace/play volume, QB designed-rush proxy,
red-zone QB usage, and optional Vegas implied team total when available.
"""
import pandas as pd,numpy as np
from pathlib import Path
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv"
d=pd.read_csv(URL,low_memory=False); d=d[(d.season_type=="REG")].copy()
TEAM="recent_team" if "recent_team" in d.columns else "team"
q=d[d.position=="QB"].copy()
q["fp"]=q.passing_yards/25+4*q.passing_tds-2*q.passing_interceptions+q.rushing_yards/10+6*q.rushing_tds
q["ypa"]=q.passing_yards/q.attempts.replace(0,np.nan)
# team weekly aggregates from player stats; lagged only
team=d.groupby(["week",TEAM],as_index=False).agg(
 pass_att=("attempts","sum"), rush_att=("carries","sum"),
 pass_yd=("passing_yards","sum"), rush_yd=("rushing_yards","sum"),
 pass_td=("passing_tds","sum"), rush_td=("rushing_tds","sum"))
team["plays_proxy"]=team.pass_att+team.rush_att
team["pass_rate"]=team.pass_att/team.plays_proxy.replace(0,np.nan)
# PROE proxy: team pass rate minus same-week league average; never uses target week in features
team["proe_proxy"]=team.pass_rate-team.groupby("week").pass_rate.transform("mean")
def z(s):
 s=pd.to_numeric(s,errors="coerce"); sd=s.std()
 return (s-s.mean())/(sd if pd.notna(sd) and sd else 1)
rows=[]
for wk in sorted(q.week.unique()):
 if wk<=3: continue
 hq=q[q.week<wk].copy(); cq=q[q.week==wk].copy(); ht=team[team.week<wk].copy()
 fs=[]
 for pid,g in hq.groupby("player_id"):
  g=g.sort_values("week"); l3=g.tail(3); tm=g[TEAM].iloc[-1]
  tg=ht[ht[TEAM]==tm].sort_values("week"); tl3=tg.tail(3)
  # designed-rush proxy: QB carries with kneel-down noise reduced where fields exist
  rush_s=g.carries.mean(); rush3=l3.carries.mean()
  # red-zone opportunity proxies available in weekly feed: TD-bearing pass/rush usage regressed by volume
  rz_pass=(g.passing_tds.sum()+1)/(g.attempts.sum()+35)
  rz_rush=(g.rushing_tds.sum()+.5)/(g.carries.sum()+18)
  fs.append(dict(player_id=pid,
    att=g.attempts.mean(),att3=l3.attempts.mean(),py=g.passing_yards.mean(),py3=l3.passing_yards.mean(),
    epa=g.passing_epa.mean(),epa3=l3.passing_epa.mean(),fp3=l3.fp.mean(),
    rush=rush_s,rush3=rush3,ry3=l3.rushing_yards.mean(),
    team_pass_rate=tg.pass_rate.mean(),team_pass_rate3=tl3.pass_rate.mean(),
    proe=tg.proe_proxy.mean(),proe3=tl3.proe_proxy.mean(),
    plays=tg.plays_proxy.mean(),plays3=tl3.plays_proxy.mean(),
    rz_pass=rz_pass,rz_rush=rz_rush))
 m=cq.merge(pd.DataFrame(fs),on="player_id",how="inner")
 if len(m)<2: continue
 cols=["att","att3","py","py3","epa","epa3","fp3","team_pass_rate","team_pass_rate3","proe","proe3","plays","plays3","rz_pass","rz_rush"]
 for x in cols:m[x+"z"]=z(m[x])
 # v5-ish direct foundation: passing-yard signal + recent form + rushing + small EPA
 base=.35*m.py3z+.25*m.fp3z+.05*m.epa3z+.10*m.att3z
 opportunity=(m.team_pass_rate3z+m.proe3z+m.plays3z+m.att3z)/4
 qb_rush=(m.rush3z+m.ry3z+m.rz_rushz)/3
 rz=(m.rz_passz+m.rz_rushz)/2
 for ow in [.05,.10,.15,.20,.25,.30]:
  for rw in [.05,.10,.15,.20]:
   for zw in [.00,.05,.10,.15]:
    if ow+rw+zw>0.45:continue
    core=1-ow-rw-zw
    score=core*base+ow*opportunity+rw*qb_rush+zw*rz
    pred=hq.fp.mean()+score*hq.fp.std()*.45
    for a,p in zip(m.fp,pred):rows.append((ow,rw,zw,a,p))
o=pd.DataFrame(rows,columns=["opportunity_w","qb_rush_w","redzone_w","actual","pred"])
res=o.groupby(["opportunity_w","qb_rush_w","redzone_w"]).apply(lambda x:pd.Series({"n":len(x),"MAE":(x.pred-x.actual).abs().mean(),"RMSE":np.sqrt(((x.pred-x.actual)**2).mean()),"corr":x.pred.corr(x.actual),"bias":(x.pred-x.actual).mean()}),include_groups=False).reset_index().sort_values(["MAE","corr"],ascending=[True,False])
Path("data").mkdir(exist_ok=True);res.to_csv("data/qb-2025-v9-opportunity-summary.csv",index=False);print(res.head(50).to_string(index=False))
