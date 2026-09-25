#!/usr/bin/env python3
"""Shared point-in-time inputs for Week 1-2 historical projection replay.
This module intentionally exposes only information available before each game week.
"""
import json,re,unicodedata
from pathlib import Path
import pandas as pd
STATS="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.csv"
SCHED="https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
PRIORS=Path("data/backtests/priors")
def key(v):
 t=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
 t=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",t)
 return re.sub(r"[^a-z0-9]","",t)
def team(v):
 v=str(v or "").strip().upper()
 return {"LA":"LAR","JAC":"JAX","WSH":"WAS"}.get(v,v)
def load(week):
 assert week in (1,2)
 prior=json.load(open(PRIORS/f"week{week}_players.json"))
 stats=pd.read_csv(STATS,low_memory=False)
 stats=stats[(stats.season_type=="REG")&(stats.week<week)].copy()
 # Explicit leakage assertion: Week 1 empty; Week 2 Week 1 only.
 assert stats.empty if week==1 else set(stats.week.unique())<={1}
 sch=pd.read_csv(SCHED,low_memory=False)
 games=sch[(sch.season==2026)&(sch.week==week)].copy()
 opp={}
 for _,g in games.iterrows():
  h,a=team(g.home_team),team(g.away_team);opp[h]=a;opp[a]=h
 if len(opp)!=32: raise RuntimeError(f"Week {week}: expected 32 team opponent mappings, got {len(opp)}")
 ranked={fmt:{key(p["name"]):p for p in prior[fmt]} for fmt in ("standard","half","ppr")}
 return {"week":week,"prior":prior,"ranked":ranked,"stats":stats,"schedule":games,"opponent":opp}
if __name__=="__main__":
 for w in (1,2):
  x=load(w);print(w,len(x["ranked"]["half"]),len(x["stats"]),len(x["opponent"]))
