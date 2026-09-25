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
rows=[]; summaries=[]; stat_summaries=[]
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
 # Grade raw stat components whenever the historical runner provides them.
 pairs=[("pass_attempts","attempts"),("carries","carries"),("targets","targets"),("receptions","receptions"),("pass_yards","passing_yards"),("pass_tds","passing_tds"),("interceptions","passing_interceptions"),("carries","carries"),("rush_yards","rushing_yards"),("rush_tds","rushing_tds"),("targets","targets"),("receptions","receptions"),("rec_yards","receiving_yards"),("rec_tds","receiving_tds")]
 for pc,ac in pairs:
  if pc not in m.columns or ac not in m.columns: continue
  e=pd.to_numeric(m[pc],errors="coerce")-pd.to_numeric(m[ac],errors="coerce")
  for pos,idx in m.groupby("position_actual").groups.items():
   z=e.loc[idx].dropna()
   if len(z): stat_summaries.append({"week":w,"position":pos,"stat":pc,"n":len(z),"mae":z.abs().mean(),"rmse":np.sqrt((z**2).mean()),"bias":z.mean()})
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
 if stat_summaries:
  ss=pd.DataFrame(stat_summaries)
  # Combined stat diagnostics.
  for (pos,stat),g in ss.groupby(["position","stat"]):
   pass
  ss.to_csv(OUT/"stat_accuracy_summary.csv",index=False);print("\nSTAT DIAGNOSTICS\n",ss.to_string(index=False))
  # RB volume-vs-efficiency diagnostic from matched player rows.
  rb=allm[allm.position_actual=="RB"].copy()
  diag=[]
  for w,g in rb.groupby("backtest_week"):
   for pc,ac in [("carries_proj","carries_actual"),("targets_proj","targets_actual"),("receptions_proj","receptions_actual")]:
    if pc in g.columns and ac in g.columns:
     e=pd.to_numeric(g[pc],errors="coerce")-pd.to_numeric(g[ac],errors="coerce")
     diag.append({"week":w,"metric":pc.replace("_proj",""),"n":e.notna().sum(),"bias":e.mean(),"mae":e.abs().mean()})
   if "carries_proj" in g.columns and "rush_yards" in g.columns:
    pc=pd.to_numeric(g["carries_proj"],errors="coerce"); py=pd.to_numeric(g.rush_yards,errors="coerce")
    ac=pd.to_numeric(g["carries_actual"],errors="coerce")
    ay=pd.to_numeric(g["rushing_yards"],errors="coerce")
    pypc=py/pc.replace(0,np.nan); aypc=ay/ac.replace(0,np.nan)
    e=pypc-aypc;diag.append({"week":w,"metric":"yards_per_carry","n":e.notna().sum(),"bias":e.mean(),"mae":e.abs().mean()})
  pd.DataFrame(diag).to_csv(OUT/"rb_volume_efficiency_diagnostic.csv",index=False);print("\nRB VOLUME/EFFICIENCY\n",pd.DataFrame(diag).to_string(index=False))
  # V4 residual analysis: rank RBs within each team by projected opportunity.
  rb["opp_score"]=pd.to_numeric(rb.get("carries_proj"),errors="coerce").fillna(0)+1.5*pd.to_numeric(rb.get("targets_proj"),errors="coerce").fillna(0)
  rb["role_rank"]=rb.groupby(["backtest_week","team"])["opp_score"].rank(method="first",ascending=False)
  rb["role_bucket"]=np.where(rb.role_rank==1,"RB1",np.where(rb.role_rank==2,"RB2","RB3+"))
  resid=[]
  for (bucket,fmt),g in [( (b,f),gg) for (b,f),gg in rb.melt(id_vars=[x for x in rb.columns if not x.endswith("_error")],value_vars=[x for x in ["standard_error","half_error","ppr_error"] if x in rb],var_name="efmt",value_name="err").assign(fmt=lambda x:x.efmt.str.replace("_error","")).groupby(["role_bucket","fmt"]) ]:
   e=pd.to_numeric(g.err,errors="coerce").dropna();resid.append({"role_bucket":bucket,"format":fmt,"n":len(e),"mae":e.abs().mean(),"rmse":np.sqrt((e**2).mean()),"bias":e.mean()})
  rr=pd.DataFrame(resid);rr.to_csv(OUT/"rb_role_residuals.csv",index=False);print("\nRB ROLE RESIDUALS\n",rr.to_string(index=False))
  if "ppr_abs_error" in rb:
   cols=[x for x in ["backtest_week","player_proj","team","role_bucket","ppr_projection","ppr_actual","ppr_error","ppr_abs_error","carries_proj","carries_actual","targets_proj","targets_actual"] if x in rb]
   worst=rb.sort_values("ppr_abs_error",ascending=False)[cols].head(20)
   worst.to_csv(OUT/"rb_largest_misses.csv",index=False);print("\nRB LARGEST PPR MISSES\n",worst.to_string(index=False))
else: print("No historical projection CSVs available to grade.")
