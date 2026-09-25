#!/usr/bin/env python3
"""Historical Week 1-2 fantasy projection runner (baseline only).
Uses frozen point-in-time player priors plus only pre-week 2026 usage.
This first pass creates a reproducible no-leakage baseline for all QB/RB/WR/TE.
"""
import sys
from pathlib import Path
import pandas as pd, numpy as np
import json
PBP="https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet"
sys.path.insert(0,str(Path(__file__).parent))
from backtest_point_in_time import load,key,team
OUT=Path("data/backtests")
# Stable position-level PPR baselines used only when a player has no prior-season weekly usage.
POS_BASE={"QB":17.0,"RB":9.5,"WR":8.5,"TE":6.5}
# Current-model efficiency regression weights, pinned for historical replay.
REGRESSION_WEIGHTS={"catch_rate":0.30,"yards_per_target":0.35,"receiving_td_per_target":0.55,"yards_per_carry":0.35,"passing_ypa":0.30,"passing_td_rate":0.45,"interception_rate":0.40,"rushing_td_rate":0.35}
NEUTRAL={"catch_rate":0.645,"yards_per_target":7.5,"receiving_td_per_target":0.045,"yards_per_carry":4.3,"passing_ypa":7.15,"passing_td_rate":0.045,"interception_rate":0.022,"rushing_td_rate":0.025}
def regress(observed,metric):
 w=REGRESSION_WEIGHTS[metric]
 try:o=float(observed)
 except:o=NEUTRAL[metric]
 if not np.isfinite(o):o=NEUTRAL[metric]
 return w*o+(1-w)*NEUTRAL[metric]
def prior_strength(p):
 # Historical analyticsScore is the cleanest common numeric player-quality signal
 # present in both pinned repository snapshots.
 try:return float(p.get("analyticsScore",50) or 50)
 except:return 50.
def preweek_usage(stats):
 if stats.empty:return {}
 s=stats.copy();s["k"]=s.player_display_name.map(key)
 # Aggregate only games strictly before the projection week.
 sumcols=[z for z in ["games","attempts","passing_yards","passing_tds","passing_interceptions","carries","rushing_yards","rushing_tds","targets","receptions","receiving_yards","receiving_tds","fantasy_points_ppr"] if z in s]
 teamcol="recent_team" if "recent_team" in s.columns else ("team" if "team" in s.columns else None)
 if teamcol is None:return {}
 g=s.groupby(["k","position",teamcol],as_index=False)[sumcols].sum()
 out={}
 for _,r in g.iterrows():
  games=max(1.,float(r.get("games",0) or 0))
  out[r.k]={z:float(r.get(z,0) or 0)/games for z in sumcols if z!="games"}
 return out
def team_volume(stats):
 if stats.empty:return {}
 s=stats.copy()
 for z in ["attempts","carries"]:
  if z not in s:s[z]=0
 teamcol="recent_team" if "recent_team" in s.columns else ("team" if "team" in s.columns else None)
 if teamcol is None:return {}
 g=s.groupby(teamcol,as_index=False)[["attempts","carries"]].sum()
 games=s.groupby(teamcol)["week"].nunique().to_dict()
 return {team(r[teamcol]):{"pass_att_pg":float(r.attempts)/max(1,games.get(r[teamcol],1)),"carries_pg":float(r.carries)/max(1,games.get(r[teamcol],1))} for _,r in g.iterrows()}
def injury_factors(week):
 p=OUT/"priors"/f"week{week}_injuries.json"
 if not p.exists():return {}
 try:d=json.loads(p.read_text()).get("players",{})
 except:return {}
 out={}
 for name,x in d.items():
  status=str(x.get("status","") or "").upper()
  a=float(x.get("availability",1) or 0); w=float(x.get("workload",1) or 0)
  if any(z in status for z in ["INJURED RESERVE","IR -","PUP","NFI","OUT ","INACTIVE","UNAVAILABLE"]): factor=0.0
  elif "DOUBTFUL" in status: factor=min(.25,a*w)
  else: factor=max(0.,min(1.,a*w))
  out[key(name)]=(factor,status)
 return out
