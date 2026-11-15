"""Grade an archived RR forecast against recorded NFL observations, without refitting."""
import argparse,collections,hashlib,json,re,unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np


def key(value):
    text=unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower()
    return re.sub('[^a-z0-9]','',re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',text))


def run(forecast,actuals,schedule,season,week,captured):
    stamp=datetime.fromisoformat(captured.replace('Z','+00:00'))
    if stamp.utcoffset() is None:raise ValueError('Forecast capture requires a timezone')
    predictions=pd.read_csv(forecast).to_dict('records');observed=pd.read_parquet(actuals)
    observed=observed[(observed.season==season)&(observed.week==week)&(observed.season_type=='REG')]
    games=pd.read_csv(schedule);games=games[(games.season==season)&(games.week==week)&(games.game_type=='REG')]
    by_match={}
    for game in games.to_dict('records'):
        start=datetime.fromisoformat(game['gameday']+'T'+game['gametime']).replace(tzinfo=ZoneInfo('America/New_York'))
        for team,opp in [(game['home_team'],game['away_team']),(game['away_team'],game['home_team'])]:by_match[team,opp]=(game['game_id'],start)
    by_id=collections.defaultdict(list)
    for row in observed.to_dict('records'):by_id[key(row['player_display_name']),row['team'],row['opponent_team'],row['position']].append(row)
    matched=[];excluded=[];seen=set()
    for row in predictions:
        identity=(key(row['Player']),row['Team'],row['Opponent'],row['Position'])
        if identity in seen:raise ValueError('Duplicate forecast identity')
        seen.add(identity)
        game=by_match.get((row['Team'],row['Opponent']))
        if not game or game[1]<=stamp:
            excluded.append(dict(player=row['Player'],team=row['Team'],reason='No matching future game at forecast capture'));continue
        actual=by_id.get(identity,[])
        if len(actual)!=1:
            excluded.append(dict(player=row['Player'],team=row['Team'],reason='No unique recorded actual; not assumed zero'));continue
        actual=actual[0]
        if actual['game_id']!=game[0]:raise ValueError('Actual game mismatch')
        if not np.isfinite(actual['fantasy_points_ppr']) or not np.isfinite(row['PPR']):raise ValueError('Nonfinite score')
        matched.append(dict(player=row['Player'],position=row['Position'],team=row['Team'],game=game[0],
            forecast=float(row['PPR']),actual=float(actual['fantasy_points_ppr']),error=float(row['PPR']-actual['fantasy_points_ppr'])))
    def summary(rows):
        if not rows:return {'n':0}
        errors=np.array([r['error'] for r in rows]);return dict(n=len(rows),mae=float(np.abs(errors).mean()),bias=float(errors.mean()),rmse=float(np.sqrt(np.square(errors).mean())))
    return dict(publishApproved=False,season=season,week=week,forecastCapturedAt=captured,
        hashes={label:hashlib.sha256(file.read_bytes()).hexdigest() for label,file in [('forecast',forecast),('actuals',actuals),('schedule',schedule)]},
        metrics=summary(matched),positions={p:summary([r for r in matched if r['position']==p]) for p in ['QB','RB','WR','TE']},
        forecastRows=len(predictions),matchedGames=len({r['game'] for r in matched}),excluded=excluded,
        largestAbsoluteErrors=sorted(matched,key=lambda r:abs(r['error']),reverse=True)[:10],
        limitations=['Archived forecast is used unchanged; no fitting or selection by actual outcome.',
            'Capture timestamp comes from the file registration metadata; Thursday forecasts are excluded because their separate original timestamp is not established here.',
            'Only uniquely matched recorded observations are graded. Missing actuals are not treated as DNP or zero.',
            'Scores use recorded nflverse PPR, not DraftKings scoring. No salary or contest lineup backtest is implied.',
            'One week does not establish calibration, profitability, or release readiness.'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ['forecast','actuals','schedule','output']:p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--season',type=int,required=True);p.add_argument('--week',type=int,required=True);p.add_argument('--forecast-captured-at',required=True)
    a=p.parse_args();result=run(a.forecast,a.actuals,a.schedule,a.season,a.week,a.forecast_captured_at);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps({k:result[k] for k in ['metrics','positions','forecastRows','matchedGames']},indent=2))
