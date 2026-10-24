#!/usr/bin/env python3
"""Week 7 projection: retain the repository structural v4 model; Weeks 1-6 are input only."""
import pandas as pd, numpy as np, sys, json
from pathlib import Path
sys.path.insert(0,"scripts")
from projection_v4_backtest import project, score
URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.parquet"
INPUTS=Path("data/projections/inputs/week7")
w=pd.read_parquet(INPUTS/"player_stats.parquet")
assert w.loc[w.season_type.eq("REG"),"week"].max()>=6, "Missing Week 6 stats"
w=w[(w.season_type=="REG")&w.week.between(1,6)&w.position.isin(["QB","RB","WR","TE"])].copy()
if "recent_team" not in w:w["recent_team"]=w["team"]
cols=["attempts","completions","passing_yards","passing_tds","interceptions","carries","rushing_yards","rushing_tds","targets","receptions","receiving_yards","receiving_tds"]
if "interceptions" not in w and "passing_interceptions" in w: w["interceptions"]=w["passing_interceptions"]
for c in cols:
 if c not in w:w[c]=0
 w[c]=pd.to_numeric(w[c],errors="coerce").fillna(0)
w=w.sort_values(["player_id","week"])
# Four-week rolling history, using the SAME alpha and structural project() as v4.
last=w.groupby("player_id",as_index=False).tail(1).copy()
for c in cols:
 last["pre_"+c]=w.groupby("player_id")[c].transform(lambda s:s.ewm(alpha=.45,adjust=False).mean()).loc[last.index]
team=w.groupby(["recent_team","week"],as_index=False).agg(team_pass=("attempts","sum"),team_carries=("carries","sum"))
for c in ["team_pass","team_carries"]:
 team["pre_"+c]=team.groupby("recent_team")[c].transform(lambda s:s.ewm(alpha=.45,adjust=False).mean())
last=last.merge(team.sort_values("week").groupby("recent_team",as_index=False).tail(1)[["recent_team","pre_team_pass","pre_team_carries"]],on="recent_team",how="left")
last["week"]=7
# Select meaningful prior usage, no Week 7 outcome leakage.
last["prior_opp"]=last.pre_attempts.fillna(0)+last.pre_carries.fillna(0)+last.pre_targets.fillna(0)*1.5
schedule_all=pd.read_csv(INPUTS/"games.csv")
week_games=schedule_all[schedule_all.week.eq(7)]
assert len(week_games)==14, "Incomplete Week 7 schedule"
games=list(zip(week_games.away_team,week_games.home_team))
opponents={a:b for a,b in games};opponents.update({b:a for a,b in games})
last=last[last.recent_team.isin(opponents)].copy()
last=last[last.prior_opp>=1].copy()
# Consistent low-usage role gate. Weekly player stats do not include snap shares;
# use observed opportunities, never label this as a measured snap percentage.
recent_usage=w[w.week.between(1,6)].copy()
recent_usage["opportunities"]=recent_usage.carries+recent_usage.targets+recent_usage.attempts
role=recent_usage.groupby("player_id").agg(
 role_games=("week","nunique"),
 role_opportunities=("opportunities","sum"),
 role_active_weeks=("opportunities",lambda x:int((x>=3).sum())),
 role_targets=("targets","sum"),
 role_carries=("carries","sum")
).reset_index()
last=last.merge(role,on="player_id",how="left")
# Players with a consistently tiny role should not accumulate substantial
# projections simply from team volume scaling. Preserve newly elevated roles
# only when at least one recent week shows meaningful opportunity.
fringe=(last.position.ne("QB") & last.role_games.ge(2)
        & last.role_opportunities.le(6)
        & last.role_active_weeks.eq(0))
last=last[~fringe].copy()

