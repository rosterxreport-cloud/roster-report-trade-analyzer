#!/usr/bin/env python3
"""Reconcile 2026 projection opportunity without hand-adjusting individual players.

Goals:
- Preserve demonstrated per-game opportunity for established players.
- Prevent depth-chart status from creating unrealistic volume explosions.
- Keep starting-QB attempts anchored to both team environment and historical pace.
- Constrain tracked fantasy-player targets/carries to plausible team totals.
- Recalculate fantasy points/ranks after volume changes.

This is a projection-only layer. It does not alter live trade-analyzer values.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

GAMES=17.0


def num(v, default=np.nan):
    try:
        x=float(v)
        return x if np.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def scoring(r, reception_points):
    def x(k): return num(r.get(k),0.0)
    return (
        .04*x("projected_passing_yards") + 4*x("projected_passing_tds") - 2*x("projected_interceptions")
        + .10*x("projected_rushing_yards") + 6*x("projected_rushing_tds")
        + reception_points*x("projected_receptions") + .10*x("projected_receiving_yards")
        + 6*x("projected_receiving_tds")
    )


def blend(a,b,w_a=.60):
    fa=np.isfinite(a); fb=np.isfinite(b)
    if fa and fb:return w_a*a+(1-w_a)*b
    if fa:return a
    if fb:return b
    return np.nan


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stats",type=Path,default=Path("data/projections/stat_projections_2026.csv"))
    ap.add_argument("--roles",type=Path,default=Path("data/projections/player_role_context_2026.csv"))
    ap.add_argument("--out",type=Path,default=Path("data/projections/stat_projections_2026.csv"))
    a=ap.parse_args()

    stats=pd.read_csv(a.stats)
    roles=pd.read_csv(a.roles)
    keep=[c for c in ["name","position","team_2026","targets_per_game","carries_per_game","attempts_per_game",
        "role_target_share_2026","role_carry_share_2026","role_qb_attempt_share_2026","projected_pass_attempts",
        "projected_rush_attempts","depth_starter","depth_rank","role_confidence","changed_team"] if c in roles.columns]
    r=roles[keep].copy().rename(columns={"team_2026":"role_team"})
    m=stats.merge(r,on=["name","position"],how="left",suffixes=("","_role"))

    modeled=m["projection_status"].eq("modeled_veteran")
    eligible=m["projection_status"].isin(["modeled_veteran","returning_fallback","rookie_model"])

    # 1) Starting QB volume: use team share and demonstrated attempts/game together.
    for idx,row in m[modeled & m["position"].eq("QB")].iterrows():
        team_pass=num(row.get("projected_pass_attempts_role"),num(row.get("projected_pass_attempts"),np.nan))
        share=num(row.get("role_qb_attempt_share_2026"),.97)
        share_based=team_pass*np.clip(share,.50,.99) if np.isfinite(team_pass) else np.nan
        hist_pg=num(row.get("attempts_per_game"),np.nan)
        hist_full=hist_pg*GAMES if np.isfinite(hist_pg) else np.nan
        starter=bool(row.get("depth_starter",False))
        if starter:
            new_att=blend(hist_full,share_based,.62)
            if np.isfinite(hist_full):new_att=max(new_att,.82*hist_full)
            if np.isfinite(team_pass):new_att=min(new_att,.99*team_pass)
        else:new_att=share_based
        old=num(row.get("projected_pass_attempts"),np.nan)
        if np.isfinite(new_att) and np.isfinite(old) and old>0:
            ratio=new_att/old
            m.at[idx,"projected_pass_attempts"]=new_att
            for c in ["projected_passing_yards","projected_passing_tds","projected_interceptions"]:
                m.at[idx,c]=num(row.get(c),0)*ratio

    # 2) RB/WR/TE targets: demonstrated targets/game is the main prior; team share is the context prior.
    for idx,row in m[modeled & m["position"].isin(["RB","WR","TE"])].iterrows():
        team_pass=num(row.get("projected_pass_attempts_role"),np.nan)
        share=num(row.get("role_target_share_2026"),np.nan)
        share_targets=team_pass*share if np.isfinite(team_pass) and np.isfinite(share) else np.nan
        hist_pg=num(row.get("targets_per_game"),np.nan)
        hist_targets=hist_pg*GAMES if np.isfinite(hist_pg) else np.nan
        changed=bool(row.get("changed_team",False))
        new_targets=blend(hist_targets,share_targets,.58 if changed else .68)
        old=num(row.get("projected_targets"),np.nan)
        if not np.isfinite(new_targets) or not np.isfinite(old) or old<=0:continue
        if np.isfinite(hist_targets):
            new_targets=min(new_targets,hist_targets*(1.22 if changed else 1.15))
            if hist_pg>=7.0:new_targets=max(new_targets,hist_targets*.92)
            elif hist_pg>=5.5:new_targets=max(new_targets,hist_targets*.88)
        ratio=new_targets/old
        m.at[idx,"projected_targets"]=new_targets
        for c in ["projected_receptions","projected_receiving_yards","projected_receiving_tds"]:
            m.at[idx,c]=num(row.get(c),0)*ratio

    # 3) RB carries: same principle, with a slightly tighter expansion cap.
    for idx,row in m[modeled & m["position"].eq("RB")].iterrows():
        team_rush=num(row.get("projected_rush_attempts_role"),np.nan)
        share=num(row.get("role_carry_share_2026"),np.nan)
        share_carries=team_rush*share if np.isfinite(team_rush) and np.isfinite(share) else np.nan
        hist_pg=num(row.get("carries_per_game"),np.nan)
        hist_carries=hist_pg*GAMES if np.isfinite(hist_pg) else np.nan
        new_carries=blend(hist_carries,share_carries,.65)
        old=num(row.get("projected_rush_attempts"),np.nan)
        if not np.isfinite(new_carries) or not np.isfinite(old) or old<=0:continue
        if np.isfinite(hist_carries):
            new_carries=min(new_carries,hist_carries*(1.18 if bool(row.get("changed_team",False)) else 1.12))
            if hist_pg>=12:new_carries=max(new_carries,hist_carries*.90)
        ratio=new_carries/old
        m.at[idx,"projected_rush_attempts"]=new_carries
        for c in ["projected_rushing_yards","projected_rushing_tds"]:
            m.at[idx,c]=num(row.get(c),0)*ratio

    # 4) Team reconciliation: count every projected fantasy player, including rookies.
    for team,g in m[eligible].groupby("team"):
        team_roles=roles[roles["team_2026"].eq(team)] if "team_2026" in roles.columns else pd.DataFrame()
        team_pass=num(team_roles["projected_pass_attempts"].dropna().iloc[0],np.nan) if len(team_roles) and "projected_pass_attempts" in team_roles and team_roles["projected_pass_attempts"].notna().any() else np.nan
        team_rush=num(team_roles["projected_rush_attempts"].dropna().iloc[0],np.nan) if len(team_roles) and "projected_rush_attempts" in team_roles and team_roles["projected_rush_attempts"].notna().any() else np.nan
        skill_idx=g[g["position"].isin(["RB","WR","TE"])].index
        total_targets=pd.to_numeric(m.loc[skill_idx,"projected_targets"],errors="coerce").sum()
        target_budget=team_pass*.96 if np.isfinite(team_pass) else np.nan
        if np.isfinite(target_budget) and total_targets>target_budget and total_targets>0:
            scale=target_budget/total_targets
            for idx in skill_idx:
                for c in ["projected_targets","projected_receptions","projected_receiving_yards","projected_receiving_tds"]:
                    if np.isfinite(num(m.at[idx,c],np.nan)):m.at[idx,c]=num(m.at[idx,c],0)*scale
        rb_idx=g[g["position"].eq("RB")].index
        total_rb_carries=pd.to_numeric(m.loc[rb_idx,"projected_rush_attempts"],errors="coerce").sum()
        rb_budget=team_rush*.86 if np.isfinite(team_rush) else np.nan
        if np.isfinite(rb_budget) and total_rb_carries>rb_budget and total_rb_carries>0:
            scale=rb_budget/total_rb_carries
            for idx in rb_idx:
                for c in ["projected_rush_attempts","projected_rushing_yards","projected_rushing_tds"]:
                    if np.isfinite(num(m.at[idx,c],np.nan)):m.at[idx,c]=num(m.at[idx,c],0)*scale

    # Recalculate scoring and ranks.
    for idx,row in m[eligible].iterrows():
        d=row.to_dict()
        m.at[idx,"ppr_points"]=scoring(d,1.0)
        m.at[idx,"half_ppr_points"]=scoring(d,.5)
        m.at[idx,"standard_points"]=scoring(d,0.0)
        m.at[idx,"ppr_per_game"]=m.at[idx,"ppr_points"]/GAMES
        m.at[idx,"half_ppr_per_game"]=m.at[idx,"half_ppr_points"]/GAMES
        m.at[idx,"standard_per_game"]=m.at[idx,"standard_points"]/GAMES
    for fmt in ["ppr_points","half_ppr_points","standard_points"]:
        m[fmt.replace("_points","_overall_rank")]=m[fmt].rank(method="min",ascending=False)
        poscol=fmt.replace("_points","_pos_rank");m[poscol]=np.nan
        for pos in ["QB","RB","WR","TE"]:
            mask=m["position"].eq(pos)&m[fmt].notna();m.loc[mask,poscol]=m.loc[mask,fmt].rank(method="min",ascending=False)

    drop=[c for c in m.columns if c.endswith("_role") or c in {"role_team","targets_per_game","carries_per_game","attempts_per_game","role_target_share_2026","role_carry_share_2026","role_qb_attempt_share_2026","depth_starter","depth_rank","role_confidence","changed_team","projected_pass_attempts_role","projected_rush_attempts_role"}]
    m=m.drop(columns=drop,errors="ignore")
    nums=m.select_dtypes(include=[np.number]).columns;m[nums]=m[nums].round(2)
    m.to_csv(a.out,index=False)
    watch=["Lamar Jackson","Breece Hall","Drake London","Brock Bowers","Juwan Johnson"]
    cols=[c for c in ["name","position","ppr_points","ppr_pos_rank","projected_pass_attempts","projected_targets","projected_rush_attempts"] if c in m.columns]
    print(m[m["name"].isin(watch)][cols].sort_values("position").to_dict("records"))
    print(f"Wrote reconciled projections to {a.out}")

if __name__=="__main__":main()
