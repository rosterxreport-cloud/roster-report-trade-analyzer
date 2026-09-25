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
  # Tight fantasy-point hit rates: cumulative thresholds by position/format.
  hitrows=[]
  for (pos,fmt),g in allm.melt(id_vars=[x for x in allm.columns if not x.endswith("_error")],value_vars=[x for x in ["standard_error","half_error","ppr_error"] if x in allm],var_name="efmt",value_name="err").assign(fmt=lambda x:x.efmt.str.replace("_error","")).groupby(["position_actual","fmt"]):
   e=pd.to_numeric(g.err,errors="coerce").dropna().abs()
   hitrows.append({"position":pos,"format":fmt,"n":len(e),"within_1_pct":100*(e<=1).mean(),"within_3_pct":100*(e<=3).mean(),"within_6_pct":100*(e<=6).mean(),"over_6_pct":100*(e>6).mean()})
  # Add week-specific hit rates using the exact same thresholds.
  for (wk,pos,fmt),g in allm.melt(id_vars=[x for x in allm.columns if not x.endswith("_error")],value_vars=[x for x in ["standard_error","half_error","ppr_error"] if x in allm],var_name="efmt",value_name="err").assign(fmt=lambda x:x.efmt.str.replace("_error","")).groupby(["backtest_week","position_actual","fmt"]):
   e=pd.to_numeric(g.err,errors="coerce").dropna().abs()
   hitrows.append({"week":wk,"position":pos,"format":fmt,"n":len(e),"within_1_pct":100*(e<=1).mean(),"within_3_pct":100*(e<=3).mean(),"within_6_pct":100*(e<=6).mean(),"over_6_pct":100*(e>6).mean()})
  hr=pd.DataFrame(hitrows);hr.to_csv(OUT/"fantasy_point_hit_rates.csv",index=False);print("\nFANTASY POINT HIT RATES +/-1 / +/-3 / +/-6\n",hr.to_string(index=False))
  if "ppr_abs_error" in rb:
   cols=[x for x in ["backtest_week","player_proj","team","role_bucket","ppr_projection","ppr_actual","ppr_error","ppr_abs_error","carries_proj","carries_actual","targets_proj","targets_actual"] if x in rb]
   worst=rb.sort_values("ppr_abs_error",ascending=False)[cols].head(20)
   worst.to_csv(OUT/"rb_largest_misses.csv",index=False);print("\nRB LARGEST PPR MISSES\n",worst.to_string(index=False))
   # Zero/near-zero workload audit: distinguish historical availability misses from football variance.
   z=rb[(pd.to_numeric(rb.get("carries_actual"),errors="coerce").fillna(0)+pd.to_numeric(rb.get("targets_actual"),errors="coerce").fillna(0)<=1)&(pd.to_numeric(rb.get("ppr_projection"),errors="coerce").fillna(0)>=5)].copy()
   if len(z):
    z["availability_flag"]=np.where(pd.to_numeric(z.get("availability_factor"),errors="coerce").fillna(1)<1,"ADJUSTED","FULL_AVAILABILITY")
    zcols=[x for x in ["backtest_week","player_proj","team","role_bucket","ppr_projection","ppr_actual","carries_actual","targets_actual","availability_factor","historical_status","availability_flag"] if x in z]
    z=z[zcols].sort_values("ppr_projection",ascending=False)
    z.to_csv(OUT/"rb_zero_workload_audit.csv",index=False);print("\nRB ZERO/NEAR-ZERO WORKLOAD AUDIT\n",z.to_string(index=False))
else: print("No historical projection CSVs available to grade.")

# WR route-vs-TPRR weight sweep grading
try:
 sw=pd.read_csv(OUT/"week2_wr_weight_sweep.csv"); act=pd.read_csv(OUT/"week2_actuals.csv")
 namecol=next(x for x in ["player","player_name","player_display_name"] if x in act.columns); act["k"]=act[namecol].map(key); sw["k"]=sw.player.map(key)
 pcol=next(x for x in ["ppr_actual","fantasy_points_ppr","ppr"] if x in act.columns); mm=sw.merge(act[["k",pcol]],on="k")
 print("\nWR V2 ROUTE-vs-TPRR WEIGHT SWEEP")
 for col in ["ppr_r100_t0","ppr_r90_t10","ppr_r85_t15","ppr_r80_t20","ppr_r75_t25","ppr_r70_t30"]:
  e=mm[col]-mm[pcol]; ae=e.abs(); print(col,"n",len(e),"MAE",round(ae.mean(),3),"BIAS",round(e.mean(),3),"+/-1",round(100*(ae<=1).mean(),2),"+/-3",round(100*(ae<=3).mean(),2),"+/-6",round(100*(ae<=6).mean(),2))
