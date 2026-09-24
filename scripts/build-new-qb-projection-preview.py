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
 "jaydendaniels":{"week_factor":0.0,"ros_missed_games":1,"status":"OUT WEEK 3 - ELBOW"},
 "calebwilliams":{"week_factor":0.0,"ros_missed_games":1,"status":"OUT WEEK 3 - HAMSTRING"},
 "jaxsondart":{"week_factor":0.0,"ros_missed_games":1,"status":"OUT WEEK 3 - KNEE"},
 "samdarnold":{"week_factor":0.55,"ros_missed_games":0,"status":"WEEK 3 QUESTIONABLE - GLUTE"},
 "tuatagovailoa":{"week_factor":0.0,"ros_missed_games":0,"status":"NOT WEEK 3 STARTER - OBLIQUE"},
 "russellwilson":{"week_factor":0.0,"ros_missed_games":0,"status":"NOT ACTIVE WEEK 3 QB"},
 "macjones":{"week_factor":0.0,"ros_missed_games":0,"status":"BACKUP - NO STARTER PROJECTION"},
 "jjmccarthy":{"week_factor":0.0,"ros_missed_games":0,"status":"QB3 - NO STARTER PROJECTION"},
 "derekcarr":{"week_factor":0.0,"ros_missed_games":0,"status":"NOT ACTIVE WEEK 3 QB"},

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
 team_pass_pg={str(k).strip().upper():float(_atts[k])/max(1.,float(_games[k])) for k in _atts.index}
except Exception as ex:
 print(f"Team pass-volume fallback: {ex}")
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
# Week 3 starter eligibility is an allow-list, not a blacklist. Only the current
# starter/expected starter for each team can receive a weekly projection.
# Update this map from current depth charts/injury news before each weekly run.
WEEK_STARTER={
 "BUF":"Josh Allen","MIA":"Malik Willis","NE":"Drake Maye","NYJ":"Geno Smith",
 "BAL":"Lamar Jackson","CIN":"Joe Burrow","CLE":"Deshaun Watson","PIT":"Aaron Rodgers",
 "HOU":"C.J. Stroud","IND":"Daniel Jones","JAX":"Trevor Lawrence","TEN":"Cam Ward",
 "DEN":"Bo Nix","KC":"Patrick Mahomes","LAC":"Justin Herbert","LV":"Kirk Cousins",
 "DAL":"Dak Prescott","NYG":"Jameis Winston","PHI":"Jalen Hurts","WAS":"Marcus Mariota",
 "CHI":"Case Keenum","DET":"Jared Goff","GB":"Jordan Love","MIN":"Kyler Murray",
 "ATL":"Michael Penix Jr.","CAR":"Bryce Young","NO":"Tyler Shough","TB":"Baker Mayfield",
 "ARI":"Jacoby Brissett","LAR":"Matthew Stafford","SF":"Brock Purdy","SEA":"Drew Lock"
}
if set(WEEK_STARTER)!=set(EXPECTED_WEEK3):
 raise SystemExit(f"QB starter teams do not equal Week 3 schedule teams: missing={set(EXPECTED_WEEK3)-set(WEEK_STARTER)}, extra={set(WEEK_STARTER)-set(EXPECTED_WEEK3)}")
_norm=[key(v) for v in WEEK_STARTER.values()]
if len(WEEK_STARTER)!=32 or len(set(_norm))!=32: raise SystemExit("QB starter map must contain 32 unique teams/QBs")
STARTER_TEAM={key(v):t for t,v in WEEK_STARTER.items()};STARTER_KEYS=set(STARTER_TEAM)
db=json.loads(Path("players.json").read_text())["half"]
ranked={key(p["name"]):p for p in db if p["pos"]=="QB"}
# Starter profiles are independent of trade-rank inclusion. If a confirmed starter
# is absent from players.json, create a neutral profile solely for weekly projection.
for _t,_name in WEEK_STARTER.items():
 _k=key(_name)
 if _k not in ranked: ranked[_k]={"name":_name,"team":_t,"pos":"QB","posRank":32}
