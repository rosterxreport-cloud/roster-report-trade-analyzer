#!/usr/bin/env python3
"""Adjust 2026 WR/TE receiving efficiency for changes in quarterback environment.

The base projection already determines player talent, targets and team opportunity.
This layer does NOT add targets. It compares the current starting QB's weighted
2023-25 passing quality with the receiver's 2025 team QB environment, then applies
a conservative, capped adjustment to catch rate, yards/target and receiving TD rate.

This is projection-only and never writes live trade-analyzer values.
"""
from __future__ import annotations
import argparse, re, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

SEASON_W={2023:.20,2024:.30,2025:.50}
METRICS=["completion_rate","pass_yards_per_attempt","passing_epa_per_attempt","pass_td_rate"]
METRIC_W={"completion_rate":.30,"pass_yards_per_attempt":.25,"passing_epa_per_attempt":.30,"pass_td_rate":.15}
CATCH_PER_SD=.025
YPT_PER_SD=.035
TD_PER_SD=.060
MAX_DELTA=1.50
TEAM_ALIAS={"JAX":"JAC","LA":"LAR"}
# Verified current starters used only when the generated role/depth table is missing
# an otherwise confirmed QB starter. This prevents a whole receiving room from
# silently bypassing QB-environment adjustment because of an upstream depth omission.
STARTER_OVERRIDES={"PIT":"Aaron Rodgers"}
GAMES=17.0


def norm_name(v):
    t=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
    t=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",t)
    return re.sub(r"[^a-z0-9]","",t)


