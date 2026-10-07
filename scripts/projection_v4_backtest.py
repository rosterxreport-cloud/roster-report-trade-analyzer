#!/usr/bin/env python3
"""Projection v4 challenger.

Structural model:
team plays -> pass/rush volume -> player opportunity share -> efficiency ->
expected touchdowns -> fantasy points.

Designed for blind weekly backtests.  All rolling features are shifted so the
week being predicted is never used in its own feature construction.
"""
import numpy as np, pandas as pd, re, argparse
from pathlib import Path

URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.parquet"

def clip(x,a,b): return np.clip(x,a,b)

def norm(s): return re.sub(r"[^a-z0-9]","",str(s).lower())

def score(r):
 p=r.position
 if p=="QB":
  return .04*r.pred_pass_yds+4*r.pred_pass_td-2*r.pred_int+.1*r.pred_rush_yds+6*r.pred_rush_td
 rec=r.pred_rec; y=r.pred_rec_yds; td=r.pred_rec_td
 rush=.1*r.pred_rush_yds+6*r.pred_rush_td
 return rush+rec+y*.1+td*6

def build_features(w):
 w=w.sort_values(["player_id","week"]).copy()
 # Prior-only exponentially weighted player rates.
 cols=["attempts","completions","passing_yards","passing_tds","interceptions",
       "carries","rushing_yards","rushing_tds","targets","receptions",
       "receiving_yards","receiving_tds"]
 for c in cols:
  w[c]=pd.to_numeric(w.get(c,0),errors="coerce").fillna(0)
  w["pre_"+c]=w.groupby("player_id")[c].transform(lambda s:s.shift().ewm(alpha=.45,adjust=False).mean())
 # Team totals and prior-only team environment.
 team=w.groupby(["recent_team","week"],as_index=False).agg(
   team_pass=("attempts","sum"),team_carries=("carries","sum"))
 for c in ["team_pass","team_carries"]:
  team["pre_"+c]=team.groupby("recent_team")[c].transform(lambda s:s.shift().ewm(alpha=.45,adjust=False).mean())
 w=w.merge(team,on=["recent_team","week"],how="left")
 return w

def project(r):
 pos=r.position
 pp=max(r.pre_team_pass if pd.notna(r.pre_team_pass) else 34,20)
 rc=max(r.pre_team_carries if pd.notna(r.pre_team_carries) else 26,15)
 # Dynamic shares are estimated from prior opportunity and shrunk toward
 # positional priors. This is deliberately conservative early in season.
 games=max(int(r.week)-1,1); shrink=min(.72,games/(games+3))
 if pos=="QB":
  att=clip((r.pre_attempts if pd.notna(r.pre_attempts) else pp*.90),18,45)
  cpa=(r.pre_completions/max(r.pre_attempts,1)) if pd.notna(r.pre_attempts) else .65
  ypa=(r.pre_passing_yards/max(r.pre_attempts,1)) if pd.notna(r.pre_attempts) else 7.1
  tdr=(r.pre_passing_tds/max(r.pre_attempts,1)) if pd.notna(r.pre_attempts) else .045
  ir=(r.pre_interceptions/max(r.pre_attempts,1)) if pd.notna(r.pre_attempts) else .025
  car=max(r.pre_carries if pd.notna(r.pre_carries) else 3.5,0)
  ypc=(r.pre_rushing_yards/max(r.pre_carries,1)) if pd.notna(r.pre_carries) else 4.2
  rtdr=(r.pre_rushing_tds/max(r.pre_carries,1)) if pd.notna(r.pre_carries) else .06
  vals=(att,att*cpa,att*clip(ypa,5,10),att*clip(tdr,.015,.09),att*clip(ir,.005,.06),
        car,car*clip(ypc,2,8),car*clip(rtdr,.01,.20),0,0,0,0)
 else:
  prior_t={"RB":.10,"WR":.20,"TE":.14}.get(pos,.08)
  prior_c={"RB":.48,"WR":.01,"TE":0}.get(pos,0)
  raw_t=(r.pre_targets/max(r.pre_team_pass,1)) if pd.notna(r.pre_targets) and pd.notna(r.pre_team_pass) else prior_t
  raw_c=(r.pre_carries/max(r.pre_team_carries,1)) if pd.notna(r.pre_carries) and pd.notna(r.pre_team_carries) else prior_c
  tsh=(1-shrink)*prior_t+shrink*raw_t; csh=(1-shrink)*prior_c+shrink*raw_c
  tar=pp*clip(tsh,0,.42); car=rc*clip(csh,0,.82)
  catch=(r.pre_receptions/max(r.pre_targets,1)) if pd.notna(r.pre_targets) else .68
  ypt=(r.pre_receiving_yards/max(r.pre_targets,1)) if pd.notna(r.pre_targets) else {"RB":6.2,"WR":8.0,"TE":7.2}.get(pos,7)
  rtd=(r.pre_receiving_tds/max(r.pre_targets,1)) if pd.notna(r.pre_targets) else .045
  ypc=(r.pre_rushing_yards/max(r.pre_carries,1)) if pd.notna(r.pre_carries) and r.pre_carries>0 else 4.2
  rutd=(r.pre_rushing_tds/max(r.pre_carries,1)) if pd.notna(r.pre_carries) and r.pre_carries>0 else .035
  vals=(0,0,0,0,0,car,car*clip(ypc,2.5,7),car*clip(rutd,.005,.16),
        tar,tar*clip(catch,.4,.9),tar*clip(ypt,3,14),tar*clip(rtd,.005,.15))
 keys=["pred_att","pred_comp","pred_pass_yds","pred_pass_td","pred_int","pred_carries",
       "pred_rush_yds","pred_rush_td","pred_targets","pred_rec","pred_rec_yds","pred_rec_td"]
 return pd.Series(dict(zip(keys,vals)))

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--out",default="data/backtests/v4")
 a=ap.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 w=pd.read_parquet(URL)
 w=w[(w.season_type=="REG") & w.position.isin(["QB","RB","WR","TE"])].copy()
 w=build_features(w)
 pred=w.apply(project,axis=1);w=pd.concat([w,pred],axis=1)
 w["v4_ppr"]=w.apply(score,axis=1)
 w["actual_ppr"]=w["fantasy_points_ppr"]
 w["abs_error"]=(w.v4_ppr-w.actual_ppr).abs()
 # Weeks 2-4: true blind historical evaluation using only prior weeks.
 bt=w[w.week.isin([2,3,4])].copy()
 # Use fantasy-relevant pools based on prior opportunity, not future outcome.
 bt["prior_opp"]=bt.pre_attempts.fillna(0)+bt.pre_carries.fillna(0)+bt.pre_targets.fillna(0)*1.5
 keep=[]
 limits={"QB":32,"RB":50,"WR":50,"TE":35}
 for (wk,pos),g in bt.groupby(["week","position"]):
  keep.append(g.nlargest(limits[pos],"prior_opp"))
 bt=pd.concat(keep,ignore_index=True)
 bt.to_csv(out/"player_results.csv",index=False)
 s=bt.groupby(["week","position"]).agg(N=("player_id","size"),v4_mae=("abs_error","mean")).reset_index()
 overall=bt.groupby("position").agg(N=("player_id","size"),v4_mae=("abs_error","mean")).reset_index()
 s.to_csv(out/"weekly_summary.csv",index=False);overall.to_csv(out/"overall_summary.csv",index=False)
 print("\nWEEKLY\n",s.to_string(index=False));print("\nOVERALL\n",overall.to_string(index=False))
if __name__=="__main__": main()

# workflow trigger