def defense_multipliers(week):
 # Only plays from weeks before the projected week are eligible. Week 1 is neutral.
 if week==1:return {}
 try:
  pbp=pd.read_parquet(PBP)
  if "week" in pbp: pbp=pbp[(pbp.season_type=="REG")&(pbp.week<week)].copy()
  vals={}
  for d,g in pbp.groupby("defteam"):
   e=pd.to_numeric(g.get("epa"),errors="coerce").mean()
   vals[team(d)]=e
  if not vals:return {}
  s=pd.Series(vals);pct=s.rank(pct=True)
  # Same intentionally modest early-season opponent envelope: +/-12%.
  return {k:.88+.24*float(pct[k]) for k in pct.index}
 except Exception as ex:
  print("Historical defense neutral fallback:",ex);return {}
def constrain_rb_team(rows):
 # V4: team-level RB opportunity budget + role-aware allocation.
 by={}
 for r in rows:
  if r["position"]=="RB":by.setdefault(r["team"],[]).append(r)
 for tm,rs in by.items():
  # Preserve V3 team pools, but allocate by role instead of proportional scaling.
  # Role score blends frozen player prior, pre-week usage and receiving involvement.
  cpool=min(24.0,sum(max(0.,r.get("carries",0)) for r in rs))
  tpool=min(7.0,sum(max(0.,r.get("targets",0)) for r in rs))
  for r in rs:
   prior=max(1.,float(r.get("_role_prior",50)))
   livec=max(0.,float(r.get("_pre_carries",0)));livet=max(0.,float(r.get("_pre_targets",0)))
   # Early season: frozen role remains important; actual usage gains influence immediately.
   r["_carry_role_score"]=(prior**1.25)*(1+.12*livec)
   r["_target_role_score"]=(prior**1.10)*(1+.22*livet)
  cs=sum(r["_carry_role_score"] for r in rs);ts=sum(r["_target_role_score"] for r in rs)
  for r in rs:
   oldc=r.get("carries",0);oldt=r.get("targets",0)
   # Do not create more opportunity than the unconstrained player projection.
   newc=min(oldc,cpool*r["_carry_role_score"]/cs) if cs else 0.
   newt=min(oldt,tpool*r["_target_role_score"]/ts) if ts else 0.
   # Redistribute unused pool once to backs with remaining modeled capacity.
   r["_newc"]=newc;r["_newt"]=newt
  for fld,pool,capfld,scorefld in [("_newc",cpool,"carries","_carry_role_score"),("_newt",tpool,"targets","_target_role_score")]:
   left=pool-sum(r[fld] for r in rs); elig=[r for r in rs if r[fld]+1e-9<r.get(capfld,0)]
   den=sum(r[scorefld] for r in elig)
   if left>0 and den>0:
    for r in elig:r[fld]+=min(r.get(capfld,0)-r[fld],left*r[scorefld]/den)
  # V5 RB2 role-certainty gate after V4 pool allocation.
  ranked=sorted(rs,key=lambda r:r.get("_newc",0)+1.5*r.get("_newt",0),reverse=True)
  if len(ranked)>1:
   r2=ranked[1];livec=float(r2.get("_pre_carries",0));livet=float(r2.get("_pre_targets",0));prior=float(r2.get("_role_prior",50))
   if livec+livet>0:certainty=max(.35,min(1.0,.35+.055*livec+.09*livet))
   else:certainty=max(.30,min(.90,.30+.006*max(0.,prior-40)))
   r2["_newc"]*=certainty;r2["_newt"]*=certainty;r2["rb2_role_certainty"]=certainty
  for r in rs:
   newc,newt=r.pop("_newc"),r.pop("_newt")
   oldc,oldt=r.get("carries",0),r.get("targets",0)
   ypc=r.get("rush_yards",0)/oldc if oldc else 0;rutdr=r.get("rush_tds",0)/oldc if oldc else 0
   cr=r.get("receptions",0)/oldt if oldt else 0;ypt=r.get("rec_yards",0)/oldt if oldt else 0;rtdr=r.get("rec_tds",0)/oldt if oldt else 0
   rec=newt*cr;std=newc*ypc*.1+newc*rutdr*6+newt*ypt*.1+newt*rtdr*6
   r.update(carries=newc,rush_yards=newc*ypc,rush_tds=newc*rutdr,targets=newt,receptions=rec,rec_yards=newt*ypt,rec_tds=newt*rtdr,standard_projection=std,half_projection=std+.5*rec,ppr_projection=std+rec)
   r["rb_role_allocation"]="V4_ROLE_AWARE"
   for z in ["_carry_role_score","_target_role_score","_role_prior","_pre_carries","_pre_targets"]:r.pop(z,None)
 return rows
