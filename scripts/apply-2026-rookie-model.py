#!/usr/bin/env python3
"""Fill true rookie/no-NFL-history 2026 projections using recent rookie outcomes.

Calibration:
- nflverse draft picks identify 2024-2025 drafted rookies.
- Their same-season NFL player_features calibrate position efficiency priors.
- 2026 opportunity is driven by current depth rank, adjusted by draft capital and
  a small capped Roster Report value percentile modifier.

Players with prior NFL history stay in the veteran/fallback paths. Backup QBs are
never promoted merely because they were drafted highly.
"""
from __future__ import annotations
import argparse,re,unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

DRAFT_URL="https://github.com/nflverse/nflverse-data/releases/download/draft_picks/draft_picks.csv"
TEAM_ALIASES={"LAR":"LA","STL":"LA","JAC":"JAX","WSH":"WAS","OAK":"LV","SD":"LAC"}
GAMES=17.0


def norm_name(v):
    t=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
    t=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",t)
    return re.sub(r"[^a-z0-9]","",t)

def norm_team(v):
    if pd.isna(v): return None
    t=str(v).strip().upper(); return TEAM_ALIASES.get(t,t)

def finite(v):
    try:return np.isfinite(float(v))
    except (TypeError,ValueError):return False

def pts(r,rec):
    x=lambda k: float(r.get(k)) if finite(r.get(k)) else 0.0
    return .04*x("projected_passing_yards")+4*x("projected_passing_tds")-2*x("projected_interceptions")+.1*x("projected_rushing_yards")+6*x("projected_rushing_tds")+rec*x("projected_receptions")+.1*x("projected_receiving_yards")+6*x("projected_receiving_tds")

def draft_schema(df):
    year="season" if "season" in df else "year"
    name="full_name" if "full_name" in df else ("player_name" if "player_name" in df else "name")
    pos="position" if "position" in df else "category"
    return year,name,pos

def capital_modifier(pick):
    if not finite(pick): return -0.04
    p=float(pick)
    if p<=32:return .10
    if p<=64:return .07
    if p<=100:return .04
    if p<=150:return .015
    if p<=220:return 0.0
    return -.02

def role_prior(pos,depth_rank):
    d=int(depth_rank) if finite(depth_rank) else 4
    if pos=="QB": return {"qb":.96 if d==1 else 0.0,"carry_pg":3.2 if d==1 else 0.0}
    if pos=="RB":
        carries={1:.50,2:.30,3:.17,4:.09}.get(min(d,4),.09); targets={1:.105,2:.065,3:.038,4:.020}.get(min(d,4),.020)
        return {"carry":carries,"target":targets}
    if pos=="WR": return {"target":{1:.225,2:.175,3:.125,4:.070}.get(min(d,4),.070)}
    if pos=="TE": return {"target":{1:.145,2:.085,3:.050,4:.030}.get(min(d,4),.030)}
    return {}

def median_or(s,default):
    v=pd.to_numeric(s,errors="coerce").dropna(); return float(v.median()) if len(v) else default

