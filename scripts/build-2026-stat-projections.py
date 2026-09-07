#!/usr/bin/env python3
"""Build context-aware 2026 QB/RB/WR/TE stat projections.

Normal veterans use 2025 efficiency and role context. Returning players rescued
by the prior-history fallback use explicitly prefixed 2024/2023 inputs. True
rookies/no-NFL-history players remain manual until the college model is applied.
"""
from __future__ import annotations
import argparse, re, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

GAMES=17.0
REG={"catch_rate":.30,"yards_per_target":.35,"rec_td_per_target":.55,"yards_per_carry":.35,
     "pass_yards_per_attempt":.30,"pass_td_rate":.45,"interception_rate":.40,"rush_td_per_attempt":.35}

def norm_name(v):
    t=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
    t=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",t)
    return re.sub(r"[^a-z0-9]","",t)

def finite(v):
    try:return np.isfinite(float(v))
    except (TypeError,ValueError):return False

def val(d,key,default=np.nan):
    fb=f"fallback_{key}"
    if bool(d.get("fallback_history_used",False)) and finite(d.get(fb)): return float(d[fb])
    return float(d[key]) if finite(d.get(key)) else default

def regress(v,mean,amount):
    mean=float(mean) if finite(mean) else 0.0
    return mean if not finite(v) else (1-amount)*float(v)+amount*mean

