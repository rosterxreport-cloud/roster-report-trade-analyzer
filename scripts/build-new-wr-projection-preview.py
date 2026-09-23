#!/usr/bin/env python3
import json,re,unicodedata
from pathlib import Path
import pandas as pd, numpy as np
STATS="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2026.csv"
PBP="https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet"
SCHED="https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
PROJECTION_AVAILABILITY={
 "nicocollins":{"week_factor":0.0,"ros_missed_games":4,"status":"IR"},
 "zayflowers":{"week_factor":0.0,"ros_missed_games":1,"status":"OUT"},
 "pukanacua":{"week_factor":0.50,"ros_missed_games":0,"status":"QUESTIONABLE"},
 "djmoore":{"week_factor":0.45,"ros_missed_games":0,"status":"WEEK 3 AVAILABILITY IN DOUBT"}
}
EXPECTED_WEEK3={"ATL":"GB","GB":"ATL","LAC":"BUF","BUF":"LAC","CAR":"CLE","CLE":"CAR","NYJ":"DET","DET":"NYJ","HOU":"IND","IND":"HOU","NE":"JAX","JAX":"NE","KC":"MIA","MIA":"KC","TEN":"NYG","NYG":"TEN","CIN":"PIT","PIT":"CIN","SEA":"WAS","WAS":"SEA","TB":"NO","NO":"TB","LV":"DEN","DEN":"LV","DAL":"BAL","BAL":"DAL","SF":"ARI","ARI":"SF","LAR":"MIN","MIN":"LAR","PHI":"CHI","CHI":"PHI"}
def key(v):
 v=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
 return re.sub(r"[^a-z0-9]","",re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",v))
def n(r,c):
 try:return max(0.,float(r.get(c,0) or 0))
 except:return 0.
stats=pd.read_csv(STATS,low_memory=False);stats=stats[stats.position.eq("WR")].copy();stats["k"]=stats.player_display_name.map(key)
# nflverse season stats can refresh between runs. The preview must not silently
# change historical inputs while we are tuning a fixed Week 3 model.
# Record a deterministic input snapshot in the artifact for auditability.
INPUT_SNAPSHOT_COLS=[x for x in ["player_id","player_display_name","games","targets","receptions","receiving_yards","receiving_tds","target_share","air_yards_share","receiving_air_yards"] if x in stats.columns]
Path("data/wr-projection-input-snapshot.json").write_text(stats[INPUT_SNAPSHOT_COLS].fillna("").to_json(orient="records",indent=2))
cols=["season_type","posteam","defteam","play_type","pass_attempt","complete_pass","yards_gained","epa","success","touchdown","yardline_100","receiver_player_id","receiving_yards","air_yards","pass_location"]
try: pbp=pd.read_parquet(PBP,columns=cols)
except Exception: pbp=pd.read_parquet(PBP)
pbp=pbp[pbp.season_type.eq("REG")].copy();pas=pbp[pd.to_numeric(pbp.pass_attempt,errors="coerce").fillna(0).eq(1)].copy()
pas["explosive"]=((pd.to_numeric(pas.complete_pass,errors="coerce").fillna(0)==1)&(pd.to_numeric(pas.yards_gained,errors="coerce").fillna(0)>=20)).astype(float)
pas["rz"]=(pd.to_numeric(pas.yardline_100,errors="coerce")<=20).fillna(False);pas["rztd"]=((pd.to_numeric(pas.touchdown,errors="coerce").fillna(0)==1)&pas.rz).astype(float)
dg=pas.groupby("defteam").agg(pass_epa=("epa","mean"),pass_success=("success","mean"),explosive=("explosive","mean"),rztd=("rztd","mean")).reset_index()
idpos=dict(zip(stats.player_id.astype(str),stats.position)) if "player_id" in stats.columns else {};pbp["receiver_position"]=pbp.receiver_player_id.astype(str).map(idpos)
wr=pbp[(pbp.play_type.eq("pass"))&(pbp.receiver_position.eq("WR"))].groupby("defteam").agg(wr_yards=("receiving_yards","sum"),wr_targets=("pass_attempt","sum")).reset_index()
dg=dg.merge(wr,on="defteam",how="left");dg["wr_ypt"]=dg.wr_yards/dg.wr_targets.replace(0,np.nan)
metrics=["pass_epa","pass_success","explosive","rztd","wr_ypt"]
for m in metrics:
 s=pd.to_numeric(dg[m],errors="coerce");dg[m+"_badpct"]=s.rank(pct=True).fillna(.5)
dg["def_bad"]=dg[[m+"_badpct" for m in metrics]].mean(axis=1);dg["matchup_mult"]=.35+(.65*(.88+.24*dg.def_bad));defmap=dict(zip(dg.defteam,dg.matchup_mult))
# Safe scoring opportunity map.
scoreopp={}
try:
 _t=pbp[pbp.receiver_player_id.notna()].copy()
 _t["_rz"]=(pd.to_numeric(_t["yardline_100"],errors="coerce")<=20).astype(float)
 _t["_ez"]=(pd.to_numeric(_t["yardline_100"],errors="coerce")<=10).astype(float)
 _t["_deep"]=(pd.to_numeric(_t["air_yards"],errors="coerce").fillna(0)>=20).astype(float)
 _so=_t.groupby("receiver_player_id").agg(rz_targets=("_rz","sum"),endzone_targets=("_ez","sum"),deep_targets=("_deep","sum"),pbp_targets=("receiver_player_id","count")).reset_index()
 scoreopp={str(r.receiver_player_id):{"rz_targets":float(r.rz_targets),"endzone_targets":float(r.endzone_targets),"deep_targets":float(r.deep_targets),"pbp_targets":float(r.pbp_targets)} for _,r in _so.iterrows()}
except Exception as e:
 print(f"Scoring-opportunity layer fallback: {e}")
oppmap={}
for _,sr in stats.iterrows():
 _pid=str(sr.get("player_id",""));_so=scoreopp.get(_pid,{})
 oppmap[_pid]={"target_share":sr.get("target_share",np.nan),"air_yard_share":sr.get("air_yards_share",sr.get("air_yard_share",np.nan)),"adot":(n(sr,"receiving_air_yards")/max(1.,n(sr,"targets"))) if n(sr,"receiving_air_yards") else np.nan,"rz_targets":_so.get("rz_targets",0),"endzone_targets":_so.get("endzone_targets",0),"deep_targets":_so.get("deep_targets",0),"pbp_targets":_so.get("pbp_targets",max(1.,n(sr,"targets")))}
# Upcoming opponent.
sch=pd.read_csv(SCHED,low_memory=False)
played = sch["result"].notna() if "result" in sch.columns else sch["home_score"].notna()
future=sch[(sch.season.eq(2026))&(~played)].sort_values("week")
# IMPORTANT: "this week" must mean the league's next chronological week,
# not each team's first unplayed game. This prevents stale/postponed rows or
# schedule quirks from assigning different NFL weeks to different players.
next_week=int(future["week"].min())
this_week=future[future["week"].eq(next_week)].copy()
# Normalize the few common abbreviation variants before matching rankings,
# schedules and nflverse defensive PBP.
TEAM_ALIAS={"LA":"LAR","JAC":"JAX","WSH":"WAS"}
def team(v):
 v=str(v or "").strip().upper()
 return TEAM_ALIAS.get(v,v)
# Use the verified official Week 3 slate as the authoritative weekly schedule.
# The nflverse schedule remains the source for the full remaining ROS schedule.
if next_week == 3:
 opp=dict(EXPECTED_WEEK3)
else:
 opp={}
 for _,gm in this_week.iterrows():
  h,a=team(gm.home_team),team(gm.away_team)
  opp[h]=a;opp[a]=h
schedule_by_team={}
for _,gm in future.iterrows():
 h,a=team(gm.home_team),team(gm.away_team)
 schedule_by_team.setdefault(h,[]).append(a)
 schedule_by_team.setdefault(a,[]).append(h)
print(f"Projection week: {next_week}; mapped teams: {len(opp)}")
if len(opp) != 32:
 raise SystemExit(f"Expected 32 team opponent mappings for Week {next_week}, got {len(opp)}")
# Normalize defensive keys too, so every mapped opponent can receive its defense.
defmap={team(k):v for k,v in defmap.items()}

defmap={team(k):v for k,v in defmap.items()}
db=json.loads(Path("players.json").read_text())["half"];ranked={key(p["name"]):p for p in db if p["pos"]=="WR"};rows=[];projected=set()
def emit(p,t,rec,ypr,td,source,op=None):
 avail=PROJECTION_AVAILABILITY.get(key(p["name"]),{"week_factor":1.0,"ros_missed_games":0,"status":"ACTIVE"})
 pr=min(100,int(p["posRank"]));op=op or {}
 def safe_float(v,default=np.nan):
  try:
   if v is None or pd.isna(v): return default
   return float(v)
  except: return default
 target_share=safe_float(op.get("target_share",np.nan));air_share=safe_float(op.get("air_yard_share",np.nan));adot=safe_float(op.get("adot",np.nan));rz_t=safe_float(op.get("rz_targets",0),0.);ez_t=safe_float(op.get("endzone_targets",0),0.);deep_t=safe_float(op.get("deep_targets",0),0.);pbp_t=max(1.,safe_float(op.get("pbp_targets",0),0.))
 strength=max(.65,min(1.20,float(p["analyticsScore"])/75.));value=max(.72,min(1.16,float(p["value"])/80.));role_targets=max(2.,min(11.0,11.0-(pr-1)*.085))
 share_targets=role_targets if np.isnan(target_share) else max(2.,min(12.,target_share*34.))
 # Two games of raw volume are too noisy for established high-ranked WRs.
 # Give the locked role baseline more weight while still allowing current
 # target share to identify genuine role changes.
 current_w=.34 if pr<=20 else .42
 role_w=.42 if pr<=20 else .34
 share_w=1.0-current_w-role_w
 tp=current_w*t+role_w*role_targets+share_w*share_targets if source!="ranking-role fallback" else role_targets
 catch=(rec/max(.1,t)) if t>0 else .65;rp=tp*max(.45,min(.82,.65*catch+.35*.65));# Early-season receiving depth/efficiency is noisy too. Regress established
 # WRs more strongly toward role-based priors, while allowing later-ranked WRs
 # to react faster to genuine role/efficiency changes.
 current_adot=12. if np.isnan(adot) else max(5.,min(22.,adot))
 role_adot=max(9.5,min(14.5,13.4-(pr-1)*.035))
 adot_current_w=.35 if pr<=20 else .50
 opp_adot=adot_current_w*current_adot+(1-adot_current_w)*role_adot
 role_ypr=max(10.5,min(14.5,13.8-(pr-1)*.035))
 ypr_current_w=.38 if pr<=20 else .52
 adj_ypr=ypr_current_w*ypr+(1-ypr_current_w)*role_ypr
 # aDOT still informs the yardage conversion, but no longer dominates it.
 adj_ypr=.78*adj_ypr+.22*opp_adot
 air_bonus=1.0 if np.isnan(air_share) else max(.92,min(1.08,.94+.24*air_share));rey=rp*max(8.,min(17.,adj_ypr*(.90+.06*strength+.04*value)*air_bonus))
 role_td=max(.08,min(.62,.62-(pr-1)*.006));rz_rate=rz_t/pbp_t;deep_rate=deep_t/pbp_t;ez_rate=ez_t/pbp_t;opp_td=max(.06,min(.70,.020*tp+.007*rey+.16*rz_rate+.18*ez_rate+.06*deep_rate));tdp=max(.04,min(.78,.25*td+.45*role_td+.30*opp_td));base=rey/10+rp*.5+tdp*6
 pt=team(p["team"]);opponent=opp.get(pt);mm=float(defmap.get(opponent,1.0));weekly=base*mm*float(avail["week_factor"]);ros_opps=schedule_by_team.get(pt,[]);mults=[float(defmap.get(o,1.0)) for o in ros_opps];left=len(ros_opps);miss=min(left,int(avail["ros_missed_games"]));active_mults=mults[miss:];ros=sum(base*m for m in active_mults);ppg=ros/left if left else 0
 rows.append({"rank":p["posRank"],"player":p["name"],"team":p["team"],"opponent":opponent,"defenseMultiplier":round(mm,3),"targets":round(tp,1),"receptions":round(rp,1),"recYds":round(rey,1),"TD":round(tdp,2),"baselineHalfPPR":round(base,1),"weeklyHalfPPR":round(weekly,1),"ROSgames":left,"ROSScheduleMultiplier":round(sum(mults)/left,3) if left else 1.0,"ROSHalfPPRperGame":round(ppg,1),"ROSpoints":round(ros,1),"targetShare":None if np.isnan(target_share) else round(target_share,3),"airYardShare":None if np.isnan(air_share) else round(air_share,3),"aDOT":None if np.isnan(adot) else round(adot,1),"rzTargets":int(rz_t),"endzoneTargets":int(ez_t),"deepTargets":int(deep_t),"availabilityStatus":avail["status"],"weekAvailability":avail["week_factor"],"projectedMissedROSGames":avail["ros_missed_games"],"projectionSource":source})
for _,r in stats.iterrows():
 k=r["k"]
 if k not in ranked: continue
 projected.add(k);g=max(1.,n(r,"games"));op=oppmap.get(str(r.get("player_id","")));emit(ranked[k],n(r,"targets")/g,n(r,"receptions")/g,n(r,"receiving_yards")/max(1.,n(r,"receptions")),n(r,"receiving_tds")/g,"2026 production + opportunity + ranking role",op)
for k,p in ranked.items():
 if k not in projected: emit(p,0,0,12,0,"ranking-role fallback")
# Redistribute a conservative share of unavailable WR opportunity to active
# same-team WRs, weighted by their existing projected target role. This affects
# weekly projections only; ROS remains independently availability-adjusted.
by_team={}
for x in rows: by_team.setdefault(team(x["team"]),[]).append(x)
for tm,grp in by_team.items():
 unavailable=[x for x in grp if float(x.get("weekAvailability",1.0))<1.0]
 active=[x for x in grp if float(x.get("weekAvailability",1.0))>=1.0]
 if not unavailable or not active: continue
 vacated=sum(float(x["targets"])*(1.0-float(x.get("weekAvailability",1.0))) for x in unavailable)
 # Only 65% of vacated WR targets are reassigned to WR teammates; the rest can
 # flow to TE/RB or disappear through changed play calling.
 pool=vacated*.65
 denom=sum(max(1.,float(x["targets"])) for x in active)
 for x in active:
  add=pool*(max(1.,float(x["targets"]))/denom)
  old_t=max(.1,float(x["targets"]));new_t=old_t+add;scale=new_t/old_t
  # Incremental targets retain the player's modeled catch/yard efficiency,
  # but TD expectation receives only a modest opportunity bump.
  old_week=float(x["weeklyHalfPPR"]);old_base=float(x["baselineHalfPPR"])
  rec=float(x["receptions"])*scale;yd=float(x["recYds"])*scale
  td=min(.90,float(x["TD"])+add*.025)
  new_base=yd/10+rec*.5+td*6
  x["targets"]=round(new_t,1);x["receptions"]=round(rec,1);x["recYds"]=round(yd,1);x["TD"]=round(td,2)
  x["weeklyHalfPPR"]=round(new_base*float(x["defenseMultiplier"]),1)
  x["redistributedTargets"]=round(add,1)
rows.sort(key=lambda x:x["weeklyHalfPPR"],reverse=True)
Path("data/new-wr-projection-preview.json").write_text(json.dumps(rows,indent=2));print(json.dumps(rows[:25],indent=2))