except Exception as ex: print("WR weight sweep grading unavailable:",ex)

# WR V2.1 YPT regression grading
try:
 sw=pd.read_csv(OUT/"week2_wr_weight_sweep.csv");act=pd.read_csv(OUT/"week2_actuals.csv");namecol=next(x for x in ["player","player_name","player_display_name"] if x in act.columns);act["k"]=act[namecol].map(key);sw["k"]=sw.player.map(key);pcol=next(x for x in ["ppr_actual","fantasy_points_ppr","ppr"] if x in act.columns);mm=sw.merge(act[["k",pcol]],on="k");print("\nWR V2.1 YPT REGRESSION SWEEP");
 for col in ["ppr_r85_t15","ppr_ypt_10","ppr_ypt_20","ppr_ypt_30"]:
  e=mm[col]-mm[pcol];ae=e.abs();print(col,"n",len(e),"MAE",round(ae.mean(),3),"BIAS",round(e.mean(),3),"+/-1",round(100*(ae<=1).mean(),2),"+/-3",round(100*(ae<=3).mean(),2),"+/-6",round(100*(ae<=6).mean(),2))
except Exception as ex: print("WR YPT grading unavailable:",ex)

try:
 sw=pd.read_csv(OUT/"week2_projections.csv");sw=sw[sw.position=="WR"].copy();act=pd.read_csv(OUT/"week2_actuals.csv");namecol=next(x for x in ["player","player_name","player_display_name"] if x in act.columns);act["k"]=act[namecol].map(key);sw["k"]=sw.player.map(key);pcol=next(x for x in ["ppr_actual","fantasy_points_ppr","ppr"] if x in act.columns);mm=sw.merge(act[["k",pcol]],on="k");print("\nWR 85/15 XTD BLEND SWEEP")
 for col in ["ppr_xtd_0","ppr_xtd_25","ppr_xtd_50","ppr_xtd_75","ppr_xtd_100"]:
  e=mm[col]-mm[pcol];ae=e.abs();print(col,"n",len(e),"MAE",round(ae.mean(),3),"BIAS",round(e.mean(),3),"+/-1",round(100*(ae<=1).mean(),2),"+/-3",round(100*(ae<=3).mean(),2),"+/-6",round(100*(ae<=6).mean(),2))
except Exception as ex:print("WR xTD grading unavailable:",ex)

try:
 sw=pd.read_csv(OUT/"week2_projections.csv");sw=sw[sw.position=="WR"].copy();act=pd.read_csv(OUT/"week2_actuals.csv");namecol=next(x for x in ["player","player_name","player_display_name"] if x in act.columns);act["k"]=act[namecol].map(key);sw["k"]=sw.player.map(key);pcol=next(x for x in ["ppr_actual","fantasy_points_ppr","ppr"] if x in act.columns);mm=sw.merge(act[["k",pcol]],on="k");print("\nWR XTD75 + YPT REGRESSION SWEEP")
 for col in ["ppr_xtd_75","ppr_xtd75_ypt_10","ppr_xtd75_ypt_20","ppr_xtd75_ypt_30"]:
  e=mm[col]-mm[pcol];ae=e.abs();print(col,"n",len(e),"MAE",round(ae.mean(),3),"BIAS",round(e.mean(),3),"+/-1",round(100*(ae<=1).mean(),2),"+/-3",round(100*(ae<=3).mean(),2),"+/-6",round(100*(ae<=6).mean(),2))
except Exception as ex:print("WR xTD75 YPT grading unavailable:",ex)

try:
 sw=pd.read_csv(OUT/"week2_projections.csv");sw=sw[sw.position=="RB"].copy();act=pd.read_csv(OUT/"week2_actuals.csv");namecol=next(x for x in ["player","player_name","player_display_name"] if x in act.columns);act["k"]=act[namecol].map(key);sw["k"]=sw.player.map(key);pcol=next(x for x in ["ppr_actual","fantasy_points_ppr","ppr"] if x in act.columns);mm=sw.merge(act[["k",pcol]],on="k");print("\nRB FP UNDERLYING METRIC ISOLATION SWEEP")
 for col in ["rb_fp_control","rb_fp_snap","rb_fp_att","rb_fp_expyds","rb_fp_i5","rb_fp_route","rb_fp_tprr","rb_fp_rushxtd","rb_fp_recxtd","rb_fp_combxtd"]:
  e=mm[col]-mm[pcol];ae=e.abs();print(col,"n",len(e),"MAE",round(ae.mean(),3),"BIAS",round(e.mean(),3),"+/-1",round(100*(ae<=1).mean(),2),"+/-3",round(100*(ae<=3).mean(),2),"+/-6",round(100*(ae<=6).mean(),2))