def points(r,rec):
    x=lambda k: float(r.get(k)) if finite(r.get(k)) else 0.0
    return .04*x("projected_passing_yards")+4*x("projected_passing_tds")-2*x("projected_interceptions")+.1*x("projected_rushing_yards")+6*x("projected_rushing_tds")+rec*x("projected_receptions")+.1*x("projected_receiving_yards")+6*x("projected_receiving_tds")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--roles",type=Path,default=Path("data/projections/player_role_context_2026.csv")); ap.add_argument("--features",type=Path,default=Path("data/projections/player_features_2023_2025.csv")); ap.add_argument("--history",type=Path,default=Path("data/projections/history_baseline_2026.csv")); ap.add_argument("--out",type=Path,default=Path("data/projections/stat_projections_2026.csv")); a=ap.parse_args()
    roles=pd.read_csv(a.roles); features=pd.read_csv(a.features); hist=pd.read_csv(a.history)
    latest=features[features.season.eq(2025)].copy(); latest["name_key"]=latest["player_display_name"].fillna(latest.get("player_name","")).map(norm_name)
    eff=["catch_rate","yards_per_target","rec_td_per_target","yards_per_carry","pass_yards_per_attempt","pass_td_rate","interception_rate","rush_td_per_attempt","carries_per_game","targets_per_game","attempts_per_game"]
    means={p:{c:pd.to_numeric(g[c],errors="coerce").mean() for c in eff if c in g} for p,g in latest.groupby("position")}
    base=roles.merge(latest[[c for c in ["name_key","position"]+eff if c in latest]],on=["name_key","position"],how="left",suffixes=("","_2025"))
    for c in eff:
        c25=f"{c}_2025"
        if c25 in base: base[c]=base[c25].combine_first(base[c] if c in base else pd.Series(index=base.index,dtype=float))
    if "player_display_name" in hist:
        hist=hist.copy(); hist["name_key"]=hist["player_display_name"].fillna(hist.get("player_name","")).map(norm_name); base=base.merge(hist[["name_key","position","history_baseline_ppr_per_game"]],on=["name_key","position"],how="left")
    rows=[]
    for _,s in base.iterrows():
        d=s.to_dict(); pos=d.get("position"); m=means.get(pos,{})
        manual=bool(d.get("needs_rookie_or_manual_role",False)); ctx=finite(d.get("projected_pass_attempts")) and finite(d.get("projected_rush_attempts")); status="manual_role_required" if manual else ("context_missing" if not ctx else ("returning_fallback" if bool(d.get("fallback_history_used",False)) else "modeled_veteran"))
        r={"name":d.get("name"),"player_id":d.get("player_id"),"team":d.get("team_2026"),"position":pos,"rookie":bool(d.get("rookie",False)),"changed_team":bool(d.get("changed_team",False)),"role_confidence":d.get("role_confidence"),"history_baseline_ppr_per_game":d.get("history_baseline_ppr_per_game"),"projection_status":status,"history_source_season":d.get("history_source_season")}
        stats=["projected_pass_attempts","projected_passing_yards","projected_passing_tds","projected_interceptions","projected_rush_attempts","projected_rushing_yards","projected_rushing_tds","projected_targets","projected_receptions","projected_receiving_yards","projected_receiving_tds"]
        for c in stats:r[c]=np.nan if status in {"manual_role_required","context_missing"} else 0.0
        if status in {"manual_role_required","context_missing"}: rows.append(r); continue
        tp=float(d["projected_pass_attempts"]); tr=float(d["projected_rush_attempts"]); role=lambda k,default,lo,hi: float(np.clip(val(d,k,default),lo,hi))
        if pos=="QB":
            share=role("role_qb_attempt_share_2026",.97,.20,1); att=tp*share; ypa=regress(val(d,"pass_yards_per_attempt"),m.get("pass_yards_per_attempt",7),REG["pass_yards_per_attempt"]); td=regress(val(d,"pass_td_rate"),m.get("pass_td_rate",.045),REG["pass_td_rate"]); inte=regress(val(d,"interception_rate"),m.get("interception_rate",.022),REG["interception_rate"]); cpg=max(0,val(d,"carries_per_game",3.5)); ypc=regress(val(d,"yards_per_carry"),m.get("yards_per_carry",4.7),REG["yards_per_carry"]); rtd=regress(val(d,"rush_td_per_attempt"),m.get("rush_td_per_attempt",.035),REG["rush_td_per_attempt"]); rc=cpg*GAMES
            r.update(projected_pass_attempts=att,projected_passing_yards=att*ypa,projected_passing_tds=att*td,projected_interceptions=att*inte,projected_rush_attempts=rc,projected_rushing_yards=rc*ypc,projected_rushing_tds=rc*rtd)
        elif pos=="RB":
            cs=role("role_carry_share_2026",.35,.01,.90); ts=role("role_target_share_2026",.08,.005,.35); carries=tr*cs; targets=tp*ts; ypc=regress(val(d,"yards_per_carry"),m.get("yards_per_carry",4.25),REG["yards_per_carry"]); catch=regress(val(d,"catch_rate"),m.get("catch_rate",.77),REG["catch_rate"]); ypt=regress(val(d,"yards_per_target"),m.get("yards_per_target",6.2),REG["yards_per_target"]); rectd=regress(val(d,"rec_td_per_target"),m.get("rec_td_per_target",.025),REG["rec_td_per_target"]); rushtd=regress(val(d,"rush_td_per_attempt"),m.get("rush_td_per_attempt",.03),REG["rush_td_per_attempt"])
            r.update(projected_rush_attempts=carries,projected_rushing_yards=carries*ypc,projected_rushing_tds=carries*rushtd,projected_targets=targets,projected_receptions=targets*catch,projected_receiving_yards=targets*ypt,projected_receiving_tds=targets*rectd)
        elif pos in {"WR","TE"}:
            ts=role("role_target_share_2026",.16 if pos=="WR" else .11,.005,.38); targets=tp*ts; catch=regress(val(d,"catch_rate"),m.get("catch_rate",.64 if pos=="WR" else .68),REG["catch_rate"]); ypt=regress(val(d,"yards_per_target"),m.get("yards_per_target",8 if pos=="WR" else 7.5),REG["yards_per_target"]); rectd=regress(val(d,"rec_td_per_target"),m.get("rec_td_per_target",.05),REG["rec_td_per_target"]); r.update(projected_targets=targets,projected_receptions=targets*catch,projected_receiving_yards=targets*ypt,projected_receiving_tds=targets*rectd)
        r["ppr_points"]=points(r,1); r["half_ppr_points"]=points(r,.5); r["standard_points"]=points(r,0); r["ppr_per_game"]=r["ppr_points"]/GAMES; r["half_ppr_per_game"]=r["half_ppr_points"]/GAMES; r["standard_per_game"]=r["standard_points"]/GAMES; rows.append(r)
    out=pd.DataFrame(rows)
    for f in ["ppr_points","half_ppr_points","standard_points"]:
        out[f.replace("_points","_overall_rank")]=out[f].rank(method="min",ascending=False)
        for p in ["QB","RB","WR","TE"]:
            mask=out.position.eq(p)&out[f].notna(); out.loc[mask,f.replace("_points","_pos_rank")]=out.loc[mask,f].rank(method="min",ascending=False)
    nums=out.select_dtypes(include=[np.number]).columns; out[nums]=out[nums].round(2); out=out.sort_values(["projection_status","half_ppr_points"],ascending=[True,False]); a.out.parent.mkdir(parents=True,exist_ok=True); out.to_csv(a.out,index=False)
    for st in ["modeled_veteran","returning_fallback","manual_role_required","context_missing"]: print(st,int(out.projection_status.eq(st).sum()))
    print('Projection rows with canonical player ID',int(out['player_id'].notna().sum()) if 'player_id' in out else 0)
    eligible=out[out.projection_status.isin(["modeled_veteran","returning_fallback"])]
    for p in ["QB","RB","WR","TE"]:
        top=eligible[eligible.position.eq(p)].nlargest(5,"half_ppr_points"); print(p,list(zip(top.name,top.half_ppr_points.round(1))))
    print(f"Wrote {a.out}")
if __name__=="__main__": main()
