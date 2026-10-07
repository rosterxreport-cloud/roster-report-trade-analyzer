import base64,gzip,json,io,re
import pandas as pd, numpy as np
BLOB="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"
base=json.loads(gzip.decompress(base64.b64decode(BLOB)))
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.parquet"
w=pd.read_parquet(URL)
w=w[(w["season_type"]=="REG") & (w["week"].isin([1,2,3,4]))].copy()
namecol="player_display_name"
def norm(x):
 return re.sub(r'[^a-z0-9]','',str(x).lower().replace('iii','').replace('jr.','').replace('jr',''))
w["key"]=w[namecol].map(norm)
rows=[]
for pos,items in base.items():
 b=pd.DataFrame(items); b["key"]=b.Player.map(norm)
 for _,r in b.iterrows():
  hist=w[(w.key==r.key)&(w.week<=3)]
  act=w[(w.key==r.key)&(w.week==4)]
  if act.empty: continue
  actual=float(act.iloc[0].get("fantasy_points_ppr",act.iloc[0].get("fantasy_points",0)) or 0)
  old=float(r["baseline_fp"]); mult=1.0
  if pos=="QB":
   avg=hist["attempts"].fillna(0).mean() if len(hist) else np.nan
   ratio=avg/float(r["Pass Att"]) if np.isfinite(avg) and r["Pass Att"] else 1
   mult=float(np.clip(1+.20*(ratio-1),.88,1.12))
  elif pos=="RB":
   avgc=hist["carries"].fillna(0).mean() if len(hist) else np.nan
   avgt=hist["targets"].fillna(0).mean() if len(hist) else np.nan
   oldopp=float(r["Carries"])+1.5*float(r["Targets"])
   newopp=avgc+1.5*avgt if np.isfinite(avgc) and np.isfinite(avgt) else oldopp
   ratio=newopp/oldopp if oldopp else 1
   mult=float(np.clip(1+.26*(ratio-1),.76,1.30))
  else:
   avgt=hist["targets"].fillna(0).mean() if len(hist) else np.nan
   ratio=avgt/float(r["Targets"]) if np.isfinite(avgt) and r["Targets"] else 1
   mult=float(np.clip(1+.28*(ratio-1),.78,1.28))
  new=old*mult
  rows.append(dict(position=pos,player=r.Player,baseline=old,v3=new,actual=actual,baseline_abs_error=abs(old-actual),v3_abs_error=abs(new-actual),multiplier=mult))
out=pd.DataFrame(rows)
out.to_csv("data/backtests/week4_v3_results.csv",index=False)
summary=[]
summary.append("# Week 4 V3 Backtest\n")
summary.append("Inputs: frozen Week 3 formula-scored Roster Report projections; nflverse Weeks 1-3 opportunity; nflverse Week 4 actual PPR.\n")
summary.append("| Position | N | Baseline MAE | V3 MAE | Change | Winner |\n|---|---:|---:|---:|---:|---|")
for pos,g in out.groupby("position"):
 a=g.baseline_abs_error.mean();v=g.v3_abs_error.mean();delta=v-a
 summary.append(f"| {pos} | {len(g)} | {a:.3f} | {v:.3f} | {delta:+.3f} | {'V3' if v<a else 'Baseline'} |")
summary.append("\nV3 is promoted position-by-position only when it lowers MAE on the identical sample.")
open("data/backtests/week4_v3_summary.md","w").write("\n".join(summary)+"\n")
print("\n".join(summary))
