#!/usr/bin/env python3
"""Build a checked, replayable statistical snapshot; never run or alter a model."""
import argparse, datetime as dt, hashlib, io, json, math, re, unicodedata
from pathlib import Path
from urllib.request import Request, urlopen
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
URLS={
 'player_stats.parquet':'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.parquet',
 'snaps.parquet':'https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{season}.parquet',
 'roster.parquet':'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{season}.parquet'}
CORE={'QB','RB','WR','TE'}
TOTALS=['attempts','completions','passing_yards','passing_tds','passing_interceptions','passing_epa','carries','rushing_yards','rushing_tds','rushing_epa','targets','receptions','receiving_yards','receiving_tds','receiving_epa','receiving_air_yards','fantasy_points','fantasy_points_ppr']
def key(value):
 s=unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode().lower()
 return re.sub('[^a-z0-9]','',re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',s))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clean(v):
 if pd.isna(v):return None
 return round(float(v),6)
def build(input_dir=None,manifest=None,through_week=None,season=2026):
 players=json.loads((ROOT/'players.json').read_text()); injuries=json.loads((ROOT/'injury-adjustments.json').read_text())
 if through_week is None:
  # Select a fully completed scheduled week, never a partially played new week.
  games_url='https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv'
  games=pd.read_csv(games_url)
  games=games[(games.season==season)&(games.game_type=='REG')]
  completed=[int(w) for w,g in games.groupby('week') if g.home_score.notna().all() and g.away_score.notna().all()]
  if not completed:raise ValueError('No completed schedule week')
  through_week=max(completed)
 if not 1<=through_week<=18:raise ValueError('Invalid completed week')
 stamp=(manifest.get('baseline_as_of') or manifest['as_of']) if manifest else dt.datetime.now(dt.timezone.utc).isoformat()
 frames={};sources=[]
 for name,url in URLS.items():
  url=url.format(season=season)
  if input_dir:
   p=input_dir/name;raw=p.read_bytes()
   if not manifest or hashlib.sha256(raw).hexdigest()!=manifest['sha256'][name]:raise ValueError(f'Input checksum mismatch: {name}')
  else:
   with urlopen(Request(url,headers={'User-Agent':'RosterReportPlayerProfiles/1.0'}),timeout=60) as response:raw=response.read()
  frames[name]=pd.read_parquet(io.BytesIO(raw))
  sources.append({'file':name,'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'capturedAt':stamp})
 stats=frames['player_stats.parquet'];snaps=frames['snaps.parquet'];roster=frames['roster.parquet']
 required={'player_id','player_display_name','position','season','week','season_type',*TOTALS}
 if not required<=set(stats):raise ValueError('Missing statistical source columns')
 stats=stats[(stats.season==season)&(stats.season_type=='REG')&(stats.week<=through_week)].copy()
 if set(map(int,stats.week.unique()))!=set(range(1,through_week+1)):raise ValueError('Incomplete weekly source coverage')
 team_attempts=stats.groupby(['team','week']).attempts.sum().to_dict()
 if stats.duplicated(['player_id','week']).any():raise ValueError('Duplicate weekly player records')
 snaps=snaps[(snaps.season==season)&(snaps.game_type=='REG')&(snaps.week<=through_week)].copy()
 if snaps.duplicated(['pfr_player_id','week']).any():raise ValueError('Duplicate snap records')
 roster=roster[(roster.season==season)&roster.position.isin(CORE)].copy()
 identities={}
 for _,r in roster.iterrows():
  nk=key(r.full_name);pid=str(r.gsis_id)
  if nk in identities and identities[nk]['id']!=pid:raise ValueError('Ambiguous roster identity: '+r.full_name)
  identities[nk]={'id':pid,'pfr':r.pfr_id,'position':r.position}
 for _,r in stats[stats.position.isin(CORE)].iterrows():
  nk=key(r.player_display_name)
  if nk not in identities:identities[nk]={'id':str(r.player_id),'pfr':None,'position':r.position}
 result={}
 for p in players['half']:
  if p['pos'] not in CORE:continue
  identity=identities.get(key(p['name']))
  if not identity or identity['position']!=p['pos']:raise ValueError('Unresolved player identity: '+p['name'])
  pid=identity['id'];rows=stats[stats.player_id==pid].sort_values('week');sr=snaps[snaps.pfr_player_id==identity['pfr']]
  weekly=[]
  for _,r in rows.iterrows():
   # A row with only defensive/special-team stats is not an offensive appearance.
   snap=sr[sr.week==r.week]
   if not (r.attempts+r.carries+r.targets>0 or (not snap.empty and float(snap.iloc[0].offense_snaps)>0)):continue
   w={'week':int(r.week),'teamPassAttempts':clean(team_attempts.get((r.team,r.week))),**{c:clean(r[c]) for c in TOTALS}}
   if not snap.empty:w.update(snapShare=clean(snap.iloc[0].offense_pct),offenseSnaps=clean(snap.iloc[0].offense_snaps))
   weekly.append(w)
  # Include observed offensive snaps even when the player registered no counting stats.
  for _,r in sr.iterrows():
   if float(r.offense_snaps)>0 and int(r.week) not in {w['week'] for w in weekly}:
    weekly.append({'week':int(r.week),'statsMissing':True,'snapShare':clean(r.offense_pct),'offenseSnaps':clean(r.offense_snaps)})
  weekly.sort(key=lambda w:w['week'])
  if any(w.get('snapShare') is not None and not 0<=w['snapShare']<=1 for w in weekly):raise ValueError('Invalid snap share')
  for w in weekly:
   if w.get('statsMissing'):continue
   if any(w[c] is None for c in ['attempts','completions','carries','targets','receptions','passing_yards','rushing_yards','receiving_yards','fantasy_points','fantasy_points_ppr']):raise ValueError('Missing required counting statistic')
   if w['receptions']>w['targets'] or w['completions']>w['attempts']:raise ValueError('Impossible statline')
  result[pid]={'id':pid,'name':p['name'],'position':p['pos'],'weekly':weekly}
 return {'schemaVersion':1,'season':season,'throughWeek':through_week,'capturedAt':stamp,'sources':sources,'players':result}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--input-dir',type=Path);ap.add_argument('--manifest',type=Path);ap.add_argument('--through-week',type=int);ap.add_argument('--output',type=Path,default=ROOT/'data/player-evidence.json');a=ap.parse_args()
 d=build(a.input_dir,json.loads(a.manifest.read_text()) if a.manifest else None,a.through_week)
 a.output.parent.mkdir(parents=True,exist_ok=True);temp=a.output.with_suffix('.tmp');temp.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n');temp.replace(a.output)
 print(f"Verified evidence for {len(d['players'])} players through Week {d['throughWeek']}")
if __name__=='__main__':main()
