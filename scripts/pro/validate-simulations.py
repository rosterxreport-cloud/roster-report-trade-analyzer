"""Validate recovered RR joint draws against frozen forecasts; never approves releases."""
import argparse, collections, copy, hashlib, importlib.util, json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

DK={'PTS':1.,'FG3M':.5,'REB':1.25,'AST':1.5,'STL':2.,'BLK':2.,'TOV':-.5}


def score(box, index):
    categories=sum(box[:,index[k]]>=10 for k in ('PTS','REB','AST','STL','BLK'))
    return sum(box[:,index[k]]*w for k,w in DK.items())+1.5*(categories>=2)+3.*(categories>=3)


def crps(draws, actual):
    ordered=np.sort(draws);n=len(ordered)
    return float(np.abs(ordered-actual).mean()-np.dot(2*np.arange(1,n+1)-n-1,ordered)/(n*n))


def validate_boxes(forecasts,index,draws):
    games=collections.defaultdict(lambda:collections.defaultdict(list))
    for (game,player),(row,box) in forecasts.items():
        if box.shape!=(draws,len(index)) or not np.isfinite(box).all() or (box<0).any():raise ValueError('Invalid simulation dimensions or counts')
        for made,attempts in [('FGM','FGA'),('FG3M','FG3A'),('FTM','FTA'),('FG3A','FGA')]:
            if (box[:,index[made]]>box[:,index[attempts]]).any():raise ValueError('Makes exceed attempts')
        if (box[:,index['FG3M']]>box[:,index['FGM']]).any():raise ValueError('Three-point makes exceed all makes')
        if not np.allclose(box[:,index['PTS']],2*box[:,index['FGM']]+box[:,index['FG3M']]+box[:,index['FTM']]):raise ValueError('Box score point identity failed')
        games[game][row['team']].append(box)
    for teams in games.values():
        if len(teams)!=2:raise ValueError('Joint game requires two teams')
        a,b=[np.stack(rows).sum(axis=0) for rows in teams.values()]
        if not np.allclose(a[:,index['MIN']],b[:,index['MIN']]):raise ValueError('Opponents have inconsistent game lengths')
        lengths=a[:,index['MIN']]/5
        if ((lengths<48-1e-7)|(~np.isclose(lengths,48+5*np.rint((lengths-48)/5),rtol=0,atol=1e-7))).any():raise ValueError('Invalid regulation/overtime minutes')
        for rows in teams.values():
            if any((box[:,index['MIN']]>lengths+1e-7).any() for box in rows):raise ValueError('Player exceeds game minutes')
        for own,other in [(a,b),(b,a)]:
            if (own[:,index['AST']]>own[:,index['FGM']]).any():raise ValueError('Assists exceed made baskets')
            if (own[:,index['STL']]>other[:,index['TOV']]).any():raise ValueError('Steals exceed opposing turnovers')
            if (own[:,index['BLK']]>other[:,index['FGA']]-other[:,index['FGM']]).any():raise ValueError('Blocks exceed opposing misses')
    return len(games)


def summarize(rows):
    if not rows:return {'n':0}
    mean=lambda key:float(np.mean([r[key] for r in rows]))
    coverage=mean('inside80');n=len(rows)
    blocks=collections.defaultdict(list)
    for row in rows:blocks[row['game']].append(row)
    keys=list(blocks);rng=np.random.default_rng(20261115);sample=rng.integers(0,len(keys),(2000,len(keys)))
    counts=np.array([len(blocks[k]) for k in keys]);denominator=counts[sample].sum(axis=1)
    intervals={}
    for label,fn in [('middle80_coverage',lambda r:r['inside80']),('simulation_mean_mae',lambda r:r['mean_error']),('simulation_mean_minus_point_mae',lambda r:r['mean_error']-r['point_error'])]:
        totals=np.array([sum(fn(r) for r in blocks[k]) for k in keys]);values=totals[sample].sum(axis=1)/denominator
        intervals[label]=np.quantile(values,[.025,.975]).tolist() if np.isfinite(values).all() else None
    return dict(n=n,games=len({r['game'] for r in rows}),dates=len({r['date'] for r in rows}),
        game_cluster_bootstrap_95=intervals,incumbent_dk_mae=mean('point_error'),simulation_mean_dk_mae=mean('mean_error'),
        simulation_median_dk_mae=mean('median_error'),simulation_mean_dk_bias=mean('bias'),
        played_conditional_mean_dk_mae=mean('conditional_mean_error'),played_conditional_mean_dk_bias=mean('conditional_bias'),
        played_conditional_middle80_coverage=mean('conditional_inside80'),
        middle80_coverage=coverage,middle80_mean_width=mean('width'),below_p10=mean('below'),above_p90=mean('above'),
        mean_crps=mean('crps'),simulated_minutes_mae=mean('minutes_error'),
        note='Played appearances only; dependent player-games are not independent trials.')


