"""Validate and export the Week 8 v4 forecast, preserving input provenance."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, html, subprocess, sys
import pandas as pd
p=Path('data/projections'); inputs=p/'inputs/week8'
d=pd.read_csv(p/'2026_week8_league_v4_full.csv')
gameday=json.loads((inputs/'gameday_availability.json').read_text())
i=pd.read_parquet(inputs/'injuries.parquet');i=i[i.week.eq(8)].drop_duplicates('gsis_id',keep='last')
roster=pd.read_parquet(inputs/'roster.parquet').sort_values('week').drop_duplicates('gsis_id',keep='last')
reports=i.set_index('full_name')
profiles=json.loads((inputs/'returning_player_profiles.json').read_text())
returners={r['Player']:r for r in profiles}
def note(n):
 if n=='Lamar Jackson':return 'Conditional on playing: full practice October 28 after three missed games; final game status pending.'
 if n in returners:return 'Returning-role assumption based on the recorded Week 7 appearance with at least 50% offensive snaps; one-game sample, workload uncertain; final availability pending.'
 if n not in reports.index:return 'No Week 8 injury designation in the downloaded report; final game-day availability pending.'
 r=reports.loc[n];status=r.report_status if pd.notna(r.report_status) else 'Final game status pending'
 return f'{status}; {r.practice_status}; {r.practice_primary_injury}'
d['Availability_Note']=d.Player.map(note)
d['QB_Starter_Assumption']=d.Team.map(gameday['conditional_starters']).fillna('')
checks=[]
games=pd.read_csv(inputs/'games.csv');games=games[games.season.eq(2026)&games.week.eq(8)]
assert len(games)==14
teams=set(games.away_team)|set(games.home_team)
assert set(d.Team)==teams and d.Player.nunique()==len(d)
reserved=set(roster.loc[roster.status.isin(['RES','RSV','IR','PUP','NFI','CUT','RET']),'full_name'])
outs=set(i.loc[i.report_status.fillna('').str.lower().eq('out'),'full_name'])
assert not set(d.Player)&(reserved|outs)
assert (d.Receptions<=d.Targets+.01).all()
for team,g in d.groupby('Team'):
 q=g[g.Position.eq('QB')];assert len(q)==1,team
 q=q.iloc[0];r=g[g.Position.ne('QB')]
 assert r.Targets.sum()<=q.Pass_Att+.2,(team,'targets')
 assert abs(r.Rec_Yds.sum()-q.Pass_Yds)<.2,(team,'yards')
 checks.append({'Team':team,'Targets':r.Targets.sum(),'QB_Att':q.Pass_Att,'Receiver_Yards':r.Rec_Yds.sum(),'QB_Yards':q.Pass_Yds})
for pos in ['QB','RB','WR','TE']:
 assert d.Position.eq(pos).any()
 d[d.Position.eq(pos)].to_csv(p/f'2026_week8_{pos.lower()}_substack.csv',index=False)
d.to_csv(p/'2026_week8_league_v4_full.csv',index=False)
pd.DataFrame(checks).round(2).to_csv(p/'2026_week8_publication_checks.csv',index=False)
flags=d[d.Snap_Data_Status.eq('unmatched')].copy();flags['Review_Reason']='No matched Week 5-7 snap record; may reflect missed games or source naming differences.'
flags.to_csv(p/'2026_week8_review_flags.csv',index=False)
a=pd.read_csv(p/'2026_week8_target_allocation_audit.csv');a=a[a.Observed_Target_Share.notna()]
assert (a.Projected_Target_Share<=a.Observed_Target_Share+1e-9).all()
base='https://github.com/nflverse/nflverse-data/releases/download/'
sources={'player_stats.parquet':base+'stats_player/stats_player_week_2026.parquet','snaps.parquet':base+'snap_counts/snap_counts_2026.parquet','roster.parquet':base+'rosters/roster_2026.parquet','injuries.parquet':base+'injuries/injuries_2026.parquet','games.csv':base+'schedules/games.csv'}
meta={'as_of':datetime.now(timezone.utc).isoformat(),'forecast_week':8,'input_weeks':[1,7],'snap_weeks':[5,7],
 'model_base':'Established structural v4 model, advanced from Week 7 with fresh frozen inputs; target-share, volume, touchdown and matchup formulas retained.',
 'returning_player_profiles':profiles,
 'counts':{k:int(v) for k,v in d.Position.value_counts().items()},'conditional_starters':gameday['conditional_starters'],
 'sources':sources,'availability_sources':gameday['sources'],
 'sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs.iterdir()},
 'model_sha256':hashlib.sha256(Path('scripts/projection_week8_league_v4.py').read_bytes()).hexdigest(),
 'update_note':'Week 8 initial run using 2026 Weeks 1-7 statistics and Weeks 5-7 snaps. Current roster reserve statuses and Week 8 reports checked. Lamar Jackson assumed to start, conditional on playing. Final weekend injury designations and game-day inactives pending.',
 'validation':'28 unique starting QBs; all 28 scheduled teams; no duplicate or current reserve/Out players; team targets <= QB attempts; receiving yards match QB yards within rounding; observed target shares never inflated.',
 'review':'Preliminary Thursday forecast. Practice absence alone is not an Out designation. Unmatched recent snap records retained in review_flags; no missing player forecasts invented. Prior-week gameday exclusions and workload overrides not inherited. Jacobs and Mason use their observed Week 7 return roles to avoid retaining injury-fill-in backfield allocations.'}
(p/'2026_week8_run_manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
subprocess.run([sys.executable,'scripts/publish-weekly-projections.py'],check=True)
print('Validated',len(d),'players;',len(flags),'recent-snap records flagged for review.')
