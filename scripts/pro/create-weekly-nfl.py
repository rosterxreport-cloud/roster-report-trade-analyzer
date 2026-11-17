"""Calendar/input orchestration for the established weekly v4 model; no fitting."""
import argparse,datetime,hashlib,json,pathlib,shutil,subprocess,sys,tempfile,urllib.request
from zoneinfo import ZoneInfo
ROOT=pathlib.Path(__file__).resolve().parents[2]
TEMPLATE_HASH='c95ac28e53c2c9550827391269dcaff95127ee8397730b33072bc81d00441d6d'
BASE='https://github.com/nflverse/nflverse-data/releases/download/'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def bind_calendar(source,season,week,games):
 if hashlib.sha256(source.encode()).hexdigest()!=TEMPLATE_HASH:raise ValueError('Established model template changed; review required')
 if not 2<=week<=18 or not 10<=games<=16:raise ValueError('Unsupported regular-season schedule')
 # Only calendar windows, file identities and schedule-coverage assertions change.
 replacements={
 'week10':f'week{week}','2026_week':f'{season}_week',
 'w.week.between(1,9)':f'w.week.between(1,{week-1})',
 'recent.week.between(1,9)':f'recent.week.between(1,{week-1})',
 'schedule.week.between(1,9)':f'schedule.week.between(1,{week-1})',
 'snaps.week.between(7,9)':f'snaps.week.between({max(1,week-3)},{week-1})',
 'w.week.between(7,9)':f'w.week.between({max(1,week-3)},{week-1})',
 'range(1,10)':f'range(1,{week})',
 'last["week"]=10':f'last["week"]={week}',
 'schedule_all.week.eq(10)':f'schedule_all.week.eq({week})',
 'reports.week.eq(10)':f'reports.week.eq({week})',
 'assert len(week_games)==14':f'assert len(week_games)=={games}',
 'Team.nunique()==28':f'Team.nunique()=={2*games}',
 'max()>=9':f'max()>={week-1}',
 'season.eq(2026)':f'season.eq({season})',
 'season==2026':f'season=={season}',
 'profile["input_season"]==2026':f'profile["input_season"]=={season}',
 }
 for old,new in replacements.items():source=source.replace(old,new)
 return source
def download(url,path):
 with urllib.request.urlopen(url,timeout=90) as r:raw=r.read()
 if not raw:raise ValueError('Empty source download')
 path.write_bytes(raw)
