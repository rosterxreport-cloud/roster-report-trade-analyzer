"""RR DST research: reconciled scoring ledger and strictly prior matchup bootstrap."""
import argparse,collections,hashlib,json
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd

WEIGHTS={'Sacks':1,'Interceptions':2,'Fumble_Recoveries':2,'Return_TD':6,'Interception_Return_TD':6,'Fumble_Return_TD':6,'Blocked_Kick_Return_TD':6,'Safeties':2,'Blocked_Kicks':2,'Conversion_Returns':2}
BANDS=['0','1-6','7-13','14-20','21-27','28-34','35+']
def band(pa):return 0 if pa==0 else 1 if pa<=6 else 2 if pa<=13 else 3 if pa<=20 else 4 if pa<=27 else 5 if pa<=34 else 6
def score(row):
    if any(not np.isfinite(row[k]) or row[k]<0 for k in list(WEIGHTS)+['Points_Allowed']):raise ValueError('Invalid DST event counts or points allowed')
    return sum(row[k]*w for k,w in WEIGHTS.items())+[10,7,4,1,0,-1,-4][band(row['Points_Allowed'])]
def ledger(frame,through_week):
    data=frame[frame.season_type.eq('REG')&frame.week.le(through_week)].copy()
    if data.duplicated(['game_id','play_id']).any():raise ValueError('Duplicate play identity')
    rows=[];audit=[]
    for gid,game in data.groupby('game_id'):
        game=game.sort_values('play_id');first=game.iloc[0];teams=[first.home_team,first.away_team]
        record={t:dict(gameId=gid,season=int(first.season),week=int(first.week),Team=t,Opponent=teams[1-i],Position='DST',Points_Allowed=0,**{k:0 for k in WEIGHTS}) for i,t in enumerate(teams)}
        scoreboard={t:0 for t in teams};excluded={t:0 for t in teams};plays=[]
        def other(t):
            if t not in teams:raise ValueError('Missing/unknown scoring team')
            return teams[1] if t==teams[0] else teams[0]
        for r in game.to_dict('records'):
            flag=lambda k:r.get(k)==1
            offense,defense=r['posteam'],r['defteam'];special=r['play_type'] in ['kickoff','punt','field_goal','extra_point']
            conversion=flag('two_point_attempt') or flag('extra_point_attempt')
            awarded=[]
            if flag('sack') and not conversion:record[defense]['Sacks']+=1
            if flag('interception') and not conversion:record[defense]['Interceptions']+=1
            if flag('safety'):
                record[defense]['Safeties']+=1;awarded.append((defense,2,False,'safety'))
            if flag('punt_blocked') or r.get('field_goal_result')=='blocked' or r.get('extra_point_result')=='blocked':record[defense]['Blocked_Kicks']+=1
            if not conversion:
                for i in [1,2]:
                    fumbled=r.get(f'fumbled_{i}_team');recovered=r.get(f'fumble_recovery_{i}_team')
                    if isinstance(fumbled,str) and isinstance(recovered,str) and fumbled!=recovered:
                        if recovered not in record:raise ValueError('Unknown fumble recovery team')
                        record[recovered]['Fumble_Recoveries']+=1
            if flag('touchdown') and not conversion:
                team=r['td_team'];against=other(team);is_defense=team==defense and not special
                if special:
                    kind='Blocked_Kick_Return_TD' if flag('punt_blocked') or r.get('field_goal_result')=='blocked' else 'Return_TD'
                    record[team][kind]+=1
                elif is_defense:
                    if flag('interception'):kind='Interception_Return_TD'
                    elif flag('fumble'):kind='Fumble_Return_TD'
                    else:raise ValueError('Unclassified defensive touchdown')
                    record[team][kind]+=1
                awarded.append((team,6,not is_defense,'touchdown'))
            if r.get('field_goal_result')=='made':awarded.append((offense,3,True,'field-goal'))
            if r.get('extra_point_result')=='good':awarded.append((offense,1,True,'extra-point'))
            if r.get('two_point_conv_result')=='success':awarded.append((offense,2,True,'two-point'))
            if flag('defensive_two_point_conv') or flag('defensive_extra_point_conv'):
                record[defense]['Conversion_Returns']+=1;awarded.append((defense,2,True,'conversion-return'))
            for team,points,counts,kind in awarded:
                opponent=other(team);scoreboard[team]+=points
                if counts:record[opponent]['Points_Allowed']+=points
                else:excluded[opponent]+=points
                plays.append(dict(playId=r['play_id'],scoringTeam=team,points=points,countsAgainstDST=counts,type=kind))
        final={teams[0]:int(game.total_home_score.max()),teams[1]:int(game.total_away_score.max())}
        if scoreboard!=final:raise ValueError('Scoring play reconciliation failed '+gid+' '+str((scoreboard,final)))
        for team in teams:
            if record[team]['Points_Allowed']+excluded[team]!=final[other(team)]:raise ValueError('DST points-allowed reconciliation failed')
            record[team]['DraftKings']=score(record[team]);rows.append(record[team])
        audit.append(dict(gameId=gid,scoreboard=scoreboard,excludedOffensePoints=excluded,scoringPlays=plays))
    return rows,audit