def project_from_usage(pos,p,ud,td):
 # Historical replay of the current model's early-season opportunity + efficiency structure.
 score=prior_strength(p)
 if pos=="QB":
  att0=max(27.,min(40.,td.get("pass_att_pg",32.5)))
  att=.60*ud.get("attempts",att0)+.40*att0
  ypa=regress(ud.get("passing_yards",att*NEUTRAL["passing_ypa"])/max(1.,ud.get("attempts",att)), "passing_ypa")
  tdr=regress(ud.get("passing_tds",att*NEUTRAL["passing_td_rate"])/max(1.,ud.get("attempts",att)), "passing_td_rate")
  intr=regress(ud.get("passing_interceptions",att*NEUTRAL["interception_rate"])/max(1.,ud.get("attempts",att)), "interception_rate")
  car=.45*ud.get("carries",2.5)+.55*2.5; ry=car*4.5; rtd=car*NEUTRAL["rushing_td_rate"]
  std=att*ypa*.04+att*tdr*4-att*intr*2+ry*.1+rtd*6
  return std,std,std,{"pass_attempts":att,"pass_yards":att*ypa,"pass_tds":att*tdr,"interceptions":att*intr,"carries":car,"rush_yards":ry,"rush_tds":rtd}
 if pos=="RB":
  car0=max(4.,min(22.,6.+score*.14));car=.55*ud.get("carries",car0)+.45*car0
  tgt0=max(1.,min(7.,1.+score*.045));tgt=.55*ud.get("targets",tgt0)+.45*tgt0
 elif pos=="WR":
  tgt0=max(2.,min(11.,2.+score*.085));tgt=.55*ud.get("targets",tgt0)+.45*tgt0;car=0
 else:
  tgt0=max(1.5,min(8.,1.5+score*.055));tgt=.55*ud.get("targets",tgt0)+.45*tgt0;car=0
 cr=regress(ud.get("receptions",tgt*NEUTRAL["catch_rate"])/max(1.,ud.get("targets",tgt)),"catch_rate")
 ypt=regress(ud.get("receiving_yards",tgt*NEUTRAL["yards_per_target"])/max(1.,ud.get("targets",tgt)),"yards_per_target")
 rtdr=regress(ud.get("receiving_tds",tgt*NEUTRAL["receiving_td_per_target"])/max(1.,ud.get("targets",tgt)),"receiving_td_per_target")
 rec=tgt*cr;std=tgt*ypt*.1+tgt*rtdr*6
 if pos=="RB":
  ypc=regress(ud.get("rushing_yards",car*NEUTRAL["yards_per_carry"])/max(1.,ud.get("carries",car)),"yards_per_carry")
  rutdr=regress(ud.get("rushing_tds",car*NEUTRAL["rushing_td_rate"])/max(1.,ud.get("carries",car)),"rushing_td_rate")
  std+=car*ypc*.1+car*rutdr*6
 return std,std+.5*rec,std+rec,{"carries":car,"rush_yards":car*ypc if pos=="RB" else 0.,"rush_tds":car*rutdr if pos=="RB" else 0.,"targets":tgt,"receptions":rec,"rec_yards":tgt*ypt,"rec_tds":tgt*rtdr}