def calibrate_rookies(features,draft):
    year,name,pos=draft_schema(draft)
    picks=draft[pd.to_numeric(draft[year],errors="coerce").isin([2024,2025])].copy()
    picks["season"]=pd.to_numeric(picks[year],errors="coerce").astype("Int64")
    picks["name_key"]=picks[name].map(norm_name); picks["draft_pos"]=picks[pos].astype(str).str.upper()
    f=features.copy(); f["name_key"]=f["player_display_name"].fillna(f.get("player_name","")).map(norm_name)
    rook=f.merge(picks[["season","name_key","draft_pos"]],on=["season","name_key"],how="inner")
    out={}
    defaults={
      "QB":{"pass_yards_per_attempt":6.8,"pass_td_rate":.038,"interception_rate":.025,"yards_per_carry":4.5,"rush_td_per_attempt":.03,"carries_per_game":3.2},
      "RB":{"yards_per_carry":4.2,"catch_rate":.73,"yards_per_target":5.8,"rec_td_per_target":.022,"rush_td_per_attempt":.025},
      "WR":{"catch_rate":.61,"yards_per_target":7.5,"rec_td_per_target":.045},
      "TE":{"catch_rate":.65,"yards_per_target":6.8,"rec_td_per_target":.040}}
    for p in ["QB","RB","WR","TE"]:
        g=rook[(rook["position"].astype(str).str.upper()==p)|(rook["draft_pos"]==p)]
        out[p]={k:median_or(g[k],v) if k in g else v for k,v in defaults[p].items()}
        out[p]["calibration_n"]=int(g["name_key"].nunique())
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stats",type=Path,default=Path("data/projections/stat_projections_2026.csv"))
    ap.add_argument("--roles",type=Path,default=Path("data/projections/player_role_context_2026.csv"))
    ap.add_argument("--features",type=Path,default=Path("data/projections/player_features_2023_2025.csv"))
    ap.add_argument("--teams",type=Path,default=Path("data/projections/team_context_2026.csv"))
    ap.add_argument("--draft-source",default=DRAFT_URL)
    ap.add_argument("--out",type=Path,default=Path("data/projections/stat_projections_2026.csv"))
    ap.add_argument("--diagnostics",type=Path,default=Path("data/projections/rookie_model_2026.csv"))
    a=ap.parse_args()
    stats=pd.read_csv(a.stats); roles=pd.read_csv(a.roles); features=pd.read_csv(a.features); teams=pd.read_csv(a.teams); draft=pd.read_csv(a.draft_source,low_memory=False)
    dy,dn,dp=draft_schema(draft); draft["draft_year"]=pd.to_numeric(draft[dy],errors="coerce"); draft["name_key"]=draft[dn].map(norm_name); draft["draft_position"]=draft[dp].astype(str).str.upper()
    pick_col="pick" if "pick" in draft else ("overall" if "overall" in draft else None)
    round_col="round" if "round" in draft else None
    current_draft=draft[draft["draft_year"].isin([2025,2026])].copy()
    keep=["name_key","draft_year","draft_position"]+([pick_col] if pick_col else [])+([round_col] if round_col else [])
    current_draft=current_draft[keep].drop_duplicates("name_key",keep="last")
    priors=calibrate_rookies(features,draft)
    roles=roles.copy(); roles["name_key"]=roles["name"].map(norm_name)
    team_lookup=teams.set_index("team_key" if "team_key" in teams else "team")
    role_lookup=roles.set_index(["name_key","position"])
    out=stats.copy(); out["name_key"]=out["name"].map(norm_name); out=out.merge(current_draft,on="name_key",how="left")
    # Roster Report value percentile by position, capped to ±5% role adjustment.
    rv=roles[["name_key","position","trade_value"]].copy(); rv["rr_percentile"]=rv.groupby("position")["trade_value"].rank(pct=True)
    out=out.merge(rv[["name_key","position","rr_percentile"]],on=["name_key","position"],how="left")
    diagnostics=[]; filled=0
    statcols=["projected_pass_attempts","projected_passing_yards","projected_passing_tds","projected_interceptions","projected_rush_attempts","projected_rushing_yards","projected_rushing_tds","projected_targets","projected_receptions","projected_receiving_yards","projected_receiving_tds"]
    for i,r in out[out["projection_status"].eq("manual_role_required")].iterrows():
        key=(r["name_key"],r["position"]); pos=r["position"]
        if key not in role_lookup.index: continue
        role=role_lookup.loc[key]; depth=role.get("depth_rank")
        # Eligible if drafted in 2025/26 or explicitly flagged rookie. This catches
        # second-year players with no NFL production without misclassifying veterans.
        eligible=finite(r.get("draft_year")) or bool(role.get("rookie",False))
        if not eligible: continue
        if pos=="QB" and (not finite(depth) or float(depth)>1): continue
        team_key=role.get("team_key_2026") or norm_team(role.get("team_2026"))
        if team_key not in team_lookup.index: continue
        team=team_lookup.loc[team_key]; tp=float(team.get("projected_pass_attempts",0)); tr=float(team.get("projected_rush_attempts",0))
        prior=priors.get(pos,{}); rp=role_prior(pos,depth)
        cap=capital_modifier(r.get(pick_col)) if pick_col else 0.0
        market=(float(r.get("rr_percentile"))-.5)*.10 if finite(r.get("rr_percentile")) else 0.0
        adj=np.clip(1+cap+market,.80,1.18)
        vals={c:0.0 for c in statcols}
        if pos=="QB":
            att=tp*rp["qb"]; cpg=rp["carry_pg"]*adj; rc=cpg*GAMES
            vals.update(projected_pass_attempts=att,projected_passing_yards=att*prior["pass_yards_per_attempt"],projected_passing_tds=att*prior["pass_td_rate"],projected_interceptions=att*prior["interception_rate"],projected_rush_attempts=rc,projected_rushing_yards=rc*prior["yards_per_carry"],projected_rushing_tds=rc*prior["rush_td_per_attempt"])
        elif pos=="RB":
            carries=tr*np.clip(rp["carry"]*adj,.02,.72); targets=tp*np.clip(rp["target"]*adj,.01,.20)
            vals.update(projected_rush_attempts=carries,projected_rushing_yards=carries*prior["yards_per_carry"],projected_rushing_tds=carries*prior["rush_td_per_attempt"],projected_targets=targets,projected_receptions=targets*prior["catch_rate"],projected_receiving_yards=targets*prior["yards_per_target"],projected_receiving_tds=targets*prior["rec_td_per_target"])
        elif pos in {"WR","TE"}:
            targets=tp*np.clip(rp["target"]*adj,.01,.32)
            vals.update(projected_targets=targets,projected_receptions=targets*prior["catch_rate"],projected_receiving_yards=targets*prior["yards_per_target"],projected_receiving_tds=targets*prior["rec_td_per_target"])
        else: continue
        for c,v in vals.items(): out.at[i,c]=v
        temp=vals.copy(); ppr=pts(temp,1); half=pts(temp,.5); std=pts(temp,0)
        out.at[i,"ppr_points"]=ppr; out.at[i,"half_ppr_points"]=half; out.at[i,"standard_points"]=std
        out.at[i,"ppr_per_game"]=ppr/GAMES; out.at[i,"half_ppr_per_game"]=half/GAMES; out.at[i,"standard_per_game"]=std/GAMES
        out.at[i,"projection_status"]="rookie_model"
        out.at[i,"role_confidence"]=min(.85,max(.35,.45+.12*(1 if finite(depth) and float(depth)==1 else 0)+.10*max(cap,0)))
        diagnostics.append({"name":r["name"],"team":r["team"],"position":pos,"draft_year":r.get("draft_year"),"pick":r.get(pick_col) if pick_col else np.nan,"depth_rank":depth,"role_adjustment":adj,"calibration_n":prior.get("calibration_n",0),"half_ppr_points":half})
        filled+=1
    # Re-rank after rookie insertion.
    for f in ["ppr_points","half_ppr_points","standard_points"]:
        out[f.replace("_points","_overall_rank")]=pd.to_numeric(out[f],errors="coerce").rank(method="min",ascending=False)
        for p in ["QB","RB","WR","TE"]:
            mask=out.position.eq(p)&pd.to_numeric(out[f],errors="coerce").notna(); out.loc[mask,f.replace("_points","_pos_rank")]=pd.to_numeric(out.loc[mask,f],errors="coerce").rank(method="min",ascending=False)
    out=out.drop(columns=[c for c in ["name_key","draft_year","draft_position",pick_col,round_col,"rr_percentile"] if c and c in out],errors="ignore")
    nums=out.select_dtypes(include=[np.number]).columns; out[nums]=out[nums].round(2); out.to_csv(a.out,index=False)
    diag=pd.DataFrame(diagnostics); diag.to_csv(a.diagnostics,index=False)
    print("Rookie calibration priors:",priors)
    print(f"Rookie/no-history projections filled: {filled}")
    print(f"Still manual: {int(out['projection_status'].eq('manual_role_required').sum())}")
    if len(diag): print(diag.sort_values("half_ppr_points",ascending=False).to_dict("records"))
    print(f"Wrote {a.out} and {a.diagnostics}")

if __name__=="__main__": main()
