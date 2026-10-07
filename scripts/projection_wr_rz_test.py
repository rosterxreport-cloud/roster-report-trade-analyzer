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
  if c not in w.columns:
   w[c]=0.0
  w[c]=pd.to_numeric(w[c],errors="coerce").fillna(0)
  w["pre_"+c]=w.groupby("player_id")[c].transform(lambda s:s.shift().ewm(alpha=.45,adjust=False).mean())
 # Team totals and prior-only team environment.
 team=w.groupby(["recent_team","week"],as_index=False).agg(
   team_pass=("attempts","sum"),team_carries=("carries","sum"))
 for c in ["team_pass","team_carries"]:
  team["pre_"+c]=team.groupby("recent_team")[c].transform(lambda s:s.shift().ewm(alpha=.45,adjust=False).mean())
 w=w.merge(team,on=["recent_team","week"],how="left")
 # Prior-only WR red-zone target share from FantasyPros custom week ranges.
 rz_parts=[]
 for pred_week,end_week in [(2,1),(3,2),(4,3)]:
  url=f"https://www.fantasypros.com/nfl/red-zone-stats/wr.php?end_week={end_week}&range=custom&start_week=1&yardline=20"
  tabs=pd.read_html(url)
  tab=max(tabs,key=lambda x: len(x))
  tab.columns=["_".join([str(y) for y in x if str(y)!="nan"]).strip("_") if isinstance(x,tuple) else str(x) for x in tab.columns]
  pc=[x for x in tab.columns if "PLAYER" in x.upper()][0]
  sc=[x for x in tab.columns if "TGT PCT" in x.upper()][0]
  q=tab[[pc,sc]].copy();q.columns=["player_name_rz","pre_rz_share"]
  q["pre_rz_share"]=pd.to_numeric(q.pre_rz_share.astype(str).str.replace("%","",regex=False),errors="coerce")/100
  q["week"]=pred_week;q["join_name"]=q.player_name_rz.map(norm);rz_parts.append(q[["week","join_name","pre_rz_share"]])
 rz=pd.concat(rz_parts,ignore_index=True)
 w["join_name"]=w.player_display_name.map(norm) if "player_display_name" in w.columns else w.player_name.map(norm)
 w=w.merge(rz,on=["week","join_name"],how="left")
 return w

RZ_WEIGHT=0.0
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
  # Minimal model: retain only opportunity signals that survived ablation.
  if pos=="RB":
   catch=.68
   ypt=6.2
   rtd=(r.pre_receiving_tds/max(r.pre_targets,1)) if pd.notna(r.pre_targets) else .045
   ypc=(r.pre_rushing_yards/max(r.pre_carries,1)) if pd.notna(r.pre_carries) and r.pre_carries>0 else 4.2
   rutd=.035
  elif pos=="WR":
   catch=.68
   ypt=8.0
   # Baseline TD rate plus prior-only red-zone target-share signal.
   # Center around a 20% WR red-zone share; cap adjustment to avoid small-sample explosions.
   rz=float(r.get("pre_rz_share",.20)) if pd.notna(r.get("pre_rz_share",np.nan)) else .20
   rtd=clip(.045 + RZ_WEIGHT*(rz-.20), .015, .10)
   ypc=4.2
   rutd=.035
  else:
   catch=(r.pre_receptions/max(r.pre_targets,1)) if pd.notna(r.pre_targets) else .68
   ypt=(r.pre_receiving_yards/max(r.pre_targets,1)) if pd.notna(r.pre_targets) else 7.2
   rtd=(r.pre_receiving_tds/max(r.pre_targets,1)) if pd.notna(r.pre_targets) else .045
   ypc=(r.pre_rushing_yards/max(r.pre_carries,1)) if pd.notna(r.pre_carries) and r.pre_carries>0 else 4.2
   rutd=(r.pre_rushing_tds/max(r.pre_carries,1)) if pd.notna(r.pre_carries) and r.pre_carries>0 else .035
  vals=(0,0,0,0,0,car,car*clip(ypc,2.5,7),car*clip(rutd,.005,.16),
        tar,tar*clip(catch,.4,.9),tar*clip(ypt,3,14),tar*clip(rtd,.005,.15))
 keys=["pred_att","pred_comp","pred_pass_yds","pred_pass_td","pred_int","pred_carries",
       "pred_rush_yds","pred_rush_td","pred_targets","pred_rec","pred_rec_yds","pred_rec_td"]
 return pd.Series(dict(zip(keys,vals)))

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--out",default="data/backtests/wr_rz_test");ap.add_argument("--alpha",type=float,default=.10);ap.add_argument("--rz-weight",type=float,default=0.0)
 a=ap.parse_args();global RZ_WEIGHT;RZ_WEIGHT=a.rz_weight;out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 w=pd.read_parquet(URL)
 w=w[(w.season_type=="REG") & w.position.isin(["QB","RB","WR","TE"])].copy()
 if "recent_team" not in w.columns and "team" in w.columns:
  w["recent_team"]=w["team"]
 if "recent_team" not in w.columns:
  raise KeyError(f"Team column missing; available={list(w.columns)}")
 # WR smoothing sweep below the previous 0.35 winner.
 w=w.sort_values(["player_id","week"]).copy()
 cols=["attempts","completions","passing_yards","passing_tds","interceptions","carries","rushing_yards","rushing_tds","targets","receptions","receiving_yards","receiving_tds"]
 for col in cols:
  if col not in w.columns: w[col]=0.0
  w[col]=pd.to_numeric(w[col],errors="coerce").fillna(0)
  w["pre_"+col]=w.groupby("player_id")[col].transform(lambda s:s.shift().ewm(alpha=a.alpha,adjust=False).mean())
 team=w.groupby(["recent_team","week"],as_index=False).agg(team_pass=("attempts","sum"),team_carries=("carries","sum"))
 for col in ["team_pass","team_carries"]:
  team["pre_"+col]=team.groupby("recent_team")[col].transform(lambda s:s.shift().ewm(alpha=a.alpha,adjust=False).mean())
 w=w.merge(team,on=["recent_team","week"],how="left")
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

# trigger minimal audit

# trigger lower alpha sweep

# trigger baseline save

# trigger isolated RZ test