# QB-level 2026 production comes from nflverse player stats, whose player_id is
# the canonical GSIS key and player_display_name is the full name. This avoids
# brittle matching against abbreviated PBP passer names.
q=stats.copy()
# Established QB rushing role priors. Early-season rushing TDs are too volatile to
# extrapolate directly, so blend 2026 with stable career/role archetypes.
RUSH_PRIOR={"jalenhurts":{"carries":9.0,"rush_td":0.65},"joshallen":{"carries":7.0,"rush_td":0.55},"lamarjackson":{"carries":8.5,"rush_td":0.30},"jayden daniels":{"carries":8.0,"rush_td":0.35},"calebwilliams":{"carries":5.5,"rush_td":0.20},"patrickmahomes":{"carries":4.0,"rush_td":0.15},"kyler murray":{"carries":6.0,"rush_td":0.25}}
RUSH_PRIOR={key(k):v for k,v in RUSH_PRIOR.items()}
for _col in ["attempts","completions","passing_yards","passing_tds","passing_interceptions","passing_air_yards","carries","rushing_yards","rushing_tds","games"]:
 if _col not in q.columns: q[_col]=0
# Season stats are already aggregated; use normalized full display names to join
# directly to the curated rankings roster.
rows=[];seen=set()
for _,r in q.iterrows():
 k=key(r.get("player_display_name",""))
 if k not in ranked or k not in STARTER_KEYS: continue
 p=ranked[k]
 if team(p["team"]) != STARTER_TEAM[k]: continue
 seen.add(k);g=max(1.,float(r.get("games",0) or 0))
 att=float(r.get("attempts",0) or 0)/g;comp=float(r.get("completions",0) or 0)/g;py=float(r.get("passing_yards",0) or 0)/g;ptd=float(r.get("passing_tds",0) or 0)/g;ints=float(r.get("passing_interceptions",0) or 0)/g
 ay=float(r.get("passing_air_yards",0) or 0)/g;ypa=py/max(1.,att);aypa=ay/max(1.,att)
 car=float(r.get("carries",0) or 0)/g;ry=float(r.get("rushing_yards",0) or 0)/g;rtd=float(r.get("rushing_tds",0) or 0)/g
 pr=min(50,int(p["posRank"]))
 # Early-season passing priors should not be derived from fantasy rank. Anchor
 # volume and efficiency to league-average QB rates, then let actual 2026 usage
 # move the projection. This prevents hot starts from being amplified by rank.
 team_att=team_pass_pg.get(team(p["team"]),32.5)
 role_att=max(27.,min(40.,team_att))
 patt=.60*att+.40*role_att
 pypa=.40*ypa+.60*7.15
 paypa=.40*aypa+.60*8.15
 pcomp=max(.54,min(.74,.45*(comp/max(1.,att))+.55*.645))
 pyd=patt*pypa;pcompn=patt*pcomp;pair=patt*paypa
 # TD/INT rates are highly volatile through two games. Regress more heavily than
 # yardage efficiency so six early TDs do not become a 3-TD weekly expectation.
 td_rate=.25*(ptd/max(1.,att))+.75*.045
 int_rate=.30*(ints/max(1.,att))+.70*.022
 pptd=patt*td_rate;pint=patt*int_rate
 rp=RUSH_PRIOR.get(k);role_car=(rp["carries"] if rp else max(1.5,min(5.0,4.2-(pr-1)*.05)))
 pcar=.45*car+.55*role_car
 ypc=ry/max(1.,car) if car else 4.5;pry=pcar*max(3.0,min(7.0,.45*ypc+.55*4.8))
 role_rtd=(rp["rush_td"] if rp else .10)
 # Rushing TDs are especially noisy over two games: 20% current season, 80% role.
 prtd=.20*rtd+.80*role_rtd
 # Guard against two-game TD spikes even for elite rushing QBs.
 prtd=min(prtd,.75)
 pt=team(p["team"]);opponent=opp.get(pt);mm=float(defmap.get(opponent,1.0))
 avail=AUTO_AVAILABILITY.get(k,{"week_factor":1.0,"ros_missed_games":0,"status":"ACTIVE","source":"default-active"}).copy();avail.update(PROJECTION_AVAILABILITY.get(k,{}))
 base=pyd*.04+pptd*4-pint*2+pry*.1+prtd*6;fp=base*mm*float(avail["week_factor"])
 ros_opps=schedule_by_team.get(pt,[]);mults=[float(defmap.get(o,1.0)) for o in ros_opps];rosppg=base*(sum(mults)/len(mults) if mults else 1)
 rows.append({"rank":p["posRank"],"player":p["name"],"team":p["team"],"opponent":opponent,"passAttempts":round(patt,1),"completions":round(pcompn,1),"passYards":round(pyd,1),"passTD":round(pptd,2),"INT":round(pint,2),"yardsPerAttempt":round(pypa,2),"airYards":round(pair,1),"airYardsPerAttempt":round(paypa,2),"carries":round(pcar,1),"rushYards":round(pry,1),"rushTD":round(prtd,2),"weeklyPoints":round(fp,1),"ROSpointsPerGame":round(rosppg,1),"availabilityStatus":avail["status"],"weekAvailability":avail["week_factor"],"projectionSource":"2026 player stats + ranking role"})
