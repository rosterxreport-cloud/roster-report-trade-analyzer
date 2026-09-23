#!/usr/bin/env python3
import json,re,unicodedata
from pathlib import Path
import pandas as pd, numpy as np
STATS="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2026.csv"
PBP="https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet"
PBP25="https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.parquet"
SCHED="https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
INJURY_FILE=Path("injury-adjustments.json")
PROJECTION_AVAILABILITY={
 "nicocollins":{"week_factor":0.0,"ros_missed_games":4,"status":"IR"},
 "zayflowers":{"week_factor":0.0,"ros_missed_games":1,"status":"OUT"},
 "pukanacua":{"week_factor":0.50,"ros_missed_games":0,"status":"QUESTIONABLE"},
 "djmoore":{"week_factor":0.45,"ros_missed_games":0,"status":"WEEK 3 AVAILABILITY IN DOUBT"},
 "jordyntyson":{"week_factor":0.0,"ros_missed_games":4,"status":"IR"},
 "dezhawnstribling":{"week_factor":0.0,"ros_missed_games":4,"status":"IR"},
 "ajbrown":{"week_factor":0.0,"ros_missed_games":3,"status":"IR"}
}
EXPECTED_WEEK3={"ATL":"GB","GB":"ATL","LAC":"BUF","BUF":"LAC","CAR":"CLE","CLE":"CAR","NYJ":"DET","DET":"NYJ","HOU":"IND","IND":"HOU","NE":"JAX","JAX":"NE","KC":"MIA","MIA":"KC","TEN":"NYG","NYG":"TEN","CIN":"PIT","PIT":"CIN","SEA":"WAS","WAS":"SEA","MIN":"TB","TB":"MIN","LV":"NO","NO":"LV","DAL":"BAL","BAL":"DAL","SF":"ARI","ARI":"SF","LAR":"DEN","DEN":"LAR","PHI":"CHI","CHI":"PHI"}
def key(v):
 v=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
 return re.sub(r"[^a-z0-9]","",re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",v))
def n(r,c):
 try:return max(0.,float(r.get(c,0) or 0))
 except:return 0.
# Automatic projection availability from the repository's refreshed injury layer.
# Confirmed IR/PUP/NFI/OUT/inactive/unavailable statuses are zero for the current
# week. Questionable/doubtful players use the maintained availability/workload
# factors. Manual entries below remain only as explicit projection overrides.
AUTO_AVAILABILITY={}
try:
 _inj=json.loads(INJURY_FILE.read_text()).get("players",{})
 for _name,_x in _inj.items():
  _status=str(_x.get("status","") or "").upper()
  _avail=float(_x.get("availability",1) or 0);_work=float(_x.get("workload",1) or 0)
  _confirmed=any(z in _status for z in ["IR ","IR -","INJURED RESERVE","PUP","NFI","OUT ","INACTIVE","UNAVAILABLE"])
  if _confirmed: _wf=0.0
  elif "DOUBTFUL" in _status: _wf=min(.25,_avail*_work)
  elif "QUESTIONABLE" in _status or "GAME-TIME" in _status: _wf=max(0.,min(1.,_avail*_work))
  else: _wf=max(0.,min(1.,_avail*_work))
  AUTO_AVAILABILITY[key(_name)]={"week_factor":_wf,"ros_missed_games":0,"status":str(_x.get("status","ACTIVE")),"source":"injury-adjustments.json"}
except Exception as ex:
 print(f"Automatic injury availability fallback: {ex}")
stats=pd.read_csv(STATS,low_memory=False);stats=stats[stats.position.eq("QB")].copy();stats["k"]=stats.player_display_name.map(key)
# nflverse season stats can refresh between runs. The preview must not silently
# change historical inputs while we are tuning a fixed Week 3 model.
# Record a deterministic input snapshot in the artifact for auditability.
INPUT_SNAPSHOT_COLS=[x for x in ["player_id","player_display_name","recent_team","games","targets","receptions","receiving_yards","receiving_tds","target_share","air_yards_share","receiving_air_yards"] if x in stats.columns]
Path("data/wr-projection-input-snapshot.json").write_text(stats[INPUT_SNAPSHOT_COLS].fillna("").to_json(orient="records",indent=2))
cols=["game_id","season_type","posteam","defteam","play_type","pass_attempt","complete_pass","yards_gained","epa","success","touchdown","yardline_100","passer_player_id","passer_player_name","passing_yards","pass_touchdown","interception","air_yards","rusher_player_id","rushing_yards","rush_attempt","rush_touchdown"]
try: pbp=pd.read_parquet(PBP,columns=cols)
except Exception: pbp=pd.read_parquet(PBP)
pbp=pbp[pbp.season_type.eq("REG")].copy();pas=pbp[pd.to_numeric(pbp.pass_attempt,errors="coerce").fillna(0).eq(1)].copy()
pas["explosive"]=((pd.to_numeric(pas.complete_pass,errors="coerce").fillna(0)==1)&(pd.to_numeric(pas.yards_gained,errors="coerce").fillna(0)>=20)).astype(float)
pas["rz"]=(pd.to_numeric(pas.yardline_100,errors="coerce")<=20).fillna(False);pas["rztd"]=((pd.to_numeric(pas.touchdown,errors="coerce").fillna(0)==1)&pas.rz).astype(float)
dg=pas.groupby("defteam").agg(pass_epa=("epa","mean"),pass_success=("success","mean"),explosive=("explosive","mean"),rztd=("rztd","mean")).reset_index()
# QB defensive environment: passing efficiency allowed, explosive rate, and red-zone TD rate.
dg["def_bad"]=dg[["pass_epa_badpct","pass_success_badpct","explosive_badpct","rztd_badpct"]].mean(axis=1) if "pass_epa_badpct" in dg else .5
# Rebuild percentile columns for QB-relevant defensive metrics.
for m in ["pass_epa","pass_success","explosive","rztd"]:
 s=pd.to_numeric(dg[m],errors="coerce");dg[m+"_badpct"]=s.rank(pct=True).fillna(.5)
dg["def_bad"]=dg[[m+"_badpct" for m in ["pass_epa","pass_success","explosive","rztd"]]].mean(axis=1)
dg["matchup_mult"]=.35+(.65*(.88+.24*dg.def_bad));defmap=dict(zip(dg.defteam,dg.matchup_mult))
# Actual 2026 team pass attempts/game from PBP. Use each player's own offense
# rather than a league-wide arbitrary attempts baseline.
team_pass_pg={}
try:
 _pass=pbp[pbp["pass_attempt"].fillna(0).eq(1)].copy()
 _games=_pass.groupby("posteam")["game_id"].nunique()
 _atts=_pass.groupby("posteam")["pass_attempt"].sum()
 team_pass_pg={team(k):float(_atts[k])/max(1.,float(_games[k])) for k in _atts.index}
except Exception as ex:
 print(f"Team pass-volume fallback: {ex}")
# Safe scoring opportunity map: blend 2025 stability with 2026 role.
scoreopp={}
try:
 try: pbp25=pd.read_parquet(PBP25,columns=cols)
 except Exception: pbp25=pd.read_parquet(PBP25)
 pbp25=pbp25[pbp25.season_type.eq("REG")].copy()
 def scoring_rates(frame):
  t=frame[frame.receiver_player_id.notna()].copy()
  t["_rz"]=(pd.to_numeric(t["yardline_100"],errors="coerce")<=20).astype(float)
  t["_ez"]=(pd.to_numeric(t["yardline_100"],errors="coerce")<=10).astype(float)
  t["_deep"]=(pd.to_numeric(t["air_yards"],errors="coerce").fillna(0)>=20).astype(float)
  g=t.groupby("receiver_player_id").agg(rz=("_rz","sum"),ez=("_ez","sum"),deep=("_deep","sum"),n=("receiver_player_id","count"))
  return {str(pid):{"rz":float(r.rz)/max(1.,float(r.n)),"ez":float(r.ez)/max(1.,float(r.n)),"deep":float(r.deep)/max(1.,float(r.n)),"n":float(r.n)} for pid,r in g.iterrows()}
 r25=scoring_rates(pbp25);r26=scoring_rates(pbp)
 for pid in set(r25)|set(r26):
  a,b=r25.get(pid),r26.get(pid)
  if a and b: rz=.65*a["rz"]+.35*b["rz"];ez=.65*a["ez"]+.35*b["ez"];deep=.65*a["deep"]+.35*b["deep"];sample_n=max(1.,b["n"])
  elif b: rz,ez,deep,sample_n=b["rz"],b["ez"],b["deep"],max(1.,b["n"])
  else: rz,ez,deep,sample_n=a["rz"],a["ez"],a["deep"],max(1.,a["n"])
  scoreopp[pid]={"rz_targets":rz*sample_n,"endzone_targets":ez*sample_n,"deep_targets":deep*sample_n,"pbp_targets":sample_n}
except Exception as ex:
 print(f"Scoring-opportunity blend fallback: {ex}")
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
db=json.loads(Path("players.json").read_text())["half"]
ranked={key(p["name"]):p for p in db if p["pos"]=="QB"}
# QB-level 2026 production comes from nflverse player stats, whose player_id is
# the canonical GSIS key and player_display_name is the full name. This avoids
# brittle matching against abbreviated PBP passer names.
q=stats.copy()
for _col in ["attempts","completions","passing_yards","passing_tds","passing_interceptions","passing_air_yards","carries","rushing_yards","rushing_tds","games"]:
 if _col not in q.columns: q[_col]=0
# Season stats are already aggregated; use normalized full display names to join
# directly to the curated rankings roster.
rows=[];seen=set()
for _,r in q.iterrows():
 k=key(r.get("player_display_name",""))
 if k not in ranked: continue
 p=ranked[k];seen.add(k);g=max(1.,float(r.get("games",0) or 0))
 att=float(r.get("attempts",0) or 0)/g;comp=float(r.get("completions",0) or 0)/g;py=float(r.get("passing_yards",0) or 0)/g;ptd=float(r.get("passing_tds",0) or 0)/g;ints=float(r.get("passing_interceptions",0) or 0)/g
 ay=float(r.get("passing_air_yards",0) or 0)/g;ypa=py/max(1.,att);aypa=ay/max(1.,att)
 car=float(r.get("carries",0) or 0)/g;ry=float(r.get("rushing_yards",0) or 0)/g;rtd=float(r.get("rushing_tds",0) or 0)/g
 pr=min(50,int(p["posRank"]));role_att=max(26.,min(39.,37.5-(pr-1)*.28))
 patt=.55*att+.45*role_att
 role_ypa=max(6.5,min(8.4,8.15-(pr-1)*.035));pypa=.45*ypa+.55*role_ypa
 role_aypa=max(6.8,min(9.6,9.1-(pr-1)*.04));paypa=.45*aypa+.55*role_aypa
 pcomp=max(.54,min(.74,.55*(comp/max(1.,att))+.45*.645))
 pyd=patt*pypa;pcompn=patt*pcomp;pair=patt*paypa
 td_rate=.40*(ptd/max(1.,att))+.60*.045;int_rate=.40*(ints/max(1.,att))+.60*.022
 pptd=patt*td_rate;pint=patt*int_rate
 role_car=max(1.5,min(7.5,5.8-(pr-1)*.08));pcar=.55*car+.45*role_car
 ypc=ry/max(1.,car) if car else 4.5;pry=pcar*max(3.0,min(7.0,.55*ypc+.45*4.8));prtd=.45*rtd+.55*.18
 pt=team(p["team"]);opponent=opp.get(pt);mm=float(defmap.get(opponent,1.0))
 avail=AUTO_AVAILABILITY.get(k,{"week_factor":1.0,"ros_missed_games":0,"status":"ACTIVE","source":"default-active"}).copy()
 base=pyd*.04+pptd*4-pint*2+pry*.1+prtd*6;fp=base*mm*float(avail["week_factor"])
 ros_opps=schedule_by_team.get(pt,[]);mults=[float(defmap.get(o,1.0)) for o in ros_opps];rosppg=base*(sum(mults)/len(mults) if mults else 1)
 rows.append({"rank":p["posRank"],"player":p["name"],"team":p["team"],"opponent":opponent,"passAttempts":round(patt,1),"completions":round(pcompn,1),"passYards":round(pyd,1),"passTD":round(pptd,2),"INT":round(pint,2),"yardsPerAttempt":round(pypa,2),"airYards":round(pair,1),"airYardsPerAttempt":round(paypa,2),"carries":round(pcar,1),"rushYards":round(pry,1),"rushTD":round(prtd,2),"weeklyPoints":round(fp,1),"ROSpointsPerGame":round(rosppg,1),"availabilityStatus":avail["status"],"weekAvailability":avail["week_factor"],"projectionSource":"2026 player stats + ranking role"})
for k,p in ranked.items(): bylast.setdefault(lname(p["name"]),[]).append((k,p))
rows=[];seen=set()
for _,r in q.iterrows():
 cand=bylast.get(lname(r["passer_player_name"]),[])
 if len(cand)!=1: continue
 k,p=cand[0];seen.add(k);g=max(1.,float(r["games"]))
 att=float(r["attempts"])/g;comp=float(r["completions"])/g;py=float(r["pass_yards"])/g;ptd=float(r["pass_td"])/g;ints=float(r["interceptions"])/g
 ay=float(r["air_yards"])/g;ypa=py/max(1.,att);aypa=ay/max(1.,att)
 car=float(r["carries"])/g;ry=float(r["rush_yards"])/g;rtd=float(r["rush_td"])/g
 pr=min(50,int(p["posRank"]));role_att=max(26.,min(39.,37.5-(pr-1)*.28))
 # Stabilize two-game passing volume/efficiency with role priors.
 patt=.55*att+.45*role_att
 role_ypa=max(6.5,min(8.4,8.15-(pr-1)*.035));pypa=.45*ypa+.55*role_ypa
 role_aypa=max(6.8,min(9.6,9.1-(pr-1)*.04));paypa=.45*aypa+.55*role_aypa
 pcomp=max(.54,min(.74,.55*(comp/max(1.,att))+.45*.645))
 pyd=patt*pypa;pcompn=patt*pcomp;pair=patt*paypa
 # Regress TD/INT rates aggressively early in season.
 td_rate=.40*(ptd/max(1.,att))+.60*.045;int_rate=.40*(ints/max(1.,att))+.60*.022
 pptd=patt*td_rate;pint=patt*int_rate
 # Preserve real QB rushing signal while preventing two-game spikes.
 role_car=max(1.5,min(7.5,5.8-(pr-1)*.08));pcar=.55*car+.45*role_car
 ypc=ry/max(1.,car) if car else 4.5;pry=pcar*max(3.0,min(7.0,.55*ypc+.45*4.8))
 prtd=.45*rtd+.55*.18
 pt=team(p["team"]);opponent=opp.get(pt);mm=float(defmap.get(opponent,1.0))
 avail=AUTO_AVAILABILITY.get(key(p["name"]),{"week_factor":1.0,"ros_missed_games":0,"status":"ACTIVE","source":"default-active"}).copy()
 fp=(pyd*.04+pptd*4-pint*2+pry*.1+prtd*6)*mm*float(avail["week_factor"])
 ros_opps=schedule_by_team.get(pt,[]);mults=[float(defmap.get(o,1.0)) for o in ros_opps];base=(pyd*.04+pptd*4-pint*2+pry*.1+prtd*6);rosppg=base*(sum(mults)/len(mults) if mults else 1)
 rows.append({"rank":p["posRank"],"player":p["name"],"team":p["team"],"opponent":opponent,"passAttempts":round(patt,1),"completions":round(pcompn,1),"passYards":round(pyd,1),"passTD":round(pptd,2),"INT":round(pint,2),"yardsPerAttempt":round(pypa,2),"airYards":round(pair,1),"airYardsPerAttempt":round(paypa,2),"carries":round(pcar,1),"rushYards":round(pry,1),"rushTD":round(prtd,2),"weeklyPoints":round(fp,1),"ROSpointsPerGame":round(rosppg,1),"availabilityStatus":avail["status"],"weekAvailability":avail["week_factor"]})
for k,p in ranked.items():
 if k in seen: continue
 # Do not fabricate a detailed stat line for unmatched QBs; expose them as fallback.
 rows.append({"rank":p["posRank"],"player":p["name"],"team":p["team"],"opponent":opp.get(team(p["team"])),"projectionSource":"ranking-role fallback","weeklyPoints":None})
rows.sort(key=lambda x:(x.get("weeklyPoints") is not None,x.get("weeklyPoints") or -999),reverse=True)
Path("data/new-qb-projection-preview.json").write_text(json.dumps(rows,indent=2))
print(json.dumps(rows[:25],indent=2))