def apply_rb_fp_experiment(rows,week):
 if week<=1:return rows
 ps=[OUT/"priors"/"fp_rb_week1_core.csv",OUT/"priors"/"fp_rb_week1_core_part2.csv",OUT/"priors"/"fp_rb_week1_core_part3.csv"]
 q=pd.concat([pd.read_csv(p) for p in ps],ignore_index=True);q["k"]=q.Name.map(key);qm={x.k:x for _,x in q.iterrows()}
 for r in rows:
  if r["position"]!="RB":continue
  x=qm.get(key(r["player"]))
  if x is None:continue
  base=float(r["ppr_projection"]);r["rb_fp_control"]=round(base,3)
  def val(n,d=0.): return float(getattr(x,n)) if pd.notna(getattr(x,n)) else d
  # Conservative one-week signal tests. Each column changes one underlying role/TD component only.
  snap=max(.55,min(1.25,(val("SNAP",43.6)/43.6)**.35));att=max(.65,min(1.30,(val("ATT",9.8)/9.8)**.35))
  rte=max(.65,min(1.30,(val("RTE_PCT",29.)/29.)**.35));tprr=max(.70,min(1.30,(val("TPRR",.20)/.20)**.30))
  exp=max(.70,min(1.30,((val("EXP_YDS",16.6)+10)/(26.6))**.30));i5=max(.85,min(1.15,1+(val("I5",20.5)-20.5)/300.))
  rushpts=float(r.get("rush_yards",0))*.1+float(r.get("rush_tds",0))*6;recpts=float(r.get("rec_yards",0))*.1+float(r.get("receptions",0))+float(r.get("rec_tds",0))*6
  r["rb_fp_snap"]=round(base+(rushpts+recpts)*(snap-1),3);r["rb_fp_att"]=round(base+rushpts*(att-1),3);r["rb_fp_expyds"]=round(base+rushpts*(exp-1),3);r["rb_fp_i5"]=round(base+rushpts*(i5-1),3);r["rb_fp_route"]=round(base+recpts*(rte-1),3);r["rb_fp_tprr"]=round(base+recpts*(tprr-1),3)
  oldrt=float(r.get("rush_tds",0));oldct=float(r.get("rec_tds",0));rx=.55*val("RUSH_XTD",.31)+.45*.31;cx=.55*val("REC_XTD",.051)+.45*.051;comb=.55*val("COMBINED_XTD",.361)+.45*.361
  r["rb_fp_rushxtd"]=round(base+6*(rx-oldrt),3);r["rb_fp_recxtd"]=round(base+6*(cx-oldct),3);r["rb_fp_combxtd"]=round(base+6*(comb-oldrt-oldct),3)
  # Target only the overbiased high-opportunity/high-projection RB tail.
  xtdbase=r["rb_fp_recxtd"];opp=float(r.get("carries",0))+float(r.get("targets",0))
  # nflverse Week-1 15+ explosive run rate; shrink small samples toward 8% prior.
  ep=OUT/"priors"/"nflverse_rb_week1_explosive15.csv"
  if ep.exists():
   ed=pd.read_csv(ep); ed["k"]=ed.rusher_player_name.astype(str).str.split(".").str[-1].map(key)
   em={z.k:z for _,z in ed.iterrows()}; ex=em.get(key(str(r["player"]).split()[-1]))
   if ex is not None:
    er=(float(ex.explosive15)+2*.08)/(float(ex.attempts)+2)
    for wt in (.10,.125,.15,.175,.20,.225,.25):
     mult=max(.90,min(1.10,1+wt*(er/.08-1)))
     r[f"rb_fp_recxtd_hi16_expl_{int(wt*100)}"]=round((xtdbase*.84 if (xtdbase>=13 and opp>=16) else xtdbase)*mult,3)
  high=(xtdbase>=13.0 and opp>=16.0)
  for pct in (5,10,12,14,15,16,18,20):
   r[f"rb_fp_recxtd_hi_comp_{pct}"]=round(xtdbase*(1-pct/100.) if high else xtdbase,3)
  # Receiving xTD winner held fixed; add only light TPRR influence to receiving opportunity.
  xtdbase=r["rb_fp_recxtd"]
  for wt in (.05,.10,.15,.20):
   light=1+wt*(tprr-1)
   r[f"rb_fp_recxtd_tprr_{int(wt*100)}"]=round(xtdbase+recpts*(light-1),3)
 return rows

