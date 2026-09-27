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
# Simple one-variable screening against Week 2 actual FP. This is diagnostic, not final fitting.
# Rank by absolute correlation and report sample coverage; small Week 1->2 sample means we avoid overfitting.
screen=[]
for col in [x for x in o.columns if x.startswith("w1_")]:
 x=pd.to_numeric(o[col],errors="coerce");y=pd.to_numeric(o["w2_actual_fp"],errors="coerce");z=x.notna()&y.notna()
 if z.sum()>=10:
  screen.append({"feature":col,"n":int(z.sum()),"corr_to_next_week_fp":round(float(x[z].corr(y[z])),4)})
s=pd.DataFrame(screen);s["abs_corr"]=s.corr_to_next_week_fp.abs();s=s.sort_values("abs_corr",ascending=False)
s.to_csv("data/qb-week1-feature-screen.csv",index=False)
print("Matched QBs:",len(o));print("Passing features:",features);print("XFP present:",any("XFP" in c.upper() for c in o.columns));print("\nTOP QB SIGNALS\n",s.head(20).to_string(index=False))


# Candidate QB composite screen. Standardize Week 1 signals and test combinations
# against Week 2 actual fantasy points; rushing is sourced only from nflverse.
def z(s):
 s=pd.to_numeric(s,errors="coerce"); sd=s.std()
 return (s-s.mean())/(sd if sd and np.isfinite(sd) else 1)
cand={}
def add(name, parts):
 vals=pd.Series(0.,index=o.index); used=0
 for col,wt in parts:
  if col in o:
   vals=vals+z(o[col]).fillna(0)*wt;used+=1
 if used:cand[name]=vals
add("pressure_escape",[("w1_P2S %",-1),("w1_SACK %",-1),("w1_TTS",1)])
add("pressure_plus_hero",[("w1_P2S %",-1),("w1_SACK %",-1),("w1_HERO %",.6)])
add("accuracy_efficiency",[("w1_CPOE",1),("w1_ADJ CMP %",.7),("w1_EPA/DB",1),("w1_ANY/A",.7)])
add("balanced_pass",[("w1_P2S %",-1),("w1_SACK %",-0.6),("w1_CPOE",.6),("w1_EPA/DB",.8),("w1_HERO %",.35)])
# nflverse rushing fantasy contribution from Week 1
rushfp=pd.Series(0.,index=o.index)
if "w1_rush_rushing_yards" in o:rushfp += pd.to_numeric(o["w1_rush_rushing_yards"],errors="coerce").fillna(0)/10
if "w1_rush_rushing_tds" in o:rushfp += pd.to_numeric(o["w1_rush_rushing_tds"],errors="coerce").fillna(0)*6
cand["rushing_only"]=z(rushfp)
if "balanced_pass" in cand:cand["balanced_plus_rush"]=cand["balanced_pass"]+.65*z(rushfp)
y=pd.to_numeric(o["w2_actual_fp"],errors="coerce")
out=[]
for name,v in cand.items():
 q=v.notna()&y.notna()
 out.append({"model":name,"n":int(q.sum()),"corr":float(v[q].corr(y[q]))})
pd.DataFrame(out).sort_values("corr",ascending=False).to_csv("data/qb-composite-screen.csv",index=False)
print("\nQB COMPOSITE SCREEN\n",pd.DataFrame(out).sort_values("corr",ascending=False).to_string(index=False))


# QB architecture v1: volume stability + pressure avoidance + rushing opportunity.
# Efficiency/accuracy enter only as small modifiers until larger out-of-sample evidence supports more.
arch=[]
def Z(col):
 return z(o[col]).fillna(0) if col in o else pd.Series(0.,index=o.index)