# Actual PFR offensive snap share, Weeks 4-6 (nflverse).
# Fail closed if the dataset/schema is unavailable rather than silently reverting
# to opportunities-only and mislabeling the output as snap-validated.
snap_url="https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_2026.parquet"
snaps=pd.read_parquet(INPUTS/"snaps.parquet")
assert snaps.week.max()>=6, "Missing Week 6 snap data"
required={"season","week","team","player","offense_pct","offense_snaps"}
missing=required-set(snaps.columns)
if missing:raise RuntimeError(f"Snap data missing required columns: {sorted(missing)}")
snaps=snaps[(snaps.season==2026)&snaps.week.between(4,6)].copy()
snaps["offense_pct"]=pd.to_numeric(snaps.offense_pct,errors="coerce")
snaps["offense_snaps"]=pd.to_numeric(snaps.offense_snaps,errors="coerce")
# PFR uses percentage units 0-100; convert only if needed.
if snaps.offense_pct.dropna().median()>1:snaps["offense_pct"]/=100
snaps["snap_name"]=snaps.player.astype(str).str.lower().str.replace(r"[^a-z0-9]","",regex=True)
last["snap_name"]=last.player_display_name.astype(str).str.lower().str.replace(r"[^a-z0-9]","",regex=True)
# Resolve common source naming differences before matching.
# Prefer team-constrained exact matches; never match on surname alone.
aliases={
 "ajbrown":"ajbrown","brianthomasjr":"brianthomas",
 "deebosamuelsr":"deebosamuel","michaelpenixjr":"michaelpenix",
 "haroldfanninjr":"haroldfannin","brianrobinson":"brianrobinsonjr",
 "olliegordonii":"olliegordon","chrisrodriguezjr":"chrisrodriguez",
 "marvinmimsjr":"marvinmims","michaelpittman":"michaelpittmanjr",
 "jord mason":"jordanmason"
}
# Only apply an alias when the corresponding team/player actually exists
# in the snap dataset; otherwise leave the record visibly unmatched.
snap_keys=set(zip(snaps.team,snaps.snap_name))
for idx in last.index:
 key=last.at[idx,"snap_name"];team_code=last.at[idx,"recent_team"]
 candidate=aliases.get(key)
 if candidate and (team_code,candidate) in snap_keys:
  last.at[idx,"snap_name"]=candidate
snaps=snaps[snaps.offense_pct.between(0,1)]
snap_role=snaps.groupby(["team","snap_name"]).agg(
 snap_games=("week","nunique"),
 avg_snap_share=("offense_pct","mean"),
 recent_snap_share=("offense_pct","last"),
 snap_max=("offense_pct","max")
).reset_index().rename(columns={"team":"recent_team"})
last=last.merge(snap_role,on=["recent_team","snap_name"],how="left",validate="many_to_one")
# Only filter genuinely consistent low participation, not new breakout roles.
# Require 2+ observed games and no recent game above 20% snaps.
tiny=(last.position.ne("QB") & last.snap_games.ge(2) &
      last.avg_snap_share.lt(.15) & last.snap_max.lt(.20))
last=last[~tiny].copy()
# Do not let unmapped players quietly receive a high-volume projection.
last["Snap_Share_3W"]=last.avg_snap_share
last["Snap_Games"]=last.snap_games
# Explicitly mark unmatched snap records for auditing; do not treat as zero snaps.
last["Snap_Data_Status"]=np.where(last.avg_snap_share.notna(),"matched","unmatched")
print("Snap-share coverage:",int(last.avg_snap_share.notna().sum()),"/",len(last))

# Current roster reserve status and Week 7 game designations only.
# Do not carry forward last week's Out designations.
roster=pd.read_parquet(INPUTS/"roster.parquet")
roster=roster.sort_values("week").drop_duplicates("gsis_id",keep="last")
reports=pd.read_parquet(INPUTS/"injuries.parquet")
reports=reports[reports.week.eq(7)].copy()
assert len(reports)>=10, "Missing Week 7 injury reports"
# ID matching avoids suffix/name drift. Practice participation is not an Out.
reserve=roster[roster.status.isin(["RES","RSV","IR","PUP","NFI","CUT","RET"])]
excluded_ids=set(reserve.gsis_id)|set(reports.loc[reports.report_status.fillna("").str.lower().eq("out"),"gsis_id"])
inactive_players=tuple(reserve.full_name)+tuple(reports.loc[reports.report_status.fillna("").str.lower().eq("out"),"full_name"])
# Verified Week 7 Out designation missing from the preliminary feed.
# Oct 24 PHI: DeVonta Smith and Dontayvion Wicks confirmed Out.
# https://www.nbcsports.com/nfl/profootballtalk/rumor-mill/news/eagles-list-saquon-barkley-as-questionable-devonta-smith-dontayvion-wicks-ruled-out
# CBS injury listing: https://www.cbssports.com/nfl/injuries/
# Scoped to this forecast only; do not carry into future weeks automatically.
verified_out_ids={"00-0035719","00-0036912","00-0038393"}  # Deebo Samuel Sr., SF, hamstring
excluded_ids.update(verified_out_ids)
inactive_players+=tuple(w.loc[w.player_id.isin(verified_out_ids),"player_display_name"].unique())
last=last[~last.player_id.isin(excluded_ids)].copy()
# Only current active-team records may forecast; traded/cut players cannot
# remain under their old team's history.
roster_teams=roster.set_index("gsis_id").team
assert last.player_id.isin(roster_teams.index).all(), "Unmapped current roster"
last=last[last.recent_team.eq(last.player_id.map(roster_teams))].copy()
# Returning players without 2026 usage need documented historical inputs,
# not fabricated 2026 statistics or a replacement-level baseline.
profiles=json.loads((INPUTS/"returning_player_profiles.json").read_text())
returning_profiles={p["player_id"]:p for p in profiles}
for pid,profile in returning_profiles.items():
 assert not w.player_id.eq(pid).any(), "Returning historical profile has 2026 usage"
 assert profile["sample_games"]>=8 and pid not in excluded_ids
 template=last[(last.recent_team==profile["Team"])&last.position.eq(profile["Position"])].iloc[0].copy()
 template["player_id"]=pid;template["player_display_name"]=profile["Player"]
 template["recent_team"]=profile["Team"];template["position"]=profile["Position"]
 for c in cols:template["pre_"+c]=profile["per_game"][c]
 template["prior_opp"]=profile["per_game"]["carries"]+1.5*profile["per_game"]["targets"]
 template["Snap_Share_3W"]=np.nan;template["Snap_Games"]=np.nan
 template["Snap_Data_Status"]="historical_role"
 last=pd.concat([last,pd.DataFrame([template])],ignore_index=True)
