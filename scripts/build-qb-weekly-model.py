#!/usr/bin/env python3
# QB weekly model scaffold: Fantasy Points passing inputs + nflverse rushing.
# XFP columns are explicitly excluded from model features.
import pandas as pd, numpy as np, re, unicodedata
from pathlib import Path
FP_W1=Path("data/qb-passing-week1.csv"); FP_W2=Path("data/qb-passing-week2.csv")
NFLVERSE="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2026.csv"
def load_fp(p):
 d=pd.read_csv(p,header=1); d=d[d["POS"].eq("QB")].copy()
 # Never allow third-party expected fantasy points into our feature set.
 d=d[[c for c in d.columns if "XFP" not in str(c).upper()]]
 return d
def key(x):
 x=unicodedata.normalize("NFKD",str(x)).encode("ascii","ignore").decode().lower()
 return re.sub(r"[^a-z0-9]","",x)
w1,w2=load_fp(FP_W1),load_fp(FP_W2)
nv=pd.read_csv(NFLVERSE,low_memory=False); nv=nv[nv.position.eq("QB")].copy()
nv["k"]=nv.player_display_name.map(key)
# nflverse rushing layer, separated by week when available.
rushcols=[c for c in ["week","player_display_name","carries","rushing_yards","rushing_tds","rushing_first_downs","rushing_epa"] if c in nv.columns]
rush=nv[rushcols].copy()
Path("data").mkdir(exist_ok=True)
w1.to_csv("data/qb-passing-week1-clean.csv",index=False);w2.to_csv("data/qb-passing-week2-clean.csv",index=False)
rush.to_csv("data/qb-nflverse-rushing-2026.csv",index=False)
print("QB passing rows",len(w1),len(w2),"nflverse QB rushing rows",len(rush))
print("XFP excluded:",not any("XFP" in str(c).upper() for c in w1.columns))