def create(output,season=None,week=None,now=None):
 import pandas as pd
 now=now or datetime.datetime.now(datetime.timezone.utc)
 output=pathlib.Path(output);output.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='rr-weekly-') as tmp:
  work=pathlib.Path(tmp);(work/'scripts').mkdir();(work/'data/projections').mkdir(parents=True)
  schedule=work/'games.csv';download(BASE+'schedules/games.csv',schedule)
  games=pd.read_csv(schedule);games=games[games.game_type.eq('REG')]
  if season is None:
   eastern=now.astimezone(ZoneInfo('America/New_York'))
   season=eastern.year if eastern.month>=7 else eastern.year-1
  season_games=games[games.season.eq(season)].copy()
  dates=pd.to_datetime(season_games.gameday)
  if week is None:
   starts=pd.to_datetime(season_games.gameday+' '+season_games.gametime).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
   first_starts=season_games.assign(start=starts).groupby('week').start.min()
   upcoming=first_starts[first_starts>pd.Timestamp(now)]
   if upcoming.empty:raise ValueError('No unstarted regular-season week')
   week=int(upcoming.index.min())
  prior=season_games[season_games.week.eq(week-1)]
  if prior.empty or prior[['home_score','away_score']].isna().any().any():raise ValueError('Previous NFL week is not final; retain prior release')
  selected=season_games[season_games.week.eq(week)]
  teams=list(selected.away_team)+list(selected.home_team)
  if len(set(teams))!=len(teams):raise ValueError('Duplicate scheduled team')
  # Tuesday creation only; never regenerate already-started games with later observations.
  first=pd.to_datetime(selected.gameday+' '+selected.gametime).dt.tz_localize('America/New_York').dt.tz_convert('UTC').min()
  if first<=pd.Timestamp(now):raise ValueError('Forecast week has already started')
  inputs=work/f'data/projections/inputs/week{week}';inputs.mkdir(parents=True)
  shutil.copyfile(schedule,inputs/'games.csv')
  sources={'games.csv':BASE+'schedules/games.csv'}
  for name,part in {'player_stats.parquet':f'stats_player/stats_player_week_{season}.parquet','snaps.parquet':f'snap_counts/snap_counts_{season}.parquet','roster.parquet':f'rosters/roster_{season}.parquet','injuries.parquet':f'injuries/injuries_{season}.parquet'}.items():
   sources[name]=BASE+part;download(sources[name],inputs/name)
  stats=pd.read_parquet(inputs/'player_stats.parquet')
  snaps=pd.read_parquet(inputs/'snaps.parquet')
  if stats.loc[stats.season_type.eq('REG'),'week'].max()<week-1 or snaps.week.max()<week-1:raise ValueError('Prior week stats/snaps are incomplete')
  # Fresh Tuesday run: never inherit last week's game-day overrides or bespoke roles.
  (inputs/'gameday_availability.json').write_text(json.dumps({'active':{},'out':{},'starters':{}}))
  (inputs/'returning_player_profiles.json').write_text('[]')
  template=(ROOT/'scripts/projection_week10_league_v4.py').read_text()
  source=bind_calendar(template,season,week,len(selected))
  for name in ['projection_v4_backtest.py','publish-weekly-projections.py']:
   shutil.copyfile(ROOT/'scripts'/name,work/'scripts'/name)
  runner=work/'scripts/current-week.py';runner.write_text(source)
  result=subprocess.run([sys.executable,str(runner)],cwd=work,capture_output=True,text=True,timeout=300)
  if result.returncode:
   (output/'failed-model-run.log').write_text(result.stdout+result.stderr)
   raise RuntimeError('Established weekly model failed; no release written')
  master=work/f'data/projections/{season}_week{week}_league_v4_full.csv'
  rows=pd.read_csv(master)
  if set(rows.Team)!=set(teams) or rows.Player.duplicated().any():raise ValueError('Incomplete or ambiguous forecast pool')
  for team,group in rows.groupby('Team'):
   qb=group[group.Position.eq('QB')];receivers=group[~group.Position.eq('QB')]
   if len(qb)!=1 or receivers.Targets.sum()>qb.Pass_Att.iloc[0]+.2 or abs(receivers.Rec_Yds.sum()-qb.Pass_Yds.iloc[0])>.2:raise ValueError('Team-volume validation failed')
  manifest={'as_of':now.isoformat(),'forecast_week':week,'input_weeks':[1,week-1],'snap_weeks':[max(1,week-3),week-1],'counts':{k:int(v) for k,v in rows.Position.value_counts().items()},'model_base':'Established structural v4 model; original Week 10 template with calendar-only bindings. No model fitting or recalibration.','model_sha256':digest(pathlib.Path(__file__)),'generator_path':'scripts/pro/create-weekly-nfl.py','template_sha256':TEMPLATE_HASH,'bound_script_sha256':digest(runner),'sources':sources,'sha256':{p.name:digest(p) for p in inputs.iterdir()},'conditional_starters':{},'update_note':'Tuesday preliminary forecast using completed prior-week stats and current roster/injury data. No previous-week game-day overrides inherited; final availability remains subject to updates.'}
  manifest_path=work/f'data/projections/{season}_week{week}_run_manifest.json';manifest_path.write_text(json.dumps(manifest,indent=2))
  subprocess.run([sys.executable,'scripts/publish-weekly-projections.py'],cwd=work,check=True,capture_output=True)
  for path in (work/'data/projections').glob('*.csv'):shutil.copyfile(path,output/path.name)
  shutil.copyfile(manifest_path,output/manifest_path.name)
  shutil.copyfile(work/'data/weekly-projections.json',output/'weekly-projections.json')
  return {'season':season,'week':week,'players':len(rows),'templateHash':TEMPLATE_HASH,'output':str(output)}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--season',type=int);p.add_argument('--week',type=int);a=p.parse_args()
 print(json.dumps(create(a.output,a.season,a.week)))