# Latest meaningful-game starter, then verified Week 7 starter changes.
qhist=w[w.position.eq("QB")].sort_values(["week","attempts"],ascending=[False,False])
starters=qhist.drop_duplicates("recent_team").set_index("recent_team").player_display_name.to_dict()
starters.update({"NYG":"J.J. McCarthy","PHI":"Tanner McKee","SEA":"Sam Darnold"})
# BAL and TB remain conditional until the teams announce their starters.
last=last[last.position.ne("QB")|last.apply(lambda r:starters.get(r.recent_team)==r.player_display_name,axis=1)].copy()
last=last.sort_values("prior_opp",ascending=False)
# Structural v4 baseline, with player-specific observed usage.
pred=last.apply(project,axis=1)
last=pd.concat([last.reset_index(drop=True),pred.reset_index(drop=True)],axis=1)
# Reallocate receiving targets for EVERY scheduled team from observed usage.
# Team targets are counted from receiver targets, NOT QB attempts; the former
# excludes sacks, spikes, throwaways and other passes without a target.
# Shrink player shares toward the v4 baseline and use recent game exposure.
# Never redistribute unavailable players' targets to arbitrary fringe receivers.
recent=w[w.week.between(1,6)].copy()
recent_team_targets=recent.groupby(["recent_team","week"]).targets.sum().rename("team_targets").reset_index()
recent=recent.merge(recent_team_targets,on=["recent_team","week"],how="left",validate="many_to_one")
recent=recent[recent.team_targets.gt(0)].copy()
# Missing player-weeks are absent, never inserted as zero-target games.
# Only count an observed zero-target appearance when actual carries or
# offensive snaps establish participation.
recent["snap_name"]=recent.player_display_name.astype(str).str.lower().str.replace(r"[^a-z0-9]","",regex=True)
participation=snaps.groupby(["team","week","player"],as_index=False).offense_snaps.max()
participation["snap_name"]=participation.player.astype(str).str.lower().str.replace(r"[^a-z0-9]","",regex=True)
participation=participation.groupby(["team","week","snap_name"],as_index=False).offense_snaps.max()
recent=recent.merge(participation[["team","week","snap_name","offense_snaps"]],left_on=["recent_team","week","snap_name"],right_on=["team","week","snap_name"],how="left",validate="many_to_one")
recent=recent[(recent.targets.gt(0))|(recent.carries.gt(0))|(recent.offense_snaps.gt(0))].copy()
recent["weekly_share"]=recent.targets/recent.team_targets
assert recent.week.between(1,6).all(), "Target-share history includes an unexpected week"
assert recent.weekly_share.between(0,1).all(), "Invalid observed target share"
recent["recency_weight"]=recent.week.map({week:week+1 for week in range(1,7)})
# Team pass attempts set the forecast ceiling, with an empirically observed
# targeted-pass rate; avoid treating all pass attempts as actual targets.
team_pass_week=w[w.week.between(1,6)].groupby(["recent_team","week"]).attempts.sum().rename("attempts").reset_index()
team_rates=recent_team_targets.merge(team_pass_week,on=["recent_team","week"],how="inner")
team_rates=team_rates[team_rates.attempts.gt(0)].copy()
team_rates["rate"]=(team_rates.team_targets/team_rates.attempts).clip(0,1)
team_rates["weight"]=team_rates.week.map({week:week+1 for week in range(1,7)})
team_target_rate=team_rates.groupby("recent_team").apply(
 lambda g:np.average(g.rate,weights=g.weight),include_groups=False)
