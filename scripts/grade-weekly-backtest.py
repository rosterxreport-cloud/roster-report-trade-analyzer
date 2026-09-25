#!/usr/bin/env python3
"""Grade historical weekly projection CSVs against leakage-safe actuals.
Expected projection files: data/backtests/week{1,2}_projections.csv
Columns: player, position, standard_projection, half_projection, ppr_projection
Optional stat projection columns are graded when present.
"""
from pathlib import Path
import pandas as pd, numpy as np, re, unicodedata
OUT=Path("data/backtests")
def key(v):
 t=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
 t=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",t)
 return re.sub(r"[^a-z0-9]","",t)
rows=[]; summaries=[]
for w in (1,2):
 pth=OUT/f"week{w}_projections.csv"
 if not pth.exists():
  print(f"Week {w}: projection file not present yet; skipping grade")
  continue
 p=pd.read_csv(pth); a=pd.read_csv(OUT/f"week{w}_actuals.csv")
 p["k"]=p.player.map(key); a["k"]=a.player_display_name.map(key)
 m=p.merge(a,on="k",how="inner",suffixes=("_proj","_actual"));m["backtest_week"]=w
 for fmt,pc,ac in [("standard","standard_projection","std_actual"),("half","half_projection","half_actual"),("ppr","ppr_projection","ppr_actual")]:
  if pc not in m: continue
  m[f"{fmt}_error"]=m[pc]-m[ac];m[f"{fmt}_abs_error"]=m[f"{fmt}_error"].abs()
  for pos,g in m.groupby("position_actual"):
   e=g[f"{fmt}_error"].dropna()
   if len(e): summaries.append({"week":w,"position":pos,"format":fmt,"n":len(e),"mae":e.abs().mean(),"rmse":np.sqrt((e**2).mean()),"bias":e.mean()})
 rows.append(m)
if rows:
 allm=pd.concat(rows,ignore_index=True);allm.to_csv(OUT/"player_level_results.csv",index=False)
 for fmt in ("standard","half","ppr"):
  ec=f"{fmt}_error"
  if ec not in allm: continue
  for pos,g in allm.groupby("position_actual"):
   e=g[ec].dropna()
   if len(e): summaries.append({"week":"combined","position":pos,"format":fmt,"n":len(e),"mae":e.abs().mean(),"rmse":np.sqrt((e**2).mean()),"bias":e.mean()})
 s=pd.DataFrame(summaries);s.to_csv(OUT/"accuracy_summary.csv",index=False);print(s.to_string(index=False))
else: print("No historical projection CSVs available to grade.")
