"""Pair verified salary facts with existing RR forecasts; never grants model approval."""
import argparse,collections,hashlib,json,re,unicodedata
from datetime import datetime
from pathlib import Path
NBA_TEAMS=dict(enumerate('ATL BOS NOP CHI CLE DAL DEN DET GSW HOU IND LAC LAL MIA MIL MIN BKN NYK ORL PHI PHX POR SAC SAS OKC UTA WAS TOR MEM CHA'.split(),1))

def key(name):
    name=unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().lower()
    return re.sub('[^a-z0-9]','',re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',name))

def stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00'))

def pair(pool,forecast):
    if pool.get('salaryDataApproved') is not True:raise ValueError('Salary pool has not passed source validation')
    sport=pool['sport'];nba=sport=='NBA';rows=forecast['predictions'] if nba else forecast['players']
    captured=forecast['createdAt'] if nba else forecast['updatedAt']
    if stamp(captured)>=stamp(pool['locksAt']):raise ValueError('Forecast postdates slate lock')
    team=lambda row:NBA_TEAMS[row['team']] if nba else {'LA':'LAR'}.get(row['Team'],row['Team'])
    # Reuse the one explicit alias in the recovered NBA optimizer; no fuzzy joins.
    name_key=lambda name:{'alexandresarr':'alexsarr'}.get(key(name),key(name)) if nba else key(name)
    lookup=collections.defaultdict(list)
    for row in rows:lookup[name_key(row['name'] if nba else row['Player']),team(row)].append(row)
    gameTeams=collections.defaultdict(set)
    if nba:
        for row in rows:gameTeams[str(row['game'])].add(team(row))
    officialGames={g['id']:g for g in pool['games']};matched=[];unmatched=[]
    for salary in pool['players']:
        candidates=lookup[name_key(salary['name']),salary['team']];valid=[]
        for row in candidates:
            game=officialGames[salary['gameId']]
            if nba:
                match=gameTeams[str(row['game'])]=={game['away'],game['home']} and stamp(row['start'])==stamp(game['startsAt'])
            else:match={'LA':'LAR'}.get(row['Opponent'],row['Opponent'])==salary['opponent'] and row['Position'] in salary['positions']
            if match:valid.append(row)
        if len(valid)!=1:
            unmatched.append(dict(id=salary['id'],name=salary['name'],team=salary['team'],sourceStatus=salary['sourceStatus'],reason='No unique model name/team/game/position match'));continue
        row=valid[0]
        matched.append(dict(id=salary['id'],name=salary['name'],team=salary['team'],salary=salary['salary'],positions=salary['positions'],gameId=salary['gameId'],startsAt=salary['startsAt'],modelId=str(row['player']) if nba else row['Player']+'|'+row['Team']+'|'+row['Position'],modelGameId=str(row['game']) if nba else None,
            rrDraftKings=row['DraftKings'] if nba else None,rrPPR=None if nba else row['PPR'],sourceStatus=salary['sourceStatus'],modelReleaseApproved=False,availabilityVerified=False,
            identityMethod='Exact normalized name + team + matching game; recorded Alexandre/Alex Sarr alias only' if nba else 'Exact normalized name + team + opponent + position; LA/LAR team alias only'))
    return dict(schemaVersion=1,sport=sport,draftGroupId=pool['draftGroupId'],publishApproved=False,salaryDataApproved=True,forecastCapturedAt=captured,salaryCapturedAt=pool['capturedAt'],locksAt=pool['locksAt'],matchedPlayers=len(matched),unmatchedPlayers=len(unmatched),players=matched,unmatched=unmatched,
        limitations=['Research pairing of an existing saved forecast, not a newly generated or approved model release.',
            'No generic forecasts, zero fills, salary-based valuations or fuzzy identity matching.',
            'NFL PPR is not represented as DraftKings scoring; its rrDraftKings field remains null.',
            'DraftKings operator status is retained without treating unlisted status as verified active.',
            'Complete game coverage, injuries, rotations, model policy and uncertainty gates remain separate from salary approval.'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pool',type=Path,required=True);p.add_argument('--forecast',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=pair(json.loads(a.pool.read_text()),json.loads(a.forecast.read_text()));result['sourceHashes']={label:hashlib.sha256(file.read_bytes()).hexdigest() for label,file in [('salaryPool',a.pool),('forecast',a.forecast)]};a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps({k:result[k] for k in ['sport','draftGroupId','matchedPlayers','unmatchedPlayers','publishApproved']}))