def forecast(rows,team,opponent,season,week,draws=10000,seed=20261115):
    prior=[r for r in rows if r['season']==season and r['week']<week]
    own=[r for r in prior if r['Team']==team];opp=[r for r in prior if r['Opponent']==opponent]
    if len(own)<4 or len(opp)<4:raise ValueError('Four strictly prior team and opponent games required')
    # Equal-weight team and matchup samples: a fixed new research hypothesis.
    # Whole event/PA rows retain within-DST dependence, rather than independent Poissons.
    pool=own+opp;weights=np.array([.5/len(own)]*len(own)+[.5/len(opp)]*len(opp));rng=np.random.default_rng(int.from_bytes(hashlib.sha256(f'{seed}:{season}:{week}:{team}:{opponent}'.encode()).digest()[:8],'big'))
    sample=rng.choice(len(pool),draws,p=weights);values=np.array([pool[i]['DraftKings'] for i in sample],dtype=float)
    expected={k:float(sum(w*r[k] for r,w in zip(pool,weights))) for k in WEIGHTS}
    probabilities={b:float(sum(w for r,w in zip(pool,weights) if band(r['Points_Allowed'])==i)) for i,b in enumerate(BANDS)}
    expected['Points_Allowed_Probabilities']=probabilities
    exact=sum(expected[k]*WEIGHTS[k] for k in WEIGHTS)+sum(probabilities[b]*v for b,v in zip(BANDS,[10,7,4,1,0,-1,-4]))
    return dict(Team=team,Opponent=opponent,Position='DST',season=season,week=week,publishApproved=False,policy='rr-dst-team-opponent-bootstrap-v1',throughWeek=max(r['week'] for r in pool),teamGames=len(own),opponentGames=len(opp),projection=exact,mean=float(values.mean()),median=float(np.median(values)),p10=float(np.quantile(values,.1)),p90=float(np.quantile(values,.9)),draws=draws,modeledInputs=expected,scores=values.tolist(),note='Within-DST correlated bootstrap only; not a joint offensive/player/game simulation.')

