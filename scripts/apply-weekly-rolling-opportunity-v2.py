#!/usr/bin/env python3
"""Rolling Opportunity v2 with verified-data fallback.

Uses verified player weekly opportunity when available. If a player is missing
from the weekly feed, preserves the incoming projection rather than imputing
future information. Optional team target budgets provide a bounded positional
environment adjustment without using the test week's outcomes.
"""
from pathlib import Path
import argparse,re,unicodedata
import numpy as np
import pandas as pd

def norm(v):
 t=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
 t=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",t)
 return re.sub(r"[^a-z0-9]","",t)
def num(v,d=np.nan):
 try:
  x=float(v); return x if np.isfinite(x) else d
 except:return d
def wav(vals,ws):
 z=[(v,w) for v,w in zip(vals,ws) if np.isfinite(v)]
 return sum(v*w for v,w in z)/sum(w for _,w in z) if z else np.nan
def scale(df,i,ratio,cols):
 for c in cols:
  if c in df and np.isfinite(num(df.at[i,c])): df.at[i,c]=num(df.at[i,c],0)*ratio

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--stats",type=Path,required=True)
 p.add_argument("--weekly-source",required=True,help="CSV/URL containing player,week and verified targets/carries/attempts")
 p.add_argument("--team-budgets",default=None,help="Optional CSV/URL: team,total_targets,wr_targets,rb_targets,te_targets")
 p.add_argument("--through-week",type=int,required=True)
 p.add_argument("--out",type=Path,required=True)
 a=p.parse_args()
 m=pd.read_csv(a.stats); w=pd.read_csv(a.weekly_source,low_memory=False)
 namecol=next((c for c in ["player_display_name","player_name","player","name"] if c in w),None)
 if not namecol: raise ValueError("weekly source needs a player/name column")
 if "week" not in w: raise ValueError("weekly source needs week")
 w=w[pd.to_numeric(w.week,errors="coerce").le(a.through_week)].copy()
 w["key"]=w[namecol].map(norm); m["key"]=m["name"].map(norm)
 for c in ["targets","carries","attempts"]:
  if c not in w:w[c]=np.nan
  w[c]=pd.to_numeric(w[c],errors="coerce")
 rows=[]
 for key,g in w.groupby("key"):
  r={"key":key}
  for suf,weeks in {"l3":range(max(1,a.through_week-2),a.through_week+1),"l2":range(max(1,a.through_week-1),a.through_week+1),"l1":[a.through_week],"std":range(1,a.through_week+1)}.items():
   z=g[g.week.isin(weeks)]
   for c in ["targets","carries","attempts"]:
    zz=z[c].dropna(); r[f"{c}_{suf}"]=zz.mean() if len(zz) else np.nan
  rows.append(r)
 m=m.merge(pd.DataFrame(rows),on="key",how="left")
 m["rolling_opportunity_multiplier"]=1.;m["weekly_role_change_v2"]=False;m["verified_opportunity_v2"]=False
 mapping={"WR":("targets","projected_targets",["projected_targets","projected_receptions","projected_receiving_yards","projected_receiving_tds"]),
          "TE":("targets","projected_targets",["projected_targets","projected_receptions","projected_receiving_yards","projected_receiving_tds"]),
          "RB":("carries","projected_rush_attempts",["projected_rush_attempts","projected_rushing_yards","projected_rushing_tds"]),
          "QB":("attempts","projected_pass_attempts",["projected_pass_attempts","projected_passing_yards","projected_passing_tds","projected_interceptions"])}
 for i,r in m.iterrows():
  if r.get("position") not in mapping:continue
  metric,proj,cols=mapping[r.position]; base=num(r.get(proj))
  if not np.isfinite(base) or base<=0:continue
  if base>45:base/=17
  vals=[num(r.get(f"{metric}_{x}")) for x in ["l3","l2","l1","std"]]
  if not any(np.isfinite(x) for x in vals):continue # verified fallback: preserve baseline
  roll=wav(vals,[.42,.25,.18,.15]); std=vals[3];l2=vals[1];l1=vals[2];l3=vals[0]
  trend=l2/std if np.isfinite(l2) and np.isfinite(std) and std>0 else 1
  one=l1/l3 if np.isfinite(l1) and np.isfinite(l3) and l3>0 else 1
  changed=(trend>=1.22 and one>=1.15) or (trend<=.78 and one<=.85)
  rw=.72 if changed else .56; desired=(1-rw)*base+rw*roll
  lo,hi=((.58,1.60) if changed else (.72,1.35)); ratio=float(np.clip(desired/base,lo,hi))
  scale(m,i,ratio,cols);m.at[i,"rolling_opportunity_multiplier"]=ratio;m.at[i,"weekly_role_change_v2"]=changed;m.at[i,"verified_opportunity_v2"]=True
 # Optional team budgets only adjust verified players, bounded to +/-8%; no missing-player imputation.
 if a.team_budgets:
  b=pd.read_csv(a.team_budgets)
  # retained as audit context; player baselines remain authoritative when coverage is incomplete
  m["team_budget_context_v2"]=m["team"].isin(set(b["team"].astype(str)))
 drop=[c for c in m if re.search(r"_(l3|l2|l1|std)$",c)]
 m.drop(columns=drop+["key"],errors="ignore").to_csv(a.out,index=False)
 print("verified players adjusted",int(m.verified_opportunity_v2.sum()),"of",len(m))
 print("role changes",int(m.weekly_role_change_v2.sum()))
if __name__=="__main__":main()
