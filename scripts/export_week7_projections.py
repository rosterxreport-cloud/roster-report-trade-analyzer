"""Export and verify the Week 7 model run without changing projections."""
from pathlib import Path
import json, html
import pandas as pd
p=Path('data/projections')
d=pd.read_csv(p/'2026_week7_league_v4_full.csv')
gameday=json.loads((p/'inputs/week7/gameday_availability.json').read_text())
profiles={x['Player']:x for x in json.loads((p/'inputs/week7/returning_player_profiles.json').read_text())}
i=pd.read_parquet(p/'inputs/week7/injuries.parquet'); i=i[i.week.eq(7)].set_index('full_name')
def note(n):
 if n=='Saquon Barkley':return 'Questionable (hamstring); expected to play Monday. Conditional healthy-role projection using 2026 Weeks 1 and 3 (50%+ offensive snaps); injury-exit/limited appearances excluded from role inputs.'
 if n=='Josh Jacobs':return 'Activated; full lead-back workload assumed at user request. Historical inputs: 12 games in 2025 with at least 50% offensive snaps; no 2026 game sample.'
 if n=='Tyler Huntley':return 'Confirmed starter; Lamar Jackson inactive (ankle).'
 if n=='Baker Mayfield':return 'Confirmed starter; returning after thumb injury.'
 if n in profiles:return 'Activated; returning-role assumption from '+str(profiles[n]['sample_games'])+' recorded 2026 appearances. Small-sample workload uncertainty.'
 if n=='Puka Nacua':return 'Questionable (calf); projection conditional on playing. Late-game inactive decision pending.'
 if n=='Adonai Mitchell':return 'Active; returning from finger injury.'
 if n not in i.index:return 'No current injury report designation'
 r=i.loc[n];return str(r.practice_status)+'; '+str(r.practice_primary_injury)
d['Availability_Note']=d.Player.map(note)
d['QB_Starter_Assumption']=d.Team.map({'BAL':'Tyler Huntley confirmed starter','TB':'Baker Mayfield confirmed starter'}).fillna('')
d.to_csv(p/'2026_week7_league_v4_full.csv',index=False)
for pos in ['QB','RB','WR','TE']:d[d.Position.eq(pos)].to_csv(p/f'2026_week7_{pos.lower()}_substack.csv',index=False)
checks=[]
for t,g in d.groupby('Team'):
 q=g[g.Position.eq('QB')].iloc[0];r=g[g.Position.ne('QB')]
 assert r.Targets.sum()<=q.Pass_Att+.2,(t,'targets')
 assert abs(r.Rec_Yds.sum()-q.Pass_Yds)<.2,(t,'yards')
 checks.append({'Team':t,'Targets':r.Targets.sum(),'QB_Att':q.Pass_Att,'Receiver_Yards':r.Rec_Yds.sum(),'QB_Yards':q.Pass_Yds})