target_diagnostics=[]
for team in opponents:
 mask=(last.recent_team==team)&last.position.isin(["RB","WR","TE"])
 if not mask.any():continue
 qb=(last.recent_team==team)&last.position.eq("QB")
 pass_attempts=float(last.loc[qb,"pred_att"].max()) if qb.any() else float(last.loc[mask,"pre_team_pass"].median())
 if not np.isfinite(pass_attempts):continue
 rate=float(team_target_rate.get(team,np.nan))
 if not np.isfinite(rate):rate=0.90
 budget=max(0.,pass_attempts*rate)
 eligible=last.index[mask]
 base=last.loc[eligible,"pred_targets"].clip(lower=0).astype(float)
 # Player targets / team targets in their observed games; use all weeks
 # rather than dividing by the number of games the player happened to play.
 hist=recent[recent.recent_team==team]
 observed=hist.groupby("player_id").targets.sum()
 # Team targets must be deduplicated by player and week, so a player's
 # denominator is the sum of team targets for weeks they actually appeared.
 obs_share=hist.groupby("player_id").apply(lambda g: np.average(g.weekly_share,weights=g.recency_weight),include_groups=False).clip(0,1)
 hist_games=hist.groupby("player_id").week.nunique()
 for pid,profile in returning_profiles.items():
  if profile["Team"]==team:
   obs_share.loc[pid]=profile["target_share"]
   hist_games.loc[pid]=profile["sample_games"]
 # Reward target earners in proportion to their weighted Weeks 1-6 share.
 # Only observed player appearances enter each average; absences are not zeros.
 shares=pd.Series(0.,index=eligible,dtype=float)
 low=[]
 adjusted=set()
 high=[]
 unknown=[]
 for idx in eligible:
  pid=last.at[idx,"player_id"]
  empirical=float(obs_share.get(pid,np.nan))
  n=int(hist_games.get(pid,0))
  structural=float(base.at[idx])/max(float(base.sum()),1.)
  if n and np.isfinite(empirical):
   # Every measured role uses the same recency-weighted observed share.
   # A 12% target earner starts at 12%, with no threshold or depth cap.
   high.append(idx)
   shares.at[idx]=max(0.,empirical)
  else:
   unknown.append(idx)
   # New/returning players have no eligible observed share: keep a
   # conservative prior rather than misclassifying injury absences as 0%.
   shares.at[idx]=min(.04,structural*.50)
 # A returning lead back displaces the existing backup receiving allocation.
 # Preserve the current team RB target pool rather than inflating team volume.
 for pid,profile in returning_profiles.items():
  if profile["Team"]!=team:continue
  idx=last.index[(last.player_id==pid)&mask][0]
  backups=last.index[mask&last.position.eq("RB")&last.player_id.ne(pid)]
  pool=float(shares.loc[backups].sum())
  if pool>0:shares.loc[backups]*=max(0.,pool-float(shares.at[idx]))/pool
 # League-wide injury-replacement regression. Compare a role player's
 # target share with and without an established high-share teammate.
 # Never treat an absent player's missed game as a zero-target appearance.
 # Apply only if both samples exist, the starter is projected to return,
 # and the role player's elevated opportunity is actually measurable.
 active_ids=set(last.loc[eligible,"player_id"])
 established=[]
 for starter_id,starter_hist in hist.groupby("player_id"):
  if starter_id not in active_ids:continue
  if int(starter_hist.week.nunique())<2:continue
  starter_share=float(obs_share.get(starter_id,0.))
  if starter_share<.20:continue
  missed=set(hist.week.unique())-set(starter_hist.week)
  if missed:established.append((starter_id,missed))
 for idx in list(high):
  pid=last.at[idx,"player_id"]
  player_hist=hist[hist.player_id==pid]
  if player_hist.empty:continue
  observed_weeks=set(player_hist.week)
  healthy=[];replacement=[]
  for starter_id,missed in established:
   if starter_id==pid:continue
   overlap=observed_weeks & missed
   together=observed_weeks-missed
   if len(overlap)<1 or len(together)<1:continue
   replacement.extend(player_hist[player_hist.week.isin(overlap)].weekly_share.tolist())
   healthy.extend(player_hist[player_hist.week.isin(together)].weekly_share.tolist())
  if not replacement or not healthy:continue
  elevated=float(np.mean(replacement))
  normal=float(np.mean(healthy))
  if elevated<normal+.05:continue
  # Use the role with the starter present, but retain a modest
  # uncertainty allowance; never raise a player's share in this step.
  corrected=min(float(shares.at[idx]),float(obs_share.get(pid,0.)),normal+.25*(elevated-normal))
  shares.at[idx]=max(0.,corrected)
  high.remove(idx)
  if idx not in low:low.append(idx)
  adjusted.add(idx)
  print("RETURNING_STARTER_AUDIT",team,last.at[idx,"player_display_name"],
        "replacement_share",round(elevated,3),"healthy_share",round(normal,3),
        "corrected_share",round(corrected,3))
 # Preserve observed shares. Only scale DOWN if independently observed
 # player samples overlap enough that their shares exceed the team budget.
 # Never force unused opportunity onto the remaining healthy receivers.
 total_share=float(shares.sum())
 if total_share>1.:
  shares/=total_share
 assert shares.ge(0).all() and shares.sum()<=1.+1e-9
 for idx in eligible:
  empirical=float(obs_share.get(last.at[idx,"player_id"],np.nan))
  if np.isfinite(empirical):
   assert shares.at[idx]<=empirical+1e-9, "Observed target share inflated"
 for idx in eligible:
  target_diagnostics.append({"Player":last.at[idx,"player_display_name"],"Team":team,
   "Observed_Target_Share":float(obs_share.get(last.at[idx,"player_id"],np.nan)),
   "Projected_Target_Share":float(shares.at[idx]),"Team_Target_Budget":budget,
   "Projected_Targets":budget*float(shares.at[idx]),
   "Observed_Games":int(hist_games.get(last.at[idx,"player_id"],0)),
   "Input_Season":returning_profiles.get(last.at[idx,"player_id"],{}).get("input_season",2026)})
 for idx in eligible:
  old=float(last.at[idx,"pred_targets"])
  new=budget*float(shares.at[idx])
  if old>0:
   factor=new/old
   for field in ("pred_targets","pred_rec","pred_rec_yds","pred_rec_td"):
    last.at[idx,field]*=factor
  else:
   # No observed or structural receiving efficiency; do not invent it.
   last.at[idx,"pred_targets"]=0.
