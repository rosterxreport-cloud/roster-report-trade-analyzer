#!/usr/bin/env python3
# QB weekly backtest scaffold. Fantasy Points passing + nflverse rushing. XFP excluded.
import pandas as pd, numpy as np, re, unicodedata
from pathlib import Path
NFLVERSE="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2026.csv"
def key(x):
 x=unicodedata.normalize("NFKD",str(x or "")).encode("ascii","ignore").decode().lower()
 return re.sub(r"[^a-z0-9]","",x)
def fp(path):
 d=pd.read_csv(path,header=1)
 d=d[d["POS"].eq("QB")].copy()
 d=d[[c for c in d.columns if "XFP" not in str(c).upper()]]
 d["k"]=d["Name"].map(key)
 return d
w1=fp("data/qb-passing-week1.csv"); w2=fp("data/qb-passing-week2.csv")
nv=pd.read_csv(NFLVERSE,low_memory=False);nv=nv[nv.position.eq("QB")].copy();nv["k"]=nv.player_display_name.map(key)
# Week-specific nflverse rushing inputs. No third-party expected fantasy points.
rushcols=[c for c in ["week","k","player_display_name","carries","rushing_yards","rushing_tds","rushing_first_downs","rushing_epa"] if c in nv.columns]
r1=nv[nv.week.eq(1)][rushcols].copy();r2=nv[nv.week.eq(2)][rushcols].copy()
# Candidate passing skill signals are intentionally separated so each can be tested.
features=["DB","ATT","CMP %","YDS","YPA","TD","INT","RATE","ANY/A","SUCC %","SACK %","CPOE","ADJ CMP %","ADOT","DEEP %","ACC %","HERO %","TWT %","DROP %","TTT","PRESS %","P2S %","EPA/DB"]
features=[x for x in features if x in w1.columns and x in w2.columns]
rows=[]
for _,b in w1.iterrows():
 if b.k not in set(w2.k):continue
 a=w2[w2.k.eq(b.k)].iloc[0]
 rr=r1[r1.k.eq(b.k)]
 out={"player":b["Name"],"team":b["Team"]}
 for x in features:
  out["w1_"+x]=pd.to_numeric(b[x],errors="coerce")
 for x in ["carries","rushing_yards","rushing_tds","rushing_first_downs","rushing_epa"]:
  out["w1_rush_"+x]=pd.to_numeric(rr.iloc[0][x],errors="coerce") if len(rr) and x in rr else 0
 out["w2_actual_fp"]=pd.to_numeric(a["FP"],errors="coerce")
 rows.append(out)
o=pd.DataFrame(rows)
Path("data").mkdir(exist_ok=True);o.to_csv("data/qb-week1-to-week2-backtest-input.csv",index=False)
print("Matched QBs:",len(o));print("Passing features:",features);print("XFP present:",any("XFP" in c.upper() for c in o.columns))