def run(root,dates,draws,seed):
    sys.path.insert(0,str(root/'src'))
    from simulate_slate import simulate, INDEX
    spec=importlib.util.spec_from_file_location('shooting_adapter',Path(__file__).with_name('audit-shooting.py'))
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter);apply=adapter.load_policy(root)
    origins=json.loads((root/'data/period_origins.json').read_text())['origins']
    observed={}
    for file in sorted((root/'data').glob('observed_archive_*.json'))+[root/'data/live_observed_games.json']:
        for row in json.loads(file.read_text())['games']:observed[(row['season'],row['game'],row['player'])]=row
    history=collections.defaultdict(list)
    for row in observed.values():history[str(row['player'])].append(row)
    auditpath=root/'forward/audit_rows.json';audit=json.loads(auditpath.read_text())
    actual={(str(r['game']),str(r['player'])):r for r in audit}
    outputs=collections.defaultdict(list);checks=[];hashes={}
    for day in dates:
        path=root/'forward/predictions'/f'{day}.json';raw=path.read_bytes();hashes[day]=hashlib.sha256(raw).hexdigest();snapshot=json.loads(raw)
        challenger=copy.deepcopy(snapshot);missing=[]
        for row in challenger['predictions']:
            prior=adapter.prior_history(history[str(row['player'])],origins,row['player'],day)
            adjusted=apply(row['model'],prior)
            if adjusted is None:missing.append({'player':row['player'],'game':row['game']})
            else:row['model']=adjusted
        rejected={r['game'] for r in missing}
        # Whole games are withheld: dropping one uncovered player would redistribute
        # their minutes and opportunities to teammates, changing more than shooting.
        challenger['predictions']=[r for r in challenger['predictions'] if r['game'] not in rejected]
        for label,source in [('incumbent',snapshot),('historical_shooting_challenger',challenger)]:
            if not source['predictions']:
                checks.append(dict(date=day,variant=label,skipped=True,missingHistory=missing));continue
            forecasts,noise=simulate(source,audit,draws,seed)
            games=validate_boxes(forecasts,INDEX,draws)
            matched=0
            for identity,(row,box) in forecasts.items():
                saved=actual.get(tuple(map(str,identity)))
                if not saved or saved['actual']['MIN']<=0:continue
                if saved['modelVersion']!=snapshot['model']:raise ValueError('Audit policy does not match the frozen forecast')
                result=saved['actual'];observed_box=np.array([[result[k] for k in INDEX]])
                y=float(score(observed_box,INDEX)[0]);values=score(box,INDEX)
                lo,median,hi=np.quantile(values,[.1,.5,.9]);mean=float(values.mean())
                played_values=values[box[:,INDEX['MIN']]>0]
                if not len(played_values):raise ValueError('No played draws for an observed played appearance')
                conditional_mean=float(played_values.mean());conditional_lo,conditional_hi=np.quantile(played_values,[.1,.9])
                point=row.get('DraftKings') if label=='incumbent' else None
                outputs[label].append(dict(date=day,game=str(identity[0]),player=str(identity[1]),
                    point_error=abs(point-y) if point is not None else float('nan'),
                    mean_error=abs(mean-y),median_error=abs(float(median)-y),bias=mean-y,
                    conditional_mean_error=abs(conditional_mean-y),conditional_bias=conditional_mean-y,conditional_inside80=float(conditional_lo<=y<=conditional_hi),
                    inside80=float(lo<=y<=hi),width=float(hi-lo),below=float(y<lo),above=float(y>hi),
                    crps=crps(values,y),minutes_error=abs(float(box[:,INDEX['MIN']].mean())-result['MIN'])))
                matched+=1
            checks.append(dict(date=day,variant=label,structuralChecksPassed=True,players=len(forecasts),games=games,
                drawsPerPlayer=draws,matchedPlayed=matched,withheldGames=sorted(rejected) if label!='incumbent' else [],
                missingHistory=missing if label!='incumbent' else [],minutesNoise=noise,
                sourceAvailability=dict(collections.Counter(r.get('status_asof_capture','missing') for r in source['predictions']))))
            print(day,label,'players',len(forecasts),'matched',matched,flush=True)
    identities={(r['date'],r['game'],r['player']) for r in outputs['historical_shooting_challenger']}
    paired=[r for r in outputs['incumbent'] if (r['date'],r['game'],r['player']) in identities]
    def clean(value):
        if isinstance(value,float) and not np.isfinite(value):return None
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    return clean(dict(publishApproved=False,executedAt=datetime.now(timezone.utc).isoformat(),drawsPerPlayer=draws,seed=seed,
        sourceHashes=hashes,auditHash=hashlib.sha256(auditpath.read_bytes()).hexdigest(),
        simulatorHash=hashlib.sha256((root/'src/simulate_slate.py').read_bytes()).hexdigest(),
        checks=checks,metrics={k:summarize(v) for k,v in outputs.items()},incumbentOnChallengerCohort=summarize(paired),
        limitations=['Retrospective simulator evaluation on immutable incumbent forecasts; the challenger was derived now and was never a saved pregame forecast.',
            'Simulated minutes noise uses only earlier dates within the source policy. No weights or noise scales are tuned in this evaluation.',
            'Observed cohorts contain played appearances only. Both all-draw and played-draw-conditional simulation means are reported; the original point forecast is conditional on playing. DNP participation calibration is not established.',
            'Historical shooting uses prior observed percentages; entire games with unsupported player shooting history are withheld from the challenger.',
            'No salary, ownership, contest, profit or complete-slate performance approval is implied.',
            'Unknown injury statuses and the source publication gate remain release blockers.']))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model-dir',type=Path,required=True);p.add_argument('--dates',nargs='+',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--draws',type=int,default=10000);p.add_argument('--seed',type=int,default=20261115);a=p.parse_args()
    result=run(a.model_dir.resolve(),a.dates,a.draws,a.seed);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(result['metrics'],indent=2))