pd.DataFrame(target_diagnostics).to_csv("data/projections/2026_week7_target_allocation_audit.csv",index=False)
# Unallocated targets are allowed. Do not force the budget onto other players.

# Smooth QB rushing touchdowns using observed 2026 QB touchdown frequency.
qh=w[w.position=="QB"]
qr=float(qh.rushing_tds.sum())/max(float(qh.carries.sum()),1.)
for i in last.index[last.position=="QB"]:
 h=qh[qh.player_id==last.at[i,"player_id"]]
 n=float(h.carries.sum())
 rate=(float(h.rushing_tds.sum())+20*qr)/(n+20)
 last.at[i,"pred_rush_td"]=min(float(last.at[i,"pred_carries"])*rate,0.75)
# Reduce small-sample touchdown spikes for secondary backs.
rb=(last.position=="RB")&last.player_display_name.ne("Javonte Williams")&~last.player_id.isin(returning_profiles)
carries=last.loc[rb,"pred_carries"].clip(lower=0)
raw=last.loc[rb,"pred_rush_td"]/carries.clip(lower=1)
last.loc[rb,"pred_rush_td"]=carries*(.75*.025+.25*raw).clip(upper=.06)
# Receiving roles already follow observed production; retain the separate
# established rushing-workload constraints below.
for name,cap in {"Tyler Goodson":3.,"Hunter Luepke":1.}.items():
 m=last.player_display_name.eq(name)
 if m.any():
  factor=(cap/last.loc[m,"pred_carries"].clip(lower=.001)).clip(upper=1)
  for field in ["pred_carries","pred_rush_yds","pred_rush_td"]:last.loc[m,field]*=factor
# Allocate team volume from projected QB attempts and historical team rush volume.
for team in opponents:
 mask=(last.recent_team==team)&last.position.isin(["RB","WR","TE"])
 qb=(last.recent_team==team)&(last.position=="QB")
 attempts=float(last.loc[qb,"pred_att"].max()) if qb.any() else float(last.loc[mask,"pre_team_pass"].median())
 qb_rush=float(last.loc[qb,"pred_carries"].max()) if qb.any() else 0.
 history=last.loc[mask,"pre_team_carries"].dropna()
 rush_budget=max(0.,float(history.iloc[0])-qb_rush) if len(history) else float(last.loc[mask,"pred_carries"].sum())
 for volume,budget,fields in [
  ("pred_targets",float(last.loc[mask,"pred_targets"].sum()),["pred_targets","pred_rec","pred_rec_yds","pred_rec_td"]),
  ("pred_carries",rush_budget,["pred_carries","pred_rush_yds","pred_rush_td"])
 ]:
  total=float(last.loc[mask,volume].sum())
  if total>budget and total>0:
   factor=budget/total
   for field in fields:last.loc[mask,field]*=factor
  elif total<budget:
   eligible=mask&((last.pred_targets>=2.5) if volume=="pred_targets" else ((last.position=="RB")&(last.pred_carries>=5)))
   weight=float(last.loc[eligible,volume].sum())
   if weight>0:
    factor=1+(budget-total)/weight
    for field in fields:last.loc[eligible,field]*=factor
