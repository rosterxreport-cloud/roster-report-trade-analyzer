"""Experimental RR DFS event extension. Prior-only inputs; never release approval."""
import argparse,collections,hashlib,json,re,unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

EVENTS=['fumbles_lost_total','passing_2pt_conversions','rushing_2pt_conversions','receiving_2pt_conversions','special_teams_tds','fumble_recovery_tds']
YARDS=[('Pass_Yds','passing_yards',300),('Rush_Yds','rushing_yards',100),('Rec_Yds','receiving_yards',100)]
def name_key(value):
    return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower())

def extend(row,history,season,week):
    prior=[r for r in history if r['season']==season and r['week']<week and r['season_type']=='REG']
    if len(prior)<4:raise ValueError('Fewer than four recorded prior appearances')
    required=EVENTS+['attempts','carries','targets','receptions']+[k for _,k,_ in YARDS]
    if any(not isinstance(r.get(k),(int,float)) or not np.isfinite(r[k]) for r in prior for k in required):raise ValueError('Missing/nonfinite historical events')
    if any(r[k]<0 for r in prior for k in EVENTS+['attempts','carries','targets','receptions']):raise ValueError('Negative event counts')
    inputs=['Pass_Att','Pass_Yds','Pass_TD','INT','Rush_Att','Rush_Yds','Rush_TD','Targets','Receptions','Rec_Yds','Rec_TD']
    if any(not np.isfinite(row[k]) or row[k]<0 for k in inputs) or row['Receptions']>row['Targets']+.01:raise ValueError('Invalid source forecast')
    mean=lambda k:float(np.mean([r[k] for r in prior]))
    rate=lambda outcome,opportunity,forecast:mean(outcome)/mean(opportunity)*forecast if mean(opportunity)>0 else (0. if forecast==0 else None)
    fumble_opportunity=sum(mean(k) for k in ['attempts','carries','receptions'])
    projected_opportunity=row['Pass_Att']+row['Rush_Att']+row['Receptions']
    fumbles=mean('fumbles_lost_total')/fumble_opportunity*projected_opportunity if fumble_opportunity>0 else None
    conversions=[rate(a,b,row[c]) for a,b,c in [('passing_2pt_conversions','attempts','Pass_Att'),('rushing_2pt_conversions','carries','Rush_Att'),('receiving_2pt_conversions','targets','Targets')]]
    if fumbles is None or any(v is None for v in conversions):raise ValueError('Projected opportunity lacks observed rate support')
    probabilities=[]
    for projected,observed,threshold in YARDS:
        value=row[projected];average=mean(observed)
        if value==0:probabilities.append(0.);continue
        if average<=0:raise ValueError('No positive historical yardage basis for projected production')
        probabilities.append(float(np.mean([r[observed]*value/average>=threshold for r in prior])))
    events=dict(Fumbles_Lost=fumbles,Two_Point_Conversions=sum(conversions),Return_TD=mean('special_teams_tds'),Offensive_Fumble_Recovery_TD=mean('fumble_recovery_tds'),Pass_300_Probability=probabilities[0],Rush_100_Probability=probabilities[1],Rec_100_Probability=probabilities[2])
    core=.04*row['Pass_Yds']+4*row['Pass_TD']-row['INT']+.1*(row['Rush_Yds']+row['Rec_Yds'])+6*(row['Rush_TD']+row['Rec_TD'])+row['Receptions']
    adjustment=-fumbles+2*events['Two_Point_Conversions']+6*(events['Return_TD']+events['Offensive_Fumble_Recovery_TD'])+3*sum(probabilities)
    return {'events':events,'DraftKings':core+adjustment,'priorAppearances':len(prior),'throughWeek':max(r['week'] for r in prior),'publishApproved':False}

def actual_score(r):
    required=EVENTS+['passing_yards','passing_tds','passing_interceptions','rushing_yards','rushing_tds','receiving_yards','receiving_tds','receptions']
    if any(not np.isfinite(r[k]) for k in required):raise ValueError('Missing actual scoring events')
    if r['def_tds'] or (r['special_teams_tds'] and r['fumble_recovery_tds']):raise ValueError('TD classification needs play-level adjudication')
    return .04*r['passing_yards']+4*r['passing_tds']-r['passing_interceptions']+.1*(r['rushing_yards']+r['receiving_yards'])+6*(r['rushing_tds']+r['receiving_tds']+r['special_teams_tds']+r['fumble_recovery_tds'])+r['receptions']-r['fumbles_lost_total']+2*sum(r[k] for k in EVENTS[1:4])+3*sum(r[k]>=t for _,k,t in YARDS)

