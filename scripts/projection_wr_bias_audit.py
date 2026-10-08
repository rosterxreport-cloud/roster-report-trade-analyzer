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
 # Prior-only actual YAC/game from available Fantasy Points Week 3 export for Week 4.
 # Earlier weeks remain missing rather than backfilled with future information.
 if a.stat=="yacpg":
  try:
   adv=pd.read_csv("data/backtests/inputs/receiving-statswk3.csv",header=[0,1])
   adv.columns=[b if str(b)!="nan" and not str(b).startswith("Unnamed") else aa for aa,b in adv.columns]
   nc=[x for x in adv.columns if str(x).strip()=="Name"][0]; yc=[x for x in adv.columns if str(x).strip()=="YAC"][0]
   q=adv[[nc,yc]].copy();q.columns=["adv_name","pre_yac"];q["pre_yac"]=pd.to_numeric(q.pre_yac,errors="coerce");q["join_name"]=q.adv_name.map(norm);q["week"]=4
   w["join_name"]=(w.player_display_name if "player_display_name" in w.columns else w.player_name).map(norm)
   w=w.merge(q[["week","join_name","pre_yac"]],on=["week","join_name"],how="left")
  except Exception:
   w["pre_yac"]=np.nan
 return w

DIRECT_STAT="none"
DIRECT_WEIGHT=0.0
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
   rtd=.045
   # Isolated actual-production challengers. Each run activates only one.
   if DIRECT_STAT=="ydspg" and pd.notna(r.get("pre_receiving_yards",np.nan)):
    base_yd=max(tar*ypt,.01); observed=max(float(r.pre_receiving_yards),0)
    ypt=clip(((1-DIRECT_WEIGHT)*base_yd+DIRECT_WEIGHT*observed)/max(tar,.01),3,14)
    # Optional receptions/game test layered only after receiving-yards weight is selected.
    rw=float(r.get("_rec_weight",0.0))
    if rw>0 and pd.notna(r.get("pre_receptions",np.nan)):
     base_rec=max(tar*catch,.01); obs_rec=max(float(r.pre_receptions),0)
     catch=clip(((1-rw)*base_rec+rw*obs_rec)/max(tar,.01),.4,.9)
    dw=float(r.get("_def_weight",0.0))
    if dw>0 and pd.notna(r.get("pre_opp_wr_allowed",np.nan)):
     # Normalize opponent prior WR PPR allowed to prior league average.
     factor=clip(float(r.pre_opp_wr_allowed)/max(float(r.pre_league_wr_allowed),1),0.65,1.35)
     tar=clip(tar*((1-dw)+dw*factor),0,18)
    sw=float(r.get("_snap_weight",0.0))
    if sw>0 and pd.notna(r.get("pre_snap_share",np.nan)):
     tar=clip(tar*((1-sw)+sw*clip(float(r.pre_snap_share)/0.75,0.25,1.4)),0,18)
    vw=float(r.get("_volume_weight",0.0))
    if vw>0 and pd.notna(r.get("pre_team_pass",np.nan)):
     baseline_pass=34.0
     tar=clip(tar*((1-vw)+vw*float(r.pre_team_pass)/baseline_pass),0,18)
    tw=float(r.get("_target_weight",0.0))
    if tw>0 and pd.notna(r.get("pre_targets",np.nan)):
     tar=clip((1-tw)*tar+tw*max(float(r.pre_targets),0),0,18)
    ew=float(r.get("_exp_weight",0.0))
    if ew>0 and pd.notna(r.get("pre_explosive",np.nan)):
     ypt=clip(ypt + ew*float(r.pre_explosive)/max(tar,1),3,14)
   elif DIRECT_STAT=="yacpg" and pd.notna(r.get("pre_yac",np.nan)):
    # YAC/game adjusts receiving yards around a conservative 35-yard WR baseline.
    ypt=clip(ypt + DIRECT_WEIGHT*(float(r.pre_yac)-35.0)/max(tar,1),3,14)
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
 ap=argparse.ArgumentParser();ap.add_argument("--out",default="data/backtests/wr_yds_rec_sweep");ap.add_argument("--alpha",type=float,default=.10);ap.add_argument("--stat",default="ydspg");ap.add_argument("--weight",type=float,default=.30);ap.add_argument("--rec-weight",type=float,default=0.0);ap.add_argument("--exp-weight",type=float,default=0.0);ap.add_argument("--target-weight",type=float,default=0.0);ap.add_argument("--volume-weight",type=float,default=0.0);ap.add_argument("--snap-weight",type=float,default=0.0);ap.add_argument("--def-weight",type=float,default=0.0)
 a=ap.parse_args();global DIRECT_STAT,DIRECT_WEIGHT;DIRECT_STAT=a.stat;DIRECT_WEIGHT=a.weight;out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
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
 w["_rec_weight"]=a.rec_weight
 w["_exp_weight"]=a.exp_weight
 w["_target_weight"]=a.target_weight
 w["_volume_weight"]=a.volume_weight
 w["_snap_weight"]=a.snap_weight
 w["_def_weight"]=a.def_weight
 snap=pd.read_parquet("https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_2026.parquet")
 print("SNAP SCHEMA",list(snap.columns),flush=True)
 print("SNAP SAMPLE",snap.head(2).to_string(index=False),flush=True)
 snap=snap[(snap.game_type=="REG") & (snap.position=="WR")].copy()
 snap["join_name"]=snap.player.map(norm)
 snap["join_team"]=snap.team.astype(str)
 snap["offense_pct"]=pd.to_numeric(snap.offense_pct,errors="coerce")
 if snap.offense_pct.max()>1.5: snap["offense_pct"]=snap.offense_pct/100.0
 snap=snap.groupby(["join_name","join_team","week"],as_index=False)["offense_pct"].mean()
 snap=snap.sort_values(["join_name","join_team","week"])
 snap["pre_snap_share"]=snap.groupby(["join_name","join_team"])["offense_pct"].transform(lambda s:s.shift().ewm(alpha=a.alpha,adjust=False).mean())
 w["join_name"]=(w.player_display_name if "player_display_name" in w.columns else w.player_name).map(norm)
 w["join_team"]=w.recent_team.astype(str)
 w=w.merge(snap[["join_name","join_team","week","pre_snap_share"]],on=["join_name","join_team","week"],how="left")
 print("SNAP MATCHES",w[(w.position=="WR")&w.week.isin([2,3,4])].pre_snap_share.notna().sum(),flush=True)
 # Schedule maps offensive teams to their actual defensive opponents.
 games=pd.read_parquet("https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet")
 games=games[(games.season==2026)&(games.game_type=="REG")].copy()
 sides=pd.concat([games[["week","home_team","away_team"]].rename(columns={"home_team":"recent_team","away_team":"opponent"}),games[["week","home_team","away_team"]].rename(columns={"away_team":"recent_team","home_team":"opponent"})],ignore_index=True)
 sides=sides.drop_duplicates(["week","recent_team"])
 # WR PPR scored against each defense, by week; no current-week results in predictors.
 wr=w[w.position=="WR"].groupby(["week","recent_team"],as_index=False)["fantasy_points_ppr"].sum().rename(columns={"fantasy_points_ppr":"wr_ppr_scored"})
 allowed=sides.merge(wr,on=["week","recent_team"],how="left").dropna(subset=["wr_ppr_scored"])
 allowed=allowed.rename(columns={"recent_team":"offense","opponent":"defense"})
 allowed=allowed.groupby(["week","defense"],as_index=False)["wr_ppr_scored"].sum()
 allowed=allowed.sort_values(["defense","week"])
 allowed["pre_opp_wr_allowed"]=allowed.groupby("defense")["wr_ppr_scored"].transform(lambda s:s.shift().ewm(alpha=a.alpha,adjust=False).mean())
 lg=allowed.groupby("week",as_index=False)["wr_ppr_scored"].mean().sort_values("week")
 lg["pre_league_wr_allowed"]=lg.wr_ppr_scored.shift().expanding().mean()
 sides=sides.rename(columns={"opponent":"defense"})
 w=w.merge(sides[["week","recent_team","defense"]],on=["week","recent_team"],how="left")
 w=w.merge(allowed[["week","defense","pre_opp_wr_allowed"]],on=["week","defense"],how="left")
 w=w.merge(lg[["week","pre_league_wr_allowed"]],on="week",how="left")
 print("DEF COVERAGE",w[(w.position=="WR")&w.week.isin([2,3,4])].pre_opp_wr_allowed.notna().sum(),flush=True)
 # Derive actual 20+ yard receptions from 2026 nflverse play-by-play, prior weeks only.
 try:
  pbp=pd.read_parquet("https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet",columns=["week","complete_pass","receiving_yards","receiver_player_id"])
  ep=pbp[(pbp.complete_pass==1)&(pd.to_numeric(pbp.receiving_yards,errors="coerce")>=20)&pbp.receiver_player_id.notna()].groupby(["receiver_player_id","week"]).size().rename("explosive_receptions").reset_index()
  ep=ep.rename(columns={"receiver_player_id":"player_id"})
  ep["pre_explosive"]=ep.groupby("player_id")["explosive_receptions"].transform(lambda s:s.shift().ewm(alpha=a.alpha,adjust=False).mean())
  w=w.merge(ep[["player_id","week","pre_explosive"]],on=["player_id","week"],how="left")
 except Exception:
  w["pre_explosive"]=np.nan
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
 wrbt=bt[bt.position=="WR"].copy()
 wrbt["signed_error"]=wrbt.v4_ppr-wrbt.actual_ppr
 over=wrbt[wrbt.signed_error>0]
 under=wrbt[wrbt.signed_error<0]
 print(f"WR OVER: {len(over)} AVG_MISS {over.signed_error.mean():.4f}",flush=True)
 print(f"WR UNDER: {len(under)} AVG_MISS {-under.signed_error.mean():.4f}",flush=True)
 print(f"WR BIAS: {wrbt.signed_error.mean():.4f}",flush=True)
 for threshold in [1,3,5,10]:
  print(f"WR MISS OVER {threshold}: {(over.signed_error>threshold).sum()} UNDER {threshold}: {(under.signed_error < -threshold).sum()}",flush=True)
 wrbt=bt[bt.position=="WR"]
 for threshold in [1,3,5]:
  n=int((wrbt.abs_error<=threshold).sum())
  print(f"WR WITHIN {threshold}: {n}/{len(wrbt)} ({100*n/len(wrbt):.2f}%)",flush=True)
 s=bt.groupby(["week","position"]).agg(N=("player_id","size"),v4_mae=("abs_error","mean")).reset_index()
 overall=bt.groupby("position").agg(N=("player_id","size"),v4_mae=("abs_error","mean")).reset_index()
 s.to_csv(out/"weekly_summary.csv",index=False);overall.to_csv(out/"overall_summary.csv",index=False)
 print("\nWEEKLY\n",s.to_string(index=False));print("\nOVERALL\n",overall.to_string(index=False))
if __name__=="__main__": main()

# workflow trigger

# trigger minimal audit

# trigger lower alpha sweep

# trigger baseline save

# trigger direct-stat tests

# trigger yards/receptions sweep

# trigger receptions on 30pct yards winner

# trigger actual PBP explosive sweep

# trigger extended explosive sweep

# trigger isolated targets sweep

# trigger team-volume sweep

# trigger snap schema probe

# run snap-share sweep

# trigger opponent allowed sweep

# trigger final thresholds

# trigger bias audit