# Constrain projected team RB workload to historical team carries.
# Avoid allocating all missing quarterback carries to one running back.
for t in opponents:
 m=(last.recent_team==t)&last.position.eq("RB")
 if not m.any():continue
 hist=last.loc[m,"pre_team_carries"].dropna()
 if hist.empty:continue
 budget=float(hist.iloc[0])
 total=float(last.loc[m,"pred_carries"].sum())
 if total>budget and total>0:
  ratio=budget/total
  for f in ("pred_carries","pred_rush_yds","pred_rush_td"):
   last.loc[m,f]*=ratio
# Reallocate backfield carries using actual Weeks 4-6 RB carry shares.
# Apply AFTER team-volume normalization so lead-back usage is not erased.
for team in opponents:
 backs=(last.recent_team==team)&last.position.eq("RB")
 recent=w[(w.recent_team==team)&w.week.between(4,6)&w.position.eq("RB")]
 observed=recent.groupby("player_id").carries.sum()
 denom=float(observed.sum())
 total=float(last.loc[backs,"pred_carries"].sum())
 if denom<=0 or total<=0:continue
 returning=[(pid,p) for pid,p in returning_profiles.items() if p["Team"]==team]
 if returning:
  assert len(returning)==1, "Multiple returning lead backs require an explicit allocation"
  pid,profile=returning[0]
  lead_idx=last.index[backs&last.player_id.eq(pid)][0]
  lead_carries=min(profile["per_game"]["carries"],total)
  backups=last.index[backs&last.player_id.ne(pid)]
  backup_weights=last.loc[backups,"player_id"].map(observed).fillna(0).astype(float)
  assert backup_weights.sum()>0
  allocation={lead_idx:lead_carries,**{i:(total-lead_carries)*float(weight)/float(backup_weights.sum()) for i,weight in backup_weights.items()}}
  for idx,new in allocation.items():
   old=float(last.at[idx,"pred_carries"])
   assert old>0 or new==0, "Cannot infer unobserved rushing efficiency"
   if old>0:
    for field in ["pred_carries","pred_rush_yds","pred_rush_td"]:last.at[idx,field]*=new/old
  assert abs(float(last.loc[backs,"pred_carries"].sum())-total)<1e-6
  print("RETURNING_FULL_WORKLOAD",profile["Player"],"carries",lead_carries,"input_season",profile["input_season"],"games",profile["sample_games"])
  continue
 weights=last.loc[backs,"player_id"].map(observed).fillna(0).astype(float)
 if float(weights.sum())<=0:continue
 for idx,weight in weights.items():
  old=float(last.at[idx,"pred_carries"])
  new=total*float(weight)/float(weights.sum())
  if old>0:
   factor=new/old
   for field in ["pred_carries","pred_rush_yds","pred_rush_td"]:
    last.at[idx,field]*=factor
  else:
   last.at[idx,"pred_carries"]=new
   # Zero historical carries means efficiency is unknown; avoid inventing it.
# Bound implausible individual RB volume after team-share reallocation.
for idx in last.index[last.position.eq("RB")]:
 volume=float(last.at[idx,"pred_carries"])
 if volume>25:
  factor=25/volume
  for field in ("pred_carries","pred_rush_yds","pred_rush_td"):
   last.at[idx,field]*=factor
# Publication gate: ensure every team has a valid, conserved receiving budget.
for team in opponents:
 receiving=last[(last.recent_team==team)&last.position.isin(["RB","WR","TE"])]
 if receiving.empty:continue
 assert receiving.pred_targets.ge(0).all(), f"{team}: negative targets"
 assert receiving.pred_rec.le(receiving.pred_targets+1e-6).all(), f"{team}: receptions exceed targets"
 qb=last[(last.recent_team==team)&last.position.eq("QB")]
 if not qb.empty:
  cap=float(qb.pred_att.max())
  assert float(receiving.pred_targets.sum())<=cap+1e-5, f"{team}: targets exceed attempts"
 print("TARGET_AUDIT",team,"targets",round(float(receiving.pred_targets.sum()),2),
       "leaders",[(str(x.Player if "Player" in receiving else x.player_display_name),round(float(x.pred_targets),2))
                  for _,x in receiving.nlargest(5,"pred_targets").iterrows()])