except Exception as ex:print("RB FP grading unavailable:",ex)

try:
 sw=pd.read_csv(OUT/"week2_projections.csv");sw=sw[sw.position=="RB"].copy();act=pd.read_csv(OUT/"week2_actuals.csv");namecol=next(x for x in ["player","player_name","player_display_name"] if x in act.columns);act["k"]=act[namecol].map(key);sw["k"]=sw.player.map(key);pcol=next(x for x in ["ppr_actual","fantasy_points_ppr","ppr"] if x in act.columns);mm=sw.merge(act[["k",pcol]],on="k");print("\nRB REC XTD + LIGHT TPRR SWEEP")
 for col in ["rb_fp_recxtd","rb_fp_recxtd_tprr_5","rb_fp_recxtd_tprr_10","rb_fp_recxtd_tprr_15","rb_fp_recxtd_tprr_20"]:
  e=mm[col]-mm[pcol];ae=e.abs();print(col,"n",len(e),"MAE",round(ae.mean(),3),"BIAS",round(e.mean(),3),"+/-1",round(100*(ae<=1).mean(),2),"+/-3",round(100*(ae<=3).mean(),2),"+/-6",round(100*(ae<=6).mean(),2))
except Exception as ex:print("RB rec xTD TPRR grading unavailable:",ex)

try:
 sw=pd.read_csv(OUT/"week2_projections.csv");sw=sw[sw.position=="RB"].copy();act=pd.read_csv(OUT/"week2_actuals.csv");namecol=next(x for x in ["player","player_name","player_display_name"] if x in act.columns);act["k"]=act[namecol].map(key);sw["k"]=sw.player.map(key);pcol=next(x for x in ["ppr_actual","fantasy_points_ppr","ppr"] if x in act.columns);m=sw.merge(act[["k",pcol]],on="k");m["err"]=m.rb_fp_recxtd-m[pcol];m["ae"]=m.err.abs();m["opp"]=m.carries+m.targets;m["recshare"]=m.targets/(m.carries+m.targets).clip(lower=1)
 print("\nRB REC XTD ERROR SEGMENTS")
 cuts=[("projected_top",pd.qcut(m.rb_fp_recxtd,3,labels=["low","mid","high"],duplicates="drop")),("opportunity",pd.qcut(m.opp,3,labels=["low","mid","high"],duplicates="drop")),("receiving_share",pd.qcut(m.recshare,3,labels=["low","mid","high"],duplicates="drop"))]
 for nm,grp in cuts:
  m["_g"]=grp
  for lab,d in m.groupby("_g",observed=True): print(nm,lab,"n",len(d),"MAE",round(d.ae.mean(),3),"BIAS",round(d.err.mean(),3),"ACT",round(d[pcol].mean(),2),"PROJ",round(d.rb_fp_recxtd.mean(),2))
 # Team depth proxy from projected RB rank within team.
 m["depth"]=m.groupby("team").rb_fp_recxtd.rank(method="first",ascending=False);m["depthgrp"]=m.depth.map(lambda z:"RB1" if z==1 else ("RB2" if z==2 else "RB3+"))
 for lab,d in m.groupby("depthgrp"): print("depth",lab,"n",len(d),"MAE",round(d.ae.mean(),3),"BIAS",round(d.err.mean(),3),"ACT",round(d[pcol].mean(),2),"PROJ",round(d.rb_fp_recxtd.mean(),2))
 print("\nBIGGEST RB OVERPROJECTIONS")
 for _,r in m.sort_values("err",ascending=False).head(12).iterrows(): print(r.player,round(r.rb_fp_recxtd,2),round(r[pcol],2),round(r.err,2),r.team,round(r.carries,1),round(r.targets,1))
except Exception as ex:print("RB segment audit unavailable:",ex)