volume=(Z("w1_DB")+Z("w1_ATT"))/2
pressure=(-Z("w1_P2S %")-Z("w1_SACK %"))/2
rushopp=Z("w1_rush_carries")
eff=(Z("w1_EPA/DB")+Z("w1_ANY/A")+Z("w1_CPOE"))/3
hero=Z("w1_HERO %")
for vw,pw,rw,ew,hw in [
 (.45,.25,.25,.05,0),(.40,.25,.30,.05,0),(.40,.30,.25,.05,0),
 (.40,.25,.25,.05,.05),(.35,.30,.30,.05,0),(.45,.20,.30,.05,0)]:
 score=vw*volume+pw*pressure+rw*rushopp+ew*eff+hw*hero
 q=score.notna()&y.notna()
 arch.append({"volume":vw,"pressure":pw,"rush":rw,"efficiency":ew,"hero":hw,"n":int(q.sum()),"corr":float(score[q].corr(y[q]))})
aa=pd.DataFrame(arch).sort_values("corr",ascending=False)
aa.to_csv("data/qb-architecture-v1.csv",index=False)
print("\nQB ARCHITECTURE V1\n",aa.to_string(index=False))


# QB v1 local refinement around 40/25/25/5/5.
tune=[]
for vw in [.35,.375,.40,.425,.45]:
 for pw in [.20,.225,.25,.275,.30]:
  rw=.25; ew=.05; hw=1-vw-pw-rw-ew
  if hw < 0 or hw > .10: continue
  score=vw*volume+pw*pressure+rw*rushopp+ew*eff+hw*hero
  q=score.notna()&y.notna()
  tune.append({"volume":vw,"pressure":pw,"rush":rw,"efficiency":ew,"hero":round(hw,3),"n":int(q.sum()),"corr":float(score[q].corr(y[q]))})
tt=pd.DataFrame(tune).sort_values("corr",ascending=False)
tt.to_csv("data/qb-v1-weight-refinement.csv",index=False)
print("\nQB V1 WEIGHT REFINEMENT\n",tt.head(20).to_string(index=False))


# Advanced Passing Score sweep — explicitly excludes pressure-to-sack rate (P2S%).
# Components: accuracy, efficiency, high-end throws, turnover risk, depth/aggression,
# pressure environment, and timing/style.
adv_parts=[
 ("w1_CPOE",1.0),("w1_ADJ CMP %",.75),("w1_EPA/DB",1.0),("w1_ANY/A",.75),
 ("w1_HERO %",.60),("w1_TWT %",-0.60),("w1_DEEP %",.45),("w1_ADOT",.35),
 ("w1_ACC %",.75),("w1_PRESS %",-0.25),("w1_TTT",-0.20),("w1_TTS",.25)
]
adv=pd.Series(0.,index=o.index);den=0.
for col,wt in adv_parts:
 if col in o:
  adv += wt*Z(col);den += abs(wt)
adv=adv/(den or 1)
# Keep core volume/rushing; test advanced layer at 10-30%.
advtests=[]
for aw in [.10,.15,.20,.25,.30]:
 remaining=1-aw
 # Preserve 40:25 volume:rushing relationship in non-advanced share.
 vw=remaining*(40/65);rw=remaining*(25/65)
 score=vw*volume+rw*rushopp+aw*adv
 q=score.notna()&y.notna()
 advtests.append({"advanced":aw,"volume":round(vw,4),"rush":round(rw,4),"P2S_weight":0,"n":int(q.sum()),"corr":float(score[q].corr(y[q]))})
at=pd.DataFrame(advtests).sort_values("corr",ascending=False)
at.to_csv("data/qb-advanced-passing-no-p2s-sweep.csv",index=False)
print("\nQB ADVANCED PASSING — NO P2S%\n",at.to_string(index=False))


# Extend no-P2S advanced passing sweep beyond 30% to locate peak.
ext=[]
for aw in [.30,.35,.40,.45,.50,.55,.60]:
 remaining=1-aw
 vw=remaining*(40/65);rw=remaining*(25/65)
 score=vw*volume+rw*rushopp+aw*adv
 q=score.notna()&y.notna()
 ext.append({"advanced":aw,"volume":round(vw,4),"rush":round(rw,4),"P2S_weight":0,"n":int(q.sum()),"corr":float(score[q].corr(y[q]))})
et=pd.DataFrame(ext).sort_values("corr",ascending=False)
et.to_csv("data/qb-advanced-passing-no-p2s-extended.csv",index=False)
print("\nQB ADVANCED PASSING EXTENDED — NO P2S%\n",et.to_string(index=False))
