#!/usr/bin/env python3
"""Blind comparison of EWMA recency weights using prior games only."""
import pandas as pd
from pathlib import Path
from projection_v4_backtest import URL, build_features, project, score

def evaluate(alpha):
    w=pd.read_parquet(URL)
    w=w[(w.season_type=="REG") & w.position.isin(["QB","RB","WR","TE"])].copy()
    if "recent_team" not in w and "team" in w: w["recent_team"]=w["team"]
    w=w.sort_values(["player_id","week"]).copy()
    w=build_features(w)
    if alpha!=.45:
        for c in ["attempts","completions","passing_yards","passing_tds","interceptions","carries","rushing_yards","rushing_tds","targets","receptions","receiving_yards","receiving_tds"]:
            w["pre_"+c]=w.groupby("player_id")[c].transform(lambda s:s.shift().ewm(alpha=alpha,adjust=False).mean())
        for c in ["team_pass","team_carries"]:
            team=w.groupby(["recent_team","week"],as_index=False).agg(team_pass=("attempts","sum"),team_carries=("carries","sum"))
            team["pre_"+c]=team.groupby("recent_team")[c].transform(lambda s:s.shift().ewm(alpha=alpha,adjust=False).mean())
            w=w.drop(columns=["pre_"+c]).merge(team[["recent_team","week","pre_"+c]],on=["recent_team","week"],how="left")
    p=w.apply(project,axis=1)
    w=pd.concat([w,p],axis=1)
    w["pred_ppr"]=w.apply(score,axis=1)
    w["err"]=(w.pred_ppr-w.fantasy_points_ppr).abs()
    bt=w[w.week.isin([2,3,4])].copy()
    bt["prior_opp"]=bt.pre_attempts.fillna(0)+bt.pre_carries.fillna(0)+1.5*bt.pre_targets.fillna(0)
    keep=[]
    for (_,pos),g in bt.groupby(["week","position"]):
        keep.append(g.nlargest({"QB":32,"RB":50,"WR":50,"TE":35}[pos],"prior_opp"))
    bt=pd.concat(keep)
    bt["alpha"]=alpha
    return bt
if __name__=="__main__":
    out=Path("data/backtests/recency_comparison")
    out.mkdir(parents=True,exist_ok=True)
    d=pd.concat([evaluate(a) for a in [.45,.55,.60]],ignore_index=True)
    summary=d.groupby(["alpha","position"]).agg(N=("err","size"),MAE=("err","mean")).reset_index()
    summary.to_csv(out/"summary.csv",index=False)
    d[["alpha","week","player_display_name","position","pred_ppr","fantasy_points_ppr","err"]].to_csv(out/"player_results.csv",index=False)
    print(summary.to_string(index=False))