try:
 sw=pd.read_csv(OUT/"week2_projections.csv");sw=sw[sw.position=="RB"].copy();act=pd.read_csv(OUT/"week2_actuals.csv");namecol=next(x for x in ["player","player_name","player_display_name"] if x in act.columns);act["k"]=act[namecol].map(key);sw["k"]=sw.player.map(key);pcol=next(x for x in ["ppr_actual","fantasy_points_ppr","ppr"] if x in act.columns);mm=sw.merge(act[["k",pcol]],on="k");print("\nRB REC XTD HIGH-END COMPRESSION SWEEP")
 for col in ["rb_fp_recxtd","rb_fp_recxtd_hi_comp_5","rb_fp_recxtd_hi_comp_10","rb_fp_recxtd_hi_comp_12","rb_fp_recxtd_hi_comp_14","rb_fp_recxtd_hi_comp_15","rb_fp_recxtd_hi_comp_16","rb_fp_recxtd_hi_comp_18","rb_fp_recxtd_hi_comp_20"]:
  e=mm[col]-mm[pcol];ae=e.abs();print(col,"n",len(e),"MAE",round(ae.mean(),3),"BIAS",round(e.mean(),3),"+/-1",round(100*(ae<=1).mean(),2),"+/-3",round(100*(ae<=3).mean(),2),"+/-6",round(100*(ae<=6).mean(),2))
except Exception as ex:print("RB high-end compression grading unavailable:",ex)

try:
 sw=pd.read_csv(OUT/"week2_projections.csv");sw=sw[sw.position=="RB"].copy();act=pd.read_csv(OUT/"week2_actuals.csv");namecol=next(x for x in ["player","player_name","player_display_name"] if x in act.columns);act["k"]=act[namecol].map(key);sw["k"]=sw.player.map(key);pcol=next(x for x in ["ppr_actual","fantasy_points_ppr","ppr"] if x in act.columns);mm=sw.merge(act[["k",pcol]],on="k");print("\nRB LEADER + EXPLOSIVE15 SWEEP")
 base=mm.rb_fp_recxtd.where(~((mm.rb_fp_recxtd>=13)&((mm.carries+mm.targets)>=16)),mm.rb_fp_recxtd*.84);mm["rb_hi16_control"]=base
 for col in ["rb_hi16_control","rb_fp_recxtd_hi16_expl_5","rb_fp_recxtd_hi16_expl_10","rb_fp_recxtd_hi16_expl_15","rb_fp_recxtd_hi16_expl_20"]:
  z=mm.dropna(subset=[col]);e=z[col]-z[pcol];ae=e.abs();print(col,"n",len(e),"MAE",round(ae.mean(),3),"BIAS",round(e.mean(),3),"+/-1",round(100*(ae<=1).mean(),2),"+/-3",round(100*(ae<=3).mean(),2),"+/-6",round(100*(ae<=6).mean(),2))
except Exception as ex:print("RB explosive15 grading unavailable:",ex)

try:
 sw=pd.read_csv(OUT/"week2_projections.csv");sw=sw[sw.position=="RB"].copy();act=pd.read_csv(OUT/"week2_actuals.csv");namecol=next(x for x in ["player","player_name","player_display_name"] if x in act.columns);act["k"]=act[namecol].map(key);sw["k"]=sw.player.map(key);pcol=next(x for x in ["ppr_actual","fantasy_points_ppr","ppr"] if x in act.columns);m=sw.merge(act[["k",pcol]],on="k");base=m.rb_fp_recxtd.where(~((m.rb_fp_recxtd>=13)&((m.carries+m.targets)>=16)),m.rb_fp_recxtd*.84);m["rb_hi16_control"]=base;cols=["rb_hi16_control","rb_fp_recxtd_hi16_expl_10","rb_fp_recxtd_hi16_expl_12","rb_fp_recxtd_hi16_expl_15","rb_fp_recxtd_hi16_expl_17","rb_fp_recxtd_hi16_expl_20","rb_fp_recxtd_hi16_expl_22","rb_fp_recxtd_hi16_expl_25","rb_fp_recxtd_hi16_expl_27","rb_fp_recxtd_hi16_expl_30","rb_fp_recxtd_hi16_expl_35","rb_fp_recxtd_hi16_expl_40"];z=m.dropna(subset=cols).copy();print("\nRB EXPLOSIVE15 MATCHED-SAMPLE SWEEP","n",len(z))
 for col in cols:
  e=z[col]-z[pcol];ae=e.abs();print(col,"MAE",round(ae.mean(),3),"BIAS",round(e.mean(),3),"+/-1",round(100*(ae<=1).mean(),2),"+/-3",round(100*(ae<=3).mean(),2),"+/-6",round(100*(ae<=6).mean(),2))
except Exception as ex:print("RB matched explosive grading unavailable:",ex)