# Confirmed starters without a 2026 sample use a conservative prior pathway.
# It uses current team pass volume, neutral NFL efficiency baselines, established
# rushing archetype when known, and the same opponent/injury layers. It never
# invents 2026 player production.
for k,p in ranked.items():
 if k in seen or k not in STARTER_KEYS: continue
 if team(p["team"]) != STARTER_TEAM[k]: continue
 pt=team(p["team"]);opponent=opp.get(pt);mm=float(defmap.get(opponent,1.0))
 patt=max(27.,min(39.,team_pass_pg.get(pt,32.5)))
 pcomp=.635;pypa=7.0;paypa=8.0
 pcompn=patt*pcomp;pyd=patt*pypa;pair=patt*paypa
 pptd=patt*.042;pint=patt*.024
 rp=RUSH_PRIOR.get(k);pcar=(rp["carries"] if rp else 2.5)
 pry=pcar*4.5;prtd=(rp["rush_td"] if rp else .10)
 avail=AUTO_AVAILABILITY.get(k,{"week_factor":1.0,"ros_missed_games":0,"status":"ACTIVE","source":"default-active"}).copy();avail.update(PROJECTION_AVAILABILITY.get(k,{}))
 base=pyd*.04+pptd*4-pint*2+pry*.1+prtd*6;fp=base*mm*float(avail["week_factor"])
 ros_opps=schedule_by_team.get(pt,[]);mults=[float(defmap.get(o,1.0)) for o in ros_opps];rosppg=base*(sum(mults)/len(mults) if mults else 1)
 rows.append({"rank":p["posRank"],"player":p["name"],"team":p["team"],"opponent":opponent,"passAttempts":round(patt,1),"completions":round(pcompn,1),"passYards":round(pyd,1),"passTD":round(pptd,2),"INT":round(pint,2),"yardsPerAttempt":round(pypa,2),"airYards":round(pair,1),"airYardsPerAttempt":round(paypa,2),"carries":round(pcar,1),"rushYards":round(pry,1),"rushTD":round(prtd,2),"weeklyPoints":round(fp,1),"ROSpointsPerGame":round(rosppg,1),"availabilityStatus":avail["status"],"weekAvailability":avail["week_factor"],"projectionSource":"no-2026-sample starter prior"})
rows.sort(key=lambda x:(x.get("weeklyPoints") is not None,x.get("weeklyPoints") or -999),reverse=True)
# Weekly output must be exactly one record per team. Fail loudly rather than
# silently publish an incomplete/duplicated quarterback slate.
_outteams=[team(x["team"]) for x in rows]
if len(rows)!=32 or len(set(_outteams))!=32 or set(_outteams)!=set(WEEK_STARTER):
 raise SystemExit(f"QB projection integrity failure: rows={len(rows)} uniqueTeams={len(set(_outteams))} missing={set(WEEK_STARTER)-set(_outteams)}")
Path("data/new-qb-projection-preview.json").write_text(json.dumps(rows,indent=2))
print(json.dumps(rows[:25],indent=2))