# Matchup adjustment: 2026 Weeks 1-6 opponent defensive efficiency.
# nflverse schedule identifies the defense for each observed offensive game.
# Opponent strength affects efficiency and TD expectations, NOT earned targets.
schedule=schedule_all.copy()
needed={"season","week","home_team","away_team"}
if not needed.issubset(schedule.columns):
 raise RuntimeError(f"Schedule missing columns: {sorted(needed-set(schedule.columns))}")
schedule=schedule[(schedule.season==2026)&schedule.week.between(1,6)].copy()
home=schedule[["week","home_team","away_team"]].rename(columns={"home_team":"recent_team","away_team":"defense"})
away=schedule[["week","home_team","away_team"]].rename(columns={"away_team":"recent_team","home_team":"defense"})
matchups=pd.concat([home,away],ignore_index=True).drop_duplicates(["week","recent_team"])
if matchups.duplicated(["week","recent_team"]).any():raise RuntimeError("Duplicate schedule mapping")
def_hist=w.merge(matchups,on=["week","recent_team"],how="left",validate="many_to_one")
if def_hist.defense.isna().any():raise RuntimeError("Incomplete Weeks 1-6 opponent mapping")
def_hist["rec_opp"]=def_hist.targets.clip(lower=0)
def_hist["rush_opp"]=def_hist.carries.clip(lower=0)
def_hist["pass_opp"]=def_hist.attempts.clip(lower=0)
def_hist["rec_yds_allowed"]=def_hist.receiving_yards.clip(lower=0)
def_hist["rush_yds_allowed"]=def_hist.rushing_yards.clip(lower=0)
def_hist["pass_yds_allowed"]=def_hist.passing_yards.clip(lower=0)
# Aggregate by defense/week/position to prevent repeated team-game denominators.
def_week=def_hist.groupby(["defense","week","position"],as_index=False).agg(
 rec_opp=("rec_opp","sum"),rush_opp=("rush_opp","sum"),pass_opp=("pass_opp","sum"),
 rec_yds_allowed=("rec_yds_allowed","sum"),rush_yds_allowed=("rush_yds_allowed","sum"),
 pass_yds_allowed=("pass_yds_allowed","sum"))
def_week["weight"]=def_week.week.map({week:week+1 for week in range(1,7)})
# Weighted defensive allowed rates with a three-game league-average prior.
rates={}
for pos,opp_col,yd_col in [("QB","pass_opp","pass_yds_allowed"),
                           ("RB","rush_opp","rush_yds_allowed"),
                           ("WR","rec_opp","rec_yds_allowed"),
                           ("TE","rec_opp","rec_yds_allowed")]:
 p=def_week[def_week.position.eq(pos)].copy()
 total_opp=float(p[opp_col].sum())
 if total_opp<=0:raise RuntimeError(f"No defensive matchup sample for {pos}")
 league_rate=float(p[yd_col].sum())/total_opp
 league_games=max(int(p[["defense","week"]].drop_duplicates().shape[0]),1)
 prior_opp=3*total_opp/league_games
 for defense,g in p.groupby("defense"):
  observed=float((g[yd_col]*g.weight).sum())
  volume=float((g[opp_col]*g.weight).sum())
  effective_weight=float(g.weight.sum())
  prior=prior_opp*effective_weight
  rate=(observed+prior*league_rate)/max(volume+prior,1e-9)
  rates[(defense,pos)]=float(np.clip(rate/max(league_rate,1e-9),.5,1.5))
for idx in last.index:
 defense=opponents.get(last.at[idx,"recent_team"])
 pos=last.at[idx,"position"]
 ratio=rates.get((defense,pos),1.)
 # 15% opponent influence; bounded at +/-7.5% for this small sample.
 factor=float(np.clip(1+.15*(ratio-1),.925,1.075))
 if pos=="QB":fields=("pred_pass_yds","pred_pass_td")
 elif pos=="RB":fields=("pred_rush_yds","pred_rush_td")
 else:fields=("pred_rec_yds","pred_rec_td")
 for field in fields:last.at[idx,field]*=factor
 print("DEFENSE_AUDIT",last.at[idx,"player_display_name"],defense,pos,round(factor,4))