def run(pbp,stats,schedule,output,season,week,verification_dir=None,salary_pool=None):
    frame=pd.read_parquet(pbp);frame=frame[frame.season.eq(season)];rows,audit=ledger(frame,week-1)
    player=pd.read_parquet(stats);player=player[player.season.eq(season)&player.season_type.eq('REG')&player.week.lt(week)]
    stats_by=player.groupby(['game_id','team'])[['def_sacks','def_interceptions','def_safeties']].sum()
    checks=[]
    for r in rows:
        if (r['gameId'],r['Team']) not in stats_by.index:raise ValueError('No independent team statistic match')
        actual=stats_by.loc[r['gameId'],r['Team']]
        for field,source in [('Sacks','def_sacks'),('Interceptions','def_interceptions'),('Safeties','def_safeties')]:
            if abs(r[field]-actual[source])>1e-8:checks.append(dict(gameId=r['gameId'],team=r['Team'],field=field,pbp=r[field],weekly=float(actual[source])))
    schedule_frame=pd.read_csv(schedule)
    for game in audit:
        scheduled=schedule_frame[schedule_frame.game_id.eq(game['gameId'])]
        if len(scheduled)!=1:raise ValueError('Historical game missing from schedule')
        g=scheduled.iloc[0]
        if not np.isfinite(g.home_score) or not np.isfinite(g.away_score) or game['scoreboard']!={g.home_team:int(g.home_score),g.away_team:int(g.away_score)}:raise ValueError('Incomplete or mismatched final scheduled score')
    for check in checks:
        matching=[r for r in rows if r['gameId']==check['gameId'] and r['Team']==check['team']][0]
        if check['field']=='Sacks':
            opposing=player[player.game_id.eq(check['gameId'])&player.team.eq(matching['Opponent'])]
            if float(opposing.sacks_suffered.sum())==check['pbp']:
                check.update(resolved=True,resolution='Team sacks corroborated by opposing weekly sacks suffered; individual defensive credits omit team sacks.')
        elif check['field']=='Safeties' and verification_dir:
            schedule_row=schedule_frame[schedule_frame.game_id.eq(check['gameId'])].iloc[0];event=str(schedule_row.espn)
            path=verification_dir/(event+'.json');receipt_path=verification_dir/(event+'-receipt.json')
            if path.exists() and receipt_path.exists():
                body=path.read_bytes();doc=json.loads(body);receipt=json.loads(receipt_path.read_text())
                expected_url='https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event='+event
                competition=doc['header']['competitions'][0]
                if receipt['sha256']!=hashlib.sha256(body).hexdigest() or receipt['url']!=expected_url or doc['header']['id']!=event or competition['status']['type']['completed'] is not True:raise ValueError('Invalid safety verification evidence')
                competitors={c['team']['abbreviation']:int(c['score']) for c in competition['competitors']}
                expected={schedule_row.home_team:int(schedule_row.home_score),schedule_row.away_team:int(schedule_row.away_score)}
                safety_count=sum(x.get('scoringType',{}).get('name')=='safety' and x.get('team',{}).get('abbreviation')==check['team'] for x in doc['scoringPlays'])
                if competitors==expected and safety_count==check['pbp']:check.update(resolved=True,resolution='Final ESPN scoring plays and scoreboard corroborate play-by-play; frozen weekly player statistic differs.',source=expected_url,sourceHash=receipt['sha256'])
    backtest=[]
    for r in rows:
        try:
            f=forecast(rows,r['Team'],r['Opponent'],season,r['week']);history=[x for x in rows if x['Team']==r['Team'] and x['week']<r['week']]
            baseline=float(np.mean([x['DraftKings'] for x in history]));backtest.append(dict(gameId=r['gameId'],week=r['week'],team=r['Team'],actual=r['DraftKings'],projection=f['projection'],baseline=baseline,error=f['projection']-r['DraftKings'],baselineError=baseline-r['DraftKings'],leagueBaselineError=float(np.mean([x['DraftKings'] for x in rows if x['week']<r['week']]))-r['DraftKings'],inside80=f['p10']<=r['DraftKings']<=f['p90']))
        except ValueError:continue
    blocks=collections.defaultdict(list)
    for r in backtest:blocks[r['gameId']].append(r)
    keys=list(blocks);rng=np.random.default_rng(20261115);boot=[]
    for _ in range(2000):
        resampled=[r for key in rng.choice(keys,len(keys),replace=True) for r in blocks[key]]
        boot.append([np.mean([abs(r['error'])-abs(r[k]) for r in resampled]) for k in ['baselineError','leagueBaselineError']])
    intervals=dict(zip(['candidateMinusOwnBaselineMAE','candidateMinusLeagueBaselineMAE'],np.quantile(np.array(boot),[.025,.975],axis=0).T.tolist())) if boot else {}
    games=pd.read_csv(schedule);games=games[games.season.eq(season)&games.week.eq(week)&games.game_type.eq('REG')];forecasts=[]
    for g in games.to_dict('records'):
        for team,opp in [(g['home_team'],g['away_team']),(g['away_team'],g['home_team'])]:forecasts.append(forecast(rows,team,opp,season,week))
    mean=lambda key:float(np.mean([abs(r[key]) for r in backtest])) if backtest else None
    salary_join=None
    if salary_pool:
        pool=json.loads(salary_pool.read_text())
        if pool.get('sport')!='NFL' or pool.get('salaryDataApproved') is not True:raise ValueError('Verified official NFL salary pool required')
        normalize=lambda team:'LAR' if team=='LA' else team
        mapping={(normalize(f['Team']),normalize(f['Opponent'])):f for f in forecasts}
        joined=[]
        for player in pool['players']:
            if player['positions']!=['DST']:continue
            key=(player['team'],player['opponent'])
            if key not in mapping:raise ValueError('Official DST has no unique same-matchup model forecast')
            f=mapping[key];joined.append(dict(id=player['id'],team=player['team'],opponent=player['opponent'],salary=player['salary'],gameId=player['gameId'],projection=f['projection'],p10=f['p10'],p90=f['p90'],publishApproved=False))
        if len({r['id'] for r in joined})!=len(joined):raise ValueError('Duplicate DST salary identity')
        salary_join=dict(draftGroupId=pool['draftGroupId'],capturedAt=pool['capturedAt'],locksAt=pool['locksAt'],salaryPoolHash=hashlib.sha256(salary_pool.read_bytes()).hexdigest(),players=joined,note='Research identity join only. This locked historical pool is not a current playable slate.')
    report=dict(publishApproved=False,generatedAt=datetime.now(timezone.utc).isoformat(),forecastTiming='Post-lock research reconstruction; not a frozen playable forecast',season=season,targetWeek=week,hashes={label:hashlib.sha256(path.read_bytes()).hexdigest() for label,path in [('pbp',pbp),('stats',stats),('schedule',schedule)]},games=len(audit),teamGames=len(rows),componentMismatches=checks,dataReconciled=all(r.get('resolved') for r in checks),unresolvedComponentMismatches=[r for r in checks if not r.get('resolved')],backtest=dict(gameClusterBootstrap95=intervals,n=len(backtest),games=len({r['gameId'] for r in backtest}),mae=mean('error'),ownHistoryBaselineMAE=mean('baselineError'),leagueHistoryBaselineMAE=mean('leagueBaselineError'),middle80Coverage=float(np.mean([r['inside80'] for r in backtest])) if backtest else None,rows=backtest),salaryJoin=salary_join,forecasts=forecasts,ledger=rows,scoringAudit=audit,limitations=['New exploratory DST policy; weights are declared here but historical outcomes were already accessible. No untouched holdout or prospective validation is claimed.','Post-hoc provider corrections may differ from records originally available before lock.','Scoreboard and selected weekly-stat reconciliation do not establish agreement with official DraftKings contest settlements.','Bootstrap preserves dependence within each historical DST result, not joint dependence with selected offensive players or opposing DST.','Forecasts cover the schedule, not a verified active DraftKings slate. No salary, injury, ownership, payout or ROI approval.','Component mismatches, if present, require review before historical labels or forecasts can be approved.'])
    output.mkdir(parents=True,exist_ok=False);(output/'dst-research.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps({k:report[k] for k in ['games','teamGames','componentMismatches']}));print(json.dumps({k:v for k,v in report['backtest'].items() if k!='rows'},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['pbp','stats','schedule','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--verification-dir',type=Path)
    p.add_argument('--salary-pool',type=Path)
    p.add_argument('--season',type=int,required=True);p.add_argument('--week',type=int,required=True)
    a=p.parse_args();run(a.pbp,a.stats,a.schedule,a.output,a.season,a.week,a.verification_dir,a.salary_pool)
