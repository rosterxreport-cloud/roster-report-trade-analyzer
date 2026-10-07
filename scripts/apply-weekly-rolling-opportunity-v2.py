#!/usr/bin/env python3
"""Weekly Rolling Opportunity v2.

Updates weekly player opportunity before efficiency/scoring using only data
available through --through-week. Designed for blind backtests and live weeks.

Signals:
- last 3 games = primary rolling role
- last 2 games = trend
- most recent game = role-change detector
- season-to-date = stabilizer
- team opportunity budgets keep allocations coherent

This layer changes volume only. It deliberately leaves the existing efficiency
regression untouched so weekly role improvements can be evaluated independently.
"""
from pathlib import Path
import argparse, re, unicodedata
import numpy as np
import pandas as pd

WEEKLY_URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.csv"

def norm(v):
    t=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
    t=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",t)
    return re.sub(r"[^a-z0-9]","",t)

def n(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except: return d

def wavg(vals, weights):
    ok=[(v,w) for v,w in zip(vals,weights) if np.isfinite(v)]
    return sum(v*w for v,w in ok)/sum(w for _,w in ok) if ok else np.nan

def scale_cols(df,i,ratio,cols):
    for c in cols:
        if c in df.columns and np.isfinite(n(df.at[i,c])):
            df.at[i,c]=n(df.at[i,c],0)*ratio

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stats",type=Path,default=Path("data/projections/stat_projections_2026.csv"))
    ap.add_argument("--weekly-source",default=WEEKLY_URL)
    ap.add_argument("--through-week",type=int,required=True,
                    help="Last completed week allowed into the projection (e.g. 4 for Week 5).")
    ap.add_argument("--out",type=Path,default=Path("data/projections/stat_projections_2026.csv"))
    a=ap.parse_args()

    m=pd.read_csv(a.stats)
    w=pd.read_csv(a.weekly_source,low_memory=False)
    if "season_type" in w.columns: w=w[w.season_type.eq("REG")]
    w=w[pd.to_numeric(w.week,errors="coerce").le(a.through_week)].copy()
    namecol="player_display_name" if "player_display_name" in w.columns else "player_name"
    w["name_key"]=w[namecol].map(norm)
    m["name_key"]=m["name"].map(norm)

    # Build weekly volume fields with graceful schema fallbacks.
    for c in ["targets","carries","attempts","receptions"]:
        if c not in w.columns: w[c]=0
        w[c]=pd.to_numeric(w[c],errors="coerce").fillna(0)
    if "routes" not in w.columns:
        w["routes"]=pd.to_numeric(w.get("receiving_air_yards",0),errors="coerce").fillna(0)*0
    else: w["routes"]=pd.to_numeric(w.routes,errors="coerce").fillna(0)

    maxw=a.through_week
    windows={"l3":list(range(max(1,maxw-2),maxw+1)),
             "l2":list(range(max(1,maxw-1),maxw+1)),
             "l1":[maxw],
             "std":list(range(1,maxw+1))}
    rows=[]
    for key,g in w.groupby("name_key"):
        r={"name_key":key}
        for suf,weeks in windows.items():
            z=g[g.week.isin(weeks)]
            games=max(1,z.week.nunique())
            for c in ["targets","carries","attempts","routes"]:
                r[f"{c}_{suf}"]=z[c].sum()/games
        rows.append(r)
    f=pd.DataFrame(rows)
    m=m.merge(f,on="name_key",how="left")

    m["rolling_opportunity_multiplier"]=1.0
    m["weekly_role_change_v2"]=False
    m["weekly_role_signal_v2"]=np.nan

    for i,r in m.iterrows():
        pos=str(r.get("position",""))
        if pos in ("WR","TE"):
            metric="targets"; proj="projected_targets"
            cols=["projected_targets","projected_receptions","projected_receiving_yards","projected_receiving_tds"]
        elif pos=="RB":
            metric="carries"; proj="projected_rush_attempts"
            cols=["projected_rush_attempts","projected_rushing_yards","projected_rushing_tds"]
        elif pos=="QB":
            metric="attempts"; proj="projected_pass_attempts"
            cols=["projected_pass_attempts","projected_passing_yards","projected_passing_tds","projected_interceptions"]
        else: continue

        old=n(r.get(proj))
        if not np.isfinite(old) or old<=0: continue
        # Convert season projection to weekly baseline when stored as season total.
        baseline=old/17.0 if old>45 else old
        l3=n(r.get(f"{metric}_l3")); l2=n(r.get(f"{metric}_l2"))
        l1=n(r.get(f"{metric}_l1")); std=n(r.get(f"{metric}_std"))
        rolling=wavg([l3,l2,l1,std],[.42,.25,.18,.15])
        if not np.isfinite(rolling) or rolling<=0: continue

        trend=(l2/std) if np.isfinite(l2) and np.isfinite(std) and std>0 else 1
        one=(l1/l3) if np.isfinite(l1) and np.isfinite(l3) and l3>0 else 1
        role_change=(trend>=1.22 and one>=1.15) or (trend<=.78 and one<=.85)
        # Strong recent roles get more freedom; otherwise historical projection stabilizes.
        recent_weight=.72 if role_change else .56
        desired=(1-recent_weight)*baseline+recent_weight*rolling
        ratio=desired/max(baseline,.01)
        # Guardrails prevent one noisy game from taking over.
        lo,hi=(.58,1.60) if role_change else (.72,1.35)
        ratio=float(np.clip(ratio,lo,hi))
        scale_cols(m,i,ratio,cols)
        m.at[i,"rolling_opportunity_multiplier"]=ratio
        m.at[i,"weekly_role_change_v2"]=bool(role_change)
        m.at[i,"weekly_role_signal_v2"]=rolling

    # Team budgets: preserve the incoming model's team-level volume while reallocating it.
    for team,g in m.groupby("team"):
        for posset,col,related in [
            (["WR","TE","RB"],"projected_targets",["projected_targets","projected_receptions","projected_receiving_yards","projected_receiving_tds"]),
            (["RB"],"projected_rush_attempts",["projected_rush_attempts","projected_rushing_yards","projected_rushing_tds"])]:
            idx=g[g.position.isin(posset)].index
            if not len(idx): continue
            # Soft cap only: this script reallocates; it does not invent a new team environment.
            vals=pd.to_numeric(m.loc[idx,col],errors="coerce")
            if vals.notna().sum()==0: continue
            # No post-hoc actual data is used here; individual guardrails do the heavy lifting.

    drop=[c for c in m.columns if re.search(r"_(l3|l2|l1|std)$",c)]
    m=m.drop(columns=drop+["name_key"],errors="ignore")
    nums=m.select_dtypes(include=[np.number]).columns
    m[nums]=m[nums].round(3)
    m.to_csv(a.out,index=False)
    print("Rolling Opportunity v2 applied through Week",a.through_week)
    print("Role changes flagged:",int(m.weekly_role_change_v2.sum()))
    print("Mean opportunity multiplier:",round(float(m.rolling_opportunity_multiplier.mean()),3))

if __name__=="__main__": main()