def apply_wr_route_tprr_experiment(rows,week,prestats):
 if week<=1:return rows
 ps=[OUT/"priors"/f"fp_wr_week1_part{i}.csv" for i in (1,2,3)]
 q=pd.concat([pd.read_csv(p) for p in ps],ignore_index=True);q["k"]=q["Name"].map(key);qm={x.k:x for _,x in q.iterrows()}
 for r in rows:
  if r["position"]!="WR":continue
  x=qm.get(key(r["player"]))
  if x is None:continue
  routes=float(x.RTE);tprr=float(x.TPRR);rs=max(.70,min(1.20,routes/32.));ts=max(.75,min(1.25,tprr/.20));mult=max(.80,min(1.20,.85*rs+.15*ts))
  base_td=float(r.get("rec_tds",0))*mult
  for z in ["targets","receptions","rec_yards"]:r[z]=float(r.get(z,0))*mult
  base_ppr=float(r["ppr_projection"])*mult;r["ppr_xtd_0"]=round(base_ppr,3)
  xtd=float(x.XTD) if pd.notna(x.XTD) else 0.;xtd_reg=.55*xtd+.45*.171
  for pct in (25,50,75,100):
   td_blend=(1-pct/100.)*base_td+(pct/100.)*xtd_reg;r[f"ppr_xtd_{pct}"]=round(base_ppr+6*(td_blend-base_td),3)
  # Hold the winning 75% xTD TD component fixed; test regressed Week-1 YPT only.
  p75=r["ppr_xtd_75"];week_ypt=float(x.YPT) if pd.notna(x.YPT) else 8.0
  for wt in (.10,.20,.30):
   reg_ypt=(1-wt)*8.0+wt*week_ypt
   # Apply YPT only to the receiving-yard fantasy-point component, not total projection.
   yard_delta=(float(r.get("rec_yards",0))*(reg_ypt/8.0-1.0))/10.0
   r[f"ppr_xtd75_ypt_{int(wt*100)}"]=round(p75+yard_delta,3)
  r["ppr_projection"]=p75;r["rec_tds"]=base_td;r["wr_routes_preweek"]=routes;r["wr_tprr_preweek"]=tprr;r["wr_xtd_week1"]=xtd;r["wr_ypt_week1"]=week_ypt
 return rows

def actual_usage_points(r):
 return float(r.get("fantasy_points_ppr",0) or 0)
for week in (1,2):
 x=load(week); prior=x["prior"]["half"]; hist=x["stats"].copy(); usage_detail=preweek_usage(hist); team_detail=team_volume(hist); def_mult=defense_multipliers(week); injuries=injury_factors(week)
 if len(hist):
  hist["k"]=hist.player_display_name.map(key)
  usage=hist.groupby("k",as_index=False).agg(games=("week","nunique"),ppr=("fantasy_points_ppr","mean"))
  um={r.k:r for _,r in usage.iterrows()}
 else: um={}
 rows=[]
 for p in prior:
  pos=p.get("pos")
  if pos not in ("QB","RB","WR","TE"): continue
  k=key(p.get("name")); q=um.get(k)
  score=prior_strength(p)
  # Convert frozen quality prior to a conservative weekly PPR baseline.
  base=POS_BASE[pos]*(0.70+0.006*min(100,max(0,score)))
  ud=usage_detail.get(k,{})
  td=team_detail.get(team(p.get("team")),{})
  standard,half,ppr,raw=project_from_usage(pos,p,ud,td)
  mm=float(def_mult.get(x["opponent"].get(team(p.get("team"))),1.0));standard*=mm;half*=mm;ppr*=mm
  af,status=injuries.get(k,(1.0,"NO HISTORICAL ADJUSTMENT"));standard*=af;half*=af;ppr*=af
  raw={z:float(v)*mm*af for z,v in raw.items()}
  raw.update({"_role_prior":score,"_pre_carries":ud.get("carries",0),"_pre_targets":ud.get("targets",0)})
  rows.append({"player":p["name"],"position":pos,"team":p.get("team"),"opponent":x["opponent"].get(team(p.get("team"))),"standard_projection":round(standard,3),"half_projection":round(half,3),"ppr_projection":round(ppr,3),"backtest_week":week,"runner_stage":"WR_85_15_XTD75_YPT_SWEEP","availability_factor":round(af,3),"historical_status":status,**{z:(round(v,3) if isinstance(v,(int,float)) else v) for z,v in raw.items()}})
 rows=constrain_rb_team(rows)
 rows=apply_rb_fp_experiment(rows,week)
 rows=apply_wr_route_tprr_experiment(rows,week,hist)
 pd.DataFrame(rows).to_csv(OUT/f"week{week}_projections.csv",index=False)
 print(f"Week {week}: wrote {len(rows)} V5 projections")