def run(forecast,stats,schedule,season,week,captured,output):
    cutoff=datetime.fromisoformat(captured.replace('Z','+00:00'))
    if cutoff.utcoffset() is None:raise ValueError('Capture requires timezone')
    frame=pd.read_parquet(stats);records=frame[frame.season_type.eq('REG')&frame.season.eq(season)].to_dict('records')
    histories=collections.defaultdict(list);identities=collections.defaultdict(set);actuals=collections.defaultdict(list)
    for r in records:
        histories[r['player_id']].append(r)
        if r['week']<week:identities[name_key(r['player_display_name']),r['position']].add(r['player_id'])
        if r['week']==week:actuals[r['player_id'],r['team'],r['opponent_team']].append(r)
    games=pd.read_csv(schedule);games=games[games.season.eq(season)&games.week.eq(week)&games.game_type.eq('REG')];kickoffs={}
    for r in games.to_dict('records'):
        start=datetime.fromisoformat(r['gameday']+'T'+r['gametime']).replace(tzinfo=ZoneInfo('America/New_York'))
        kickoffs[r['home_team'],r['away_team']]=start;kickoffs[r['away_team'],r['home_team']]=start
    rows=pd.read_csv(forecast).to_dict('records');counts=collections.Counter(name_key(r['Player']) for r in rows);candidates=[];excluded=[];results=[]
    for row in rows:
        try:
            identity=identities[name_key(row['Player']),row['Position']]
            if len(identity)!=1 or counts[name_key(row['Player'])]!=1:raise ValueError('Ambiguous/unmatched prior-only player identity')
            if (row['Team'],row['Opponent']) not in kickoffs or kickoffs[row['Team'],row['Opponent']]<=cutoff:raise ValueError('No uniquely matching future scheduled game at capture')
            if re.search(r'\bOUT\b|\bIR\b|injured reserve',str(row.get('note','')),re.I):raise ValueError('Source availability conflict')
            pid=next(iter(identity));extension=extend(row,histories[pid],season,week)
            candidates.append(dict(playerId=pid,Player=row['Player'],Team=row['Team'],Position=row['Position'],**extension))
            match=actuals[pid,row['Team'],row['Opponent']]
            if len(match)==1:
                try:
                    actual=actual_score(match[0]);results.append(dict(playerId=pid,position=row['Position'],game=match[0]['game_id'],forecast=extension['DraftKings'],actual=actual,error=extension['DraftKings']-actual))
                except ValueError as e:excluded.append(dict(player=row['Player'],stage='actuals',reason=str(e)))
        except ValueError as e:excluded.append(dict(player=row['Player'],stage='candidate',reason=str(e)))
    summary=lambda group:{'n':len(group),'mae':float(np.mean([abs(r['error']) for r in group])) if group else None,'bias':float(np.mean([r['error'] for r in group])) if group else None}
    report=dict(publishApproved=False,policy='rr-prior-player-empirical-events-v1-research',season=season,week=week,forecastCapturedAt=captured,hashes={label:hashlib.sha256(p.read_bytes()).hexdigest() for label,p in [('forecast',forecast),('stats',stats),('schedule',schedule)]},candidates=candidates,excluded=excluded,metrics=summary(results),positions={p:summary([r for r in results if r['position']==p]) for p in ['QB','RB','WR','TE']},results=results,limitations=['Experimental extension, not the previously validated original model. No source forecasts changed.','Prior recorded appearances only; no DNP-inclusive accuracy or zero-filling. Historical provider corrections may differ from pre-lock data.','Bonus probabilities use rescaled own-player empirical yardage, anchored to unchanged RR means. Four-game minimum is a support guard, not proof of calibration.','Rare-event rates are unsmoothed own-player historical estimates; sampling zero is an estimate, not absence of risk.','Fumble recovery TD classification is unresolved for overlapping special-team/defensive TD records; ambiguous observed records are withheld.','No release-approved DST, joint correlated NFL simulations, salary replay, contest payout or profitability claim.'])
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps({'candidates':len(candidates),'excluded':len(excluded),'metrics':report['metrics'],'positions':report['positions']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['forecast','stats','schedule','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--season',type=int,required=True);p.add_argument('--week',type=int,required=True);p.add_argument('--captured-at',required=True)
    a=p.parse_args();run(a.forecast,a.stats,a.schedule,a.season,a.week,a.captured_at,a.output)