def num(v,default=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else default
    except (TypeError,ValueError): return default


def points(r,rec=1.0):
    x=lambda k:num(r.get(k),0.0)
    return .04*x("projected_passing_yards")+4*x("projected_passing_tds")-2*x("projected_interceptions")+\
        .1*x("projected_rushing_yards")+6*x("projected_rushing_tds")+rec*x("projected_receptions")+\
        .1*x("projected_receiving_yards")+6*x("projected_receiving_tds")


def weighted_qb_score(q, player_name):
    key=norm_name(player_name)
    hist=q[q.name_key.eq(key)].copy()
    if hist.empty:return None
    hist["sw"]=hist.season.map(SEASON_W).fillna(0)
    good=hist.qb_env_score.notna() & hist.sw.gt(0)
    if not good.any():return None
    return float(np.average(hist.loc[good,"qb_env_score"],weights=hist.loc[good,"sw"]))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stats",type=Path,default=Path("data/projections/stat_projections_2026.csv"))
    ap.add_argument("--roles",type=Path,default=Path("data/projections/player_role_context_2026.csv"))
    ap.add_argument("--features",type=Path,default=Path("data/projections/player_features_2023_2025.csv"))
    ap.add_argument("--out",type=Path,default=Path("data/projections/stat_projections_2026.csv"))
    a=ap.parse_args()
    stats=pd.read_csv(a.stats); roles=pd.read_csv(a.roles); f=pd.read_csv(a.features)
    q=f[(f.position.eq("QB")) & (pd.to_numeric(f.get("attempts"),errors="coerce")>=50)].copy()
    for c in METRICS:q[c]=pd.to_numeric(q[c],errors="coerce")
    mu=q[METRICS].mean(); sd=q[METRICS].std().replace(0,np.nan)
    for c in METRICS:q[f"z_{c}"]=(q[c]-mu[c])/sd[c]
    q["qb_env_score"]=sum(METRIC_W[c]*q[f"z_{c}"] for c in METRICS)
    q["team_norm"]=q["recent_team"].replace(TEAM_ALIAS)
    q["name_key"]=q["player_display_name"].fillna(q.get("player_name","")).map(norm_name)

    prior={}
    for team,g in q[q.season.eq(2025)].groupby("team_norm"):
        w=pd.to_numeric(g["attempts"],errors="coerce").fillna(0)
        good=g["qb_env_score"].notna() & w.gt(0)
        if good.any():prior[team]=float(np.average(g.loc[good,"qb_env_score"],weights=w[good]))

    starters=roles[(roles.position.eq("QB")) & roles.get("depth_starter",False).fillna(False)].copy()
    current={}; starter_name={}
    for _,r in starters.iterrows():
        team=str(r.get("team_2026")); score=weighted_qb_score(q,r.get("name"))
        if score is None:continue
        current[team]=score; starter_name[team]=r.get("name")

    # Fill only unresolved teams from explicit, verified starter overrides.
    for team,name in STARTER_OVERRIDES.items():
        if team in current:continue
        score=weighted_qb_score(q,name)
        if score is not None:
            current[team]=score; starter_name[team]=name

    stats["qb_environment_delta"]=np.nan
    stats["qb_environment_starter"]=""
    stats["qb_environment_prior_score"]=np.nan
    stats["qb_environment_current_score"]=np.nan
    eligible=stats.projection_status.isin(["modeled_veteran","returning_fallback","rookie_model"])
    for idx,r in stats[eligible & stats.position.isin(["WR","TE"])].iterrows():
        team=str(r.get("team")); old=prior.get(team); new=current.get(team)
        if old is None or new is None:continue
        delta=float(np.clip(new-old,-MAX_DELTA,MAX_DELTA))
        stats.at[idx,"qb_environment_delta"]=delta
        stats.at[idx,"qb_environment_starter"]=starter_name.get(team,"")
        stats.at[idx,"qb_environment_prior_score"]=old
        stats.at[idx,"qb_environment_current_score"]=new
        stats.at[idx,"projected_receptions"]=num(r.get("projected_receptions"),0)*(1+CATCH_PER_SD*delta)
        stats.at[idx,"projected_receiving_yards"]=num(r.get("projected_receiving_yards"),0)*(1+YPT_PER_SD*delta)
        stats.at[idx,"projected_receiving_tds"]=num(r.get("projected_receiving_tds"),0)*(1+TD_PER_SD*delta)

    for idx,r in stats[eligible].iterrows():
        d=stats.loc[idx].to_dict()
        stats.at[idx,"ppr_points"]=points(d,1); stats.at[idx,"half_ppr_points"]=points(d,.5); stats.at[idx,"standard_points"]=points(d,0)
        stats.at[idx,"ppr_per_game"]=stats.at[idx,"ppr_points"]/GAMES
        stats.at[idx,"half_ppr_per_game"]=stats.at[idx,"half_ppr_points"]/GAMES
        stats.at[idx,"standard_per_game"]=stats.at[idx,"standard_points"]/GAMES
    for fmt in ["ppr_points","half_ppr_points","standard_points"]:
        stats[fmt.replace("_points","_overall_rank")]=stats[fmt].rank(method="min",ascending=False)
        pc=fmt.replace("_points","_pos_rank"); stats[pc]=np.nan
        for pos in ["QB","RB","WR","TE"]:
            mask=stats.position.eq(pos)&stats[fmt].notna(); stats.loc[mask,pc]=stats.loc[mask,fmt].rank(method="min",ascending=False)
    nums=stats.select_dtypes(include=[np.number]).columns; stats[nums]=stats[nums].round(3)
    stats.to_csv(a.out,index=False)
    watch=stats[stats.name.isin(["Justin Jefferson","CeeDee Lamb","Davante Adams","Ladd McConkey","Jameson Williams","DK Metcalf","Michael Pittman Jr."])]
    cols=["name","team","qb_environment_starter","qb_environment_delta","projected_targets","projected_receptions","projected_receiving_yards","projected_receiving_tds","ppr_points","ppr_pos_rank"]
    print(watch[cols].sort_values("ppr_pos_rank").to_dict("records"))
    print(f"QB environment teams resolved: {len(set(prior)&set(current))}")
    print(f"Wrote QB-environment-adjusted projections to {a.out}")

if __name__=="__main__":main()