# Preserve the original structural QB model as the source of truth.
# Normalize individual receiving yards to that QB's projected passing yards,
# never overwrite QB attempts, yards, TDs, or interceptions.
# Target allocation remains tied to the QB's projected attempts and the
# historical credited-target rate, with no fabricated target recipients.
team_reconciliation=[]
for team in sorted(opponents):
 passers=last.index[(last.recent_team==team)&(last.position=="QB")]
 receivers=last.index[(last.recent_team==team)&last.position.isin(["RB","WR","TE"])]
 if len(passers)!=1 or len(receivers)==0:
  print("TEAM_RECONCILIATION_SKIP",team,"passers",len(passers),"receivers",len(receivers))
  continue
 qbidx=passers[0]
 qb_attempts=float(last.at[qbidx,"pred_att"])
 qb_yards=float(last.at[qbidx,"pred_pass_yds"])
 actual_targets=float(last.loc[receivers,"pred_targets"].sum())
 target_budget=qb_attempts*float(team_target_rate.get(team,.90))
 old_receiving_yards=float(last.loc[receivers,"pred_rec_yds"].sum())
 if old_receiving_yards>0:
  yard_factor=qb_yards/old_receiving_yards
  last.loc[receivers,"pred_rec_yds"]*=yard_factor
 else:
  assert qb_yards<=.01,(team,"No receiving yards to normalize",qb_yards)
  yard_factor=1.
 new_receiving_yards=float(last.loc[receivers,"pred_rec_yds"].sum())
 target_gap=target_budget-actual_targets
 team_reconciliation.append((team,qb_attempts,actual_targets,target_budget,target_gap,
                             qb_yards,old_receiving_yards,new_receiving_yards,yard_factor))
 assert actual_targets<=qb_attempts+.01,(team,actual_targets,qb_attempts)
 assert abs(new_receiving_yards-qb_yards)<.01,(team,new_receiving_yards,qb_yards)
 print("TEAM_PASS_RECONCILED",team,"QB_att",round(qb_attempts,2),
       "targets",round(actual_targets,2),"budget",round(target_budget,2),
       "unallocated",round(target_gap,2),"QB_pass_yds_unchanged",round(qb_yards,2),
       "receiver_yards_before",round(old_receiving_yards,2),
       "receiver_yards_after",round(new_receiving_yards,2),
       "receiving_yard_factor",round(yard_factor,3))
pd.DataFrame(team_reconciliation,columns=["Team","QB_Pass_Att","Projected_Targets",
 "Expected_Targets","Unallocated_Targets","QB_Pass_Yds","Previous_Receiver_Yds",
 "Normalized_Receiver_Yds","Receiving_Yard_Factor"]).round(3).to_csv(
 "data/projections/2026_week7_team_pass_reconciliation.csv",index=False)
last["Opponent"]=last.recent_team.map(opponents)
last["Total_xTD"]=last.pred_rush_td+last.pred_rec_td
last["PPR"]=last.apply(score,axis=1)
last["Half_PPR"]=last.PPR-.5*last.pred_rec
last["Standard"]=last.PPR-last.pred_rec
last["Pass_Att"]=last.pred_att;last["Pass_Yds"]=last.pred_pass_yds;last["Pass_TD"]=last.pred_pass_td
last["INT"]=last.pred_int;last["Rush_Att"]=last.pred_carries;last["Rush_Yds"]=last.pred_rush_yds
last["Rush_TD"]=last.pred_rush_td;last["Targets"]=last.pred_targets;last["Receptions"]=last.pred_rec
last["Rec_Yds"]=last.pred_rec_yds;last["Rec_TD"]=last.pred_rec_td
last=last[(last.position=="QB")|(last.prior_opp>=1)].copy()
last=last.rename(columns={"player_display_name":"Player","recent_team":"Team","position":"Position"})
out=last[["Player","Team","Opponent","Position","Rush_TD","Rec_TD","Total_xTD"]].sort_values("Total_xTD",ascending=False).round(3)
Path("data/projections").mkdir(parents=True,exist_ok=True)
out.to_csv("data/projections/2026_week7_league_v4_touchdowns.csv",index=False)
full=last[["Player","Team","Opponent","Position","Pass_Att","Pass_Yds","Pass_TD","INT","Rush_Att","Rush_Yds","Rush_TD","Targets","Receptions","Rec_Yds","Rec_TD","Total_xTD","Standard","Half_PPR","PPR","Snap_Share_3W","Snap_Games","Snap_Data_Status"]].copy()
full=full.sort_values(["Position","PPR"],ascending=[True,False]).round(2)
full.to_csv("data/projections/2026_week7_league_v4_full.csv",index=False)
assert len(full)>=150, f"Unusually low Week 7 coverage: {len(full)}"
assert not full.PPR.isna().any(), "Missing projected points"
assert not full.Player.isin(inactive_players).any(), "Unavailable player survived injury filter"
assert not full.Player.isin(["Demarcus Robinson","Tank Bigsby","Travis Etienne","Xavier Legette"]).any(), "Known IR player survived"
assert set(full.Team)==set(opponents), "Missing scheduled team"
assert full[full.Position.eq("QB")].Team.nunique()==28, "Missing starting QB"
assert full.Player.nunique()==len(full), "Duplicate player"
print("Full projections:",len(full),"players")
print(out.head(30).to_string(index=False))
