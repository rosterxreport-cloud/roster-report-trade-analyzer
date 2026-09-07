#!/usr/bin/env python3
"""Merge latest nflverse 2026 depth charts into fantasy role context.

The latest depth-chart snapshot is also used as an identity/team integrity check. If a
fantasy player has one unique current NFL depth-chart team and players.json carries a
different team, the role context is corrected before any backfield grouping occurs.
This prevents stale transactions from creating fake committees.
"""
from __future__ import annotations
import argparse,re,unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

DEPTH_URL="https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.csv"
TEAM_ALIASES={"LAR":"LA","STL":"LA","JAC":"JAX","WSH":"WAS","OAK":"LV","SD":"LAC"}
DEF_RE=r"(?:^|/)(?:CB|LCB|RCB|DB|S|FS|SS|NB|NCB)(?:$|/)"

def norm_name(v):
    t=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
    t=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",t)
    return re.sub(r"[^a-z0-9]","",t)

def norm_team(v):
    if pd.isna(v):return None
    t=str(v).strip().upper();return TEAM_ALIASES.get(t,t)

def offensive_match(pos,abb):
    a=str(abb or "").upper()
    if pos=="WR":return "WR" in a
    if pos=="RB":return any(x in a for x in ["RB","HB","FB"])
    if pos=="TE":return "TE" in a
    if pos=="QB":return "QB" in a
    return False

def latest_depth(source):
    d=pd.read_csv(source,low_memory=False)
    if "dt" not in d:raise RuntimeError(f"Unexpected depth-chart schema: {list(d.columns)}")
    d["dt_parsed"]=pd.to_datetime(d["dt"],errors="coerce",utc=True); newest=d["dt_parsed"].max()
    if pd.isna(newest):raise RuntimeError("Depth chart contains no valid timestamps")
    d=d[d["dt_parsed"].eq(newest)].copy();d["name_key"]=d["player_name"].map(norm_name);d["team_key_2026"]=d["team"].map(norm_team)
    d["pos_rank"]=pd.to_numeric(d["pos_rank"],errors="coerce")
    return d,newest

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--roles",type=Path,default=Path("data/projections/player_role_context_2026.csv"));ap.add_argument("--source",default=DEPTH_URL);ap.add_argument("--out",type=Path,default=Path("data/projections/player_role_context_2026.csv"));a=ap.parse_args()
    roles=pd.read_csv(a.roles); raw,newest=latest_depth(a.source)
    if "team_key_2026" not in roles:roles["team_key_2026"]=roles["team_2026"].map(norm_team)
    if "name_key" not in roles:roles["name_key"]=roles["name"].map(norm_name)

    # TEAM-INTEGRITY PASS: resolve a unique current team by normalized identity + offensive position.
    # We deliberately require a unique team so common-name collisions cannot silently move players.
    roles["team_2026_source"]=roles["team_2026"]
    roles["team_assignment_corrected"]=False
    roles["team_assignment_depth_team"]=pd.Series([None]*len(roles),index=roles.index,dtype="object")
    corrections=[]
    for i,r in roles.iterrows():
        g=raw[raw["name_key"].eq(r["name_key"])]
        if len(g)==0: continue
        off=g[g["pos_abb"].map(lambda x:offensive_match(r["position"],x))]
        if len(off)==0: continue
        teams=sorted(set(x for x in off["team_key_2026"].dropna().astype(str) if x))
        if len(teams)!=1: continue
        dt_team=teams[0]; roles.at[i,"team_assignment_depth_team"]=dt_team
        if norm_team(r["team_2026"])!=dt_team:
            old=r["team_2026"]; roles.at[i,"team_2026"]=dt_team; roles.at[i,"team_key_2026"]=dt_team
            roles.at[i,"team_assignment_corrected"]=True; corrections.append((r["name"],old,dt_team))

    rows=[]
    for _,r in roles.iterrows():
        g=raw[(raw["name_key"].eq(r["name_key"]))&(raw["team_key_2026"].eq(r["team_key_2026"]))]
        if len(g)==0:
            rows.append({"name_key":r["name_key"],"team_key_2026":r["team_key_2026"]});continue
        off=g[g["pos_abb"].map(lambda x:offensive_match(r["position"],x))]
        chosen=off if len(off) else g
        all_pos="/".join(sorted(set(str(x) for x in g["pos_abb"].dropna())))
        off_pos="/".join(sorted(set(str(x) for x in off["pos_abb"].dropna()))) if len(off) else ""
        has_def=g["pos_abb"].astype(str).str.upper().str.contains(DEF_RE,regex=True).any(); has_off=len(off)>0
        rows.append({"name_key":r["name_key"],"team_key_2026":r["team_key_2026"],"depth_snapshot":g["dt"].iloc[0],
            "depth_player_name":g["player_name"].iloc[0],"depth_gsis_id":g["gsis_id"].iloc[0],
            "depth_pos_group":chosen["pos_grp"].iloc[0] if "pos_grp" in chosen else None,"depth_pos":all_pos,"offensive_depth_pos":off_pos,
            "depth_rank":pd.to_numeric(chosen["pos_rank"],errors="coerce").min(),"offensive_depth_rank":pd.to_numeric(off["pos_rank"],errors="coerce").min() if len(off) else np.nan,
            "two_way_player":bool(has_off and has_def)})
    depth=pd.DataFrame(rows); merged=roles.merge(depth,on=["name_key","team_key_2026"],how="left")
    merged["depth_matched"]=merged["depth_rank"].notna();merged["depth_starter"]=merged["depth_rank"].eq(1);merged["depth_backup"]=merged["depth_rank"].gt(1)
    confidence=pd.to_numeric(merged["role_confidence"],errors="coerce").fillna(0)
    confidence=np.where(merged["depth_starter"],np.maximum(confidence,.85),confidence);confidence=np.where(merged["depth_backup"],np.minimum(confidence,.55),confidence)
    confidence=np.where(merged["two_way_player"].fillna(False),np.minimum(confidence,.50),confidence); merged["role_confidence"]=np.clip(confidence,0,1)
    qb=merged["position"].eq("QB");merged["qb_depth_starter_confirmed"]=qb&merged["depth_starter"];merged["qb_depth_backup_flag"]=qb&merged["depth_backup"]
    merged.loc[merged["qb_depth_backup_flag"],"needs_rookie_or_manual_role"]=True;merged.loc[merged["qb_depth_backup_flag"],"role_confidence"]=0.0
    a.out.parent.mkdir(parents=True,exist_ok=True);merged.to_csv(a.out,index=False)
    print(f"Depth snapshot: {newest}"); print(f"Fantasy players matched: {int(merged.depth_matched.sum())}/{len(merged)}")
    print(f"Team assignments auto-corrected: {len(corrections)}")
    for name,old,new in corrections: print(f"TEAM FIX: {name}: {old} -> {new}")
    rb_unmatched=merged[(merged.position.eq('RB')) & (~merged.depth_matched)]
    print(f"RBs unmatched to current depth snapshot: {len(rb_unmatched)}")
    if len(rb_unmatched): print("RB TEAM AUDIT UNMATCHED:",rb_unmatched[['name','team_2026']].to_dict('records'))
    print(f"Depth starters: {int(merged.depth_starter.sum())}");print(f"Two-way players: {int(merged.two_way_player.fillna(False).sum())}");print(f"QB starters confirmed: {int(merged.qb_depth_starter_confirmed.sum())}");print(f"QB backups gated: {int(merged.qb_depth_backup_flag.sum())}")
    print(f"Wrote {a.out}")
if __name__=="__main__":main()
