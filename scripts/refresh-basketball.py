#!/usr/bin/env python3
"""Publish numeric ESPN projected-stat inputs. Never reads or writes football data."""
import argparse, datetime as dt, hashlib, json, math, pathlib, urllib.request
ROOT = pathlib.Path(__file__).resolve().parents[1]
FIELDS = {'PTS':'0','BLK':'1','STL':'2','AST':'3','REB':'6','TOV':'11','FGM':'13','FGA':'14','FTM':'15','FTA':'16','FG3M':'17'}
POSITIONS = {0:'PG',1:'SG',2:'SF',3:'PF',4:'C'}
TEAM_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams'
def fetch(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=60) as r: return r.read()
def build(raw, teams, season, captured):
    rows=[];excluded=[];seen=set()
    for p in raw:
        if not p.get('active') or p.get('proTeamId') not in teams: continue
        projected=[s for s in p.get('stats',[]) if s.get('seasonId')==season and s.get('statSourceId')==1 and s.get('statSplitTypeId')==0 and s.get('scoringPeriodId')==0]
        if len(projected)!=1: excluded.append({'id':p['id'],'name':p['fullName'],'reason':'No unique full-season projection'});continue
        stats=projected[0]['stats']; gp=stats.get('42'); name=p['fullName']
        if not isinstance(gp,(float,int)) or not 0<gp<=82: excluded.append({'id':p['id'],'name':name,'reason':'No positive projected games'});continue
        values={k:stats.get(v) for k,v in FIELDS.items()}
        if any(v is None for v in values.values()):
            excluded.append({'id':p['id'],'name':name,'reason':'Incomplete projected statline'});continue
        if any(not isinstance(v,(float,int)) or not math.isfinite(v) or v<0 for v in values.values()): raise ValueError('Invalid projected statistic: '+name)
        if values['FGM']>values['FGA'] or values['FTM']>values['FTA'] or values['FG3M']>values['FGM']: raise ValueError('Impossible shooting totals: '+name)
        if abs(values['PTS']-(2*values['FGM']+values['FG3M']+values['FTM']))>3: raise ValueError('Inconsistent projected points: '+name)
        positions=[v for k,v in POSITIONS.items() if k in p.get('eligibleSlots',[])]
        if not positions: raise ValueError('Missing position: '+name)
        if p['id'] in seen: raise ValueError('Duplicate player ID')
        seen.add(p['id']); rows.append({'id':str(p['id']),'name':name,'team':teams[p['proTeamId']],'positions':positions,'injuryStatus':p.get('injuryStatus','UNKNOWN'),'projectedGames':gp,'totals':values})
    if len(rows)<200: raise ValueError('Incomplete projection feed: '+str(len(rows)))
    rows.sort(key=lambda p:int(p['id']))
    return {'schemaVersion':1,'season':f'{season-1}-{str(season)[-2:]}','capturedAt':captured,'source':'ESPN full-season statistical projections','sourceUrl':f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{season}/players?view=kona_player_info','sourceSha256':hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest(),'note':'Source retrieval time, not ESPN projection-generation time. Rankings are calculated from ESPN projected statistics; these are not an independently backtested Roster Report forecast. Injury status is a snapshot. Per-game values do not apply extra injury discounts or weekly schedule adjustments. Positions use ESPN eligibility in every scoring preset.','players':rows,'excluded':excluded}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--season',type=int);parser.add_argument('--input');parser.add_argument('--teams');args=parser.parse_args()
    now=dt.datetime.now(dt.timezone.utc);season=args.season or now.year+(now.month>=7)
    url=f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{season}/players?view=kona_player_info'
    raw=json.loads(pathlib.Path(args.input).read_text()) if args.input else json.loads(fetch(url,{'X-Fantasy-Filter':json.dumps({'players':{'limit':1500}})}))
    team_raw=json.loads(pathlib.Path(args.teams).read_text()) if args.teams else json.loads(fetch(TEAM_URL))
    teams={int(x['team']['id']):x['team']['abbreviation'] for x in team_raw['sports'][0]['leagues'][0]['teams']}
    if len(teams)!=30: raise ValueError('NBA team feed incomplete')
    out=build(raw,teams,season,now.isoformat());target=ROOT/'data/basketball/players.json';target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        previous=json.loads(target.read_text())
        if previous.get('season')==out['season'] and len(out['players'])<0.85*len(previous['players']): raise ValueError('Projection coverage fell more than 15%; retaining last valid snapshot')
    temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');temporary.replace(target)
    print(f"Published {len(out['players'])} basketball projections; excluded {len(out['excluded'])} players without usable forecasts.")
if __name__=='__main__': main()