assert not d.Player.isin(['Deebo Samuel Sr.','DeVonta Smith','Dontayvion Wicks']).any()
assert d.Player.eq('Josh Jacobs').sum()==1
assert d.Player.nunique()==len(d) and len(d)>=150
assert not d.Player.isin(gameday['out'].values()).any()
assert d[d.Position.eq('QB')].Team.nunique()==28
assert (d.Receptions<=d.Targets+.01).all()
a=pd.read_csv(p/'2026_week7_target_allocation_audit.csv')
observed=a[a.Observed_Target_Share.notna()]
assert (observed.Projected_Target_Share<=observed.Observed_Target_Share+1e-9).all()
# Below-threshold roles are preserved unless the documented returning-starter
# adjustment or team-wide downward reconciliation applies.
pd.DataFrame(checks).round(2).to_csv(p/'2026_week7_publication_checks.csv',index=False)
flags=d[d.Snap_Data_Status.eq('unmatched')].copy();flags['Review_Reason']='Unmatched recent snap record'
flags.to_csv(p/'2026_week7_review_flags.csv',index=False)
m=json.loads((p/'2026_week7_run_manifest.json').read_text())
from datetime import datetime, timezone
m.setdefault('baseline_as_of',m['as_of'])
m['as_of']=datetime.now(timezone.utc).isoformat()
m['update_note']='October 25 pregame injury refresh: confirmed inactives excluded; Mayfield and Huntley confirmed starters; Mason and Coleman restored using recorded 2026 roles. Jacobs full-workload and Barkley conditional healthy-role assumptions retained. Puka remains conditional. Kirk, Dell and Sampson are activated but have no usable 2026 offensive sample, so no numeric forecast is invented. Thursday and Paris-game forecasts preserved for audit.'
m['conditional_starters']={}
m['confirmed_starters']=gameday['starters']
m['gameday_sources']=gameday['sources']
m['active_without_usable_2026_sample']=['Christian Kirk','Tank Dell','Dylan Sampson']
import hashlib
m['sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (p/'inputs/week7').iterdir()}
m['returning_player_profiles']=json.loads((p/'inputs/week7/returning_player_profiles.json').read_text())
m['counts']=d.Position.value_counts().to_dict()
m['verified_out_overrides']={pid:name+' — confirmed Week 7 Out/inactive; October 25 availability check' for pid,name in gameday['out'].items()}
m['target_allocation']='Recency-weighted observed target shares for all measured players. No 12% threshold, no 2% receiving share cap, no upward redistribution. Downward team reconciliation and returning-starter adjustment retained.'
m['review']='Later-game inactive decisions remain pending, including Puka Nacua and Monday Saquon Barkley. Kirk, Dell and Sampson lack usable 2026 offensive inputs; no numeric forecasts fabricated. Returning RB samples are small. Unmatched snap records listed separately.'
(p/'2026_week7_run_manifest.json').write_text(json.dumps(m,indent=2))
out=['<!doctype html><html><head><meta charset="utf-8"><title>Week 7 Projections</title><style>body{font:16px/1.6 Arial;max-width:850px;margin:40px auto;padding:0 20px;color:#17233d}h1,h2{color:#183c78}h2{border-bottom:3px solid #edc53b;padding-top:25px}article{border-bottom:1px solid #ddd;padding:12px 0}strong{color:#183c78}</style></head><body><h1>The Roster Report: Week 7 Projections</h1><p>Updated with Weeks 1–6 of 2026. Full PPR for RB/WR/TE; 4-point passing touchdowns for QBs.</p><p>Receiving targets follow observed production at every target-share level. Unallocated targets are allowed.</p><p><strong>Starter assumptions:</strong> Tyler Huntley for Baltimore and Baker Mayfield for Tampa Bay confirmed starters. Confirmed inactives excluded. Mason and Coleman use their recorded 2026 roles. Kirk, Dell and Sampson are activated but lack usable 2026 offensive inputs and have no numeric forecast. Puka Nacua remains conditional pending late-game status. Jacobs uses a full-workload assumption and a 12-game 2025 lead-role sample. Barkley uses his healthy 2026 Weeks 1 and 3 role, conditional on playing Monday (officially questionable). DeVonta Smith and Dontayvion Wicks are excluded.</p>']
for pos in ['QB','RB','WR','TE']:
 out.append(f'<h2>{pos}</h2>')
 for rank,(_,r) in enumerate(d[d.Position.eq(pos)].iterrows(),1):
  line=(f'{r.Pass_Att:.2f} attempts, {r.Pass_Yds:.2f} passing yards, {r.Pass_TD:.2f} passing TD, {r.INT:.2f} INT; ' if pos=='QB' else '')
  line+=f'{r.Rush_Att:.2f} carries, {r.Rush_Yds:.2f} rushing yards, {r.Rush_TD:.2f} rushing TD'
  if pos!='QB':line+=f'; {r.Targets:.2f} targets, {r.Receptions:.2f} receptions, {r.Rec_Yds:.2f} receiving yards, {r.Rec_TD:.2f} receiving TD'
  out.append(f'<article><strong>{rank}. {html.escape(r.Player)} ({r.Team} vs. {r.Opponent}) — {r.PPR:.2f} PPR</strong><br>{line}<br>Standard: {r.Standard:.2f} | Half PPR: {r.Half_PPR:.2f} | PPR: {r.PPR:.2f}<br><small>{html.escape(r.Availability_Note)}</small></article>')
out.append('</body></html>');(p/'2026_week7_full_statlines.html').write_text(''.join(out))
print(f'Validated {len(d)} players, 28 teams; confirmed inactives excluded and receiving totals reconciled.')

# Keep the website snapshot synchronized with this verified master export.
import subprocess, sys
subprocess.run([sys.executable, str(Path(__file__).with_name('publish-weekly-projections.py'))], check=True)
