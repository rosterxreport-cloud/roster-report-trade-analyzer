"""Freeze a pre-lock RR historical-shooting candidate without approving publication.
Uses the recovered model's existing shotline guard and joint simulator. No fitting.
"""
import argparse,collections,copy,hashlib,importlib.util,json,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np


def load_helper(name,file):
    spec=importlib.util.spec_from_file_location(name,file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def run(root,snapshot_file,pool_file,injury_file,output,seed):
    NBA_TEAMS=load_helper('candidate_pairing',Path(__file__).with_name('pair-salary-research.py')).NBA_TEAMS
    if output.exists():raise ValueError('Choose a new output directory; never overwrite a frozen candidate')
    output.mkdir(parents=True)
    decision=datetime.now(timezone.utc)
    source=json.loads(snapshot_file.read_text());pool=json.loads(pool_file.read_text());injury=json.loads(injury_file.read_text())
    stamp=lambda x:datetime.fromisoformat(x.replace('Z','+00:00'))
    if pool.get('salaryDataApproved') is not True or pool.get('sport')!='NBA':raise ValueError('A verified NBA salary capture is required')
    if decision>=stamp(pool['locksAt']) or stamp(source['createdAt'])>decision or stamp(pool['capturedAt'])>decision or stamp(injury['capturedAt'])>decision:raise ValueError('Candidate must be generated before first slate lock using already captured sources')
    if not injury.get('source') or not injury.get('rawSha256'):raise ValueError('Dated official injury provenance is required')
    sys.path.insert(0,str(root/'src'))
    from shooting_policy import historical_percentages
    from shooting_redistribution import shotline,attempts
    from simulate_slate import simulate,INDEX,FIELDS
    from draftkings_audit import DK
    audit_helper=load_helper('candidate_history',Path(__file__).with_name('audit-shooting.py'))
    validator=load_helper('candidate_joint_validation',Path(__file__).with_name('validate-simulations.py'))
    observations={}
    files=sorted((root/'data').glob('observed_archive_*.json'))+[root/'data/live_observed_games.json']
    for file in files:
        for row in json.loads(file.read_text())['games']:
            key=(row['season'],row['game'],row['player'])
            if key in observations and any(observations[key][f]!=row[f] for f in ['FGM','FGA','FG3M','FG3A','FTM','FTA']):raise ValueError('Conflicting historical counts')
            observations[key]=row
    history=collections.defaultdict(list)
    for row in observations.values():history[str(row['player'])].append(row)
    origins=json.loads((root/'data/period_origins.json').read_text())['origins']
    game_teams=collections.defaultdict(set)
    for row in source['predictions']:game_teams[str(row['game'])].add(NBA_TEAMS[row['team']])
    games={}
    for official in pool['games']:
        matches=[game for game,teams in game_teams.items() if teams=={official['home'],official['away']} and all(stamp(r['start'])==stamp(official['startsAt']) for r in source['predictions'] if str(r['game'])==game)]
        if len(matches)!=1:raise ValueError('No unique source-model game for salary slate')
        games[matches[0]]=official
    selected=[];support=[]
    for original in source['predictions']:
        if str(original['game']) not in games:continue
        row=copy.deepcopy(original);past=audit_helper.prior_history(history[str(row['player'])],origins,row['player'],source['predictionDate'])
        if not past:raise ValueError('No prior observed history for '+row['name'])
        rates=historical_percentages(past);accuracy=[rates[k]['percentage'] for k in ['2P','3P','FT']]
        old=copy.deepcopy(row['model']);new=shotline(old,attempts(old),accuracy)
        if any(new[k]!=old[k] for k in ['MIN','AST','REB','STL','BLK','TOV']):raise ValueError('Non-shooting source model inputs changed')
        omitted=[k for k in ['2P','3P','FT'] if rates[k]['attempted']==0]
        if omitted:support.append(dict(player=row['player'],name=row['name'],priorAppearances=len(past),unsupportedCategories=omitted,sourceAttempts=attempts(old),candidateAttempts=attempts(new)))
        row['model']=new;row['historicalShootingEvidence']=rates
        row['status_asof_capture']=injury['statuses'].get(str(row['player']),'Unknown')
        selected.append(row)
    candidate={**source,'createdAt':decision.isoformat(),'sourceCreatedAt':source['createdAt'],'predictions':selected,'fixtures':[f for f in source['fixtures'] if str(f['id']) in games],'publishApproved':False,'shootingPolicy':'historical-observed-shotline-v1-candidate','sourceSnapshotHash':hashlib.sha256(snapshot_file.read_bytes()).hexdigest(),'sourceModelFingerprint':source['modelFingerprint']}
    # Minutes are unchanged, so the original policy's strictly prior minute errors
    # remain the calibration basis. This candidate never enters that audit cohort.
    audit=json.loads((root/'forward/audit_rows.json').read_text());forecasts,noise=simulate(candidate,audit,10000,seed)
    validator.validate_boxes(forecasts,INDEX,10000)
    # Freeze a paired control with the same injury evidence and calibration.
    # This avoids attributing a later availability refresh to shooting changes.
    control_rows=[copy.deepcopy(r) for r in source['predictions'] if str(r['game']) in games]
    for row in control_rows:row['status_asof_capture']=injury['statuses'].get(str(row['player']),'Unknown')
    control={**source,'createdAt':decision.isoformat(),'predictions':control_rows,'fixtures':candidate['fixtures'],'publishApproved':False}
    control_forecasts,_=simulate(control,audit,10000,seed)
    validator.validate_boxes(control_forecasts,INDEX,10000)
    control_scores={};control_points=[]
    for (game,player),(row,box) in control_forecasts.items():
        values=validator.score(box,INDEX);played=box[:,INDEX['MIN']]>0
        categories=sum(box[:,INDEX[k]]>=10 for k in ['PTS','REB','AST','STL','BLK'])
        bonus=float((1.5*(categories[played]>=2)+3*(categories[played]>=3)).mean()) if played.any() else 0.
        control_points.append(dict(player=str(player),game=str(game),projection=None if row['status_asof_capture']=='Out' else sum(row['model'][k]*w for k,w in DK.items())+bonus,availability=row['status_asof_capture']))
        control_scores[str(player)]=values.tolist()
    completed=datetime.now(timezone.utc)
    if completed>=stamp(pool['locksAt']):raise ValueError('Generation did not finish before first lock')
    candidate['generationStartedAt']=decision.isoformat();candidate['createdAt']=completed.isoformat()
    output.mkdir(parents=True,exist_ok=True)
    summary=[];scores={};basic=[];distributions=[]
    for (game,player),(row,box) in forecasts.items():
        values=validator.score(box,INDEX);played=box[:,INDEX['MIN']]>0
        if not played.any():bonus=0.
        else:
            categories=sum(box[:,INDEX[k]]>=10 for k in ['PTS','REB','AST','STL','BLK'])
            bonus=float((1.5*(categories[played]>=2)+3*(categories[played]>=3)).mean())
        # Recompute the bonus from this candidate's own joint draws, not the
        # incumbent saved bonus. Retain the proprietary point statline as the anchor.
        projection=sum(row['model'][k]*w for k,w in DK.items())+bonus
        row.update(DraftKings=projection,expected_DK_bonus=bonus)
        official=games[str(game)];team=NBA_TEAMS[row['team']];opponent=official['away'] if team==official['home'] else official['home']
        known_out=row['status_asof_capture']=='Out'
        record=dict(id=str(player),name=row['name'],team=team,opponent=opponent,gameId=str(game),minutes=None if known_out else row['model']['MIN'],statline=None if known_out else row['model'],projection=None if known_out else projection,conditionalStatline=row['model'],conditionalProjection=projection,availability=row['status_asof_capture'],availabilityVerified=False)
        basic.append(record);scores[str(player)]=values.tolist();hist,edges=np.histogram(values,bins=24)
        distributions.append({**record,'mean':float(values.mean()),'median':float(np.median(values)),**{'p'+str(q):float(np.percentile(values,q)) for q in [5,10,25,75,90,95]},'probabilityAtLeast':{str(n):float((values>=n).mean()) for n in [20,30,40,50,60,70]},'histogram':[{'count':int(n),'from':float(edges[i]),'to':float(edges[i+1])} for i,n in enumerate(hist)],'simulatedStatMeans':{k:float(box[:,INDEX[k]].mean()) for k in FIELDS}})
        summary.append(dict(player=str(player),game=str(game),name=row['name'],projection=projection,mean=float(values.mean()),p10=float(np.quantile(values,.1)),p90=float(np.quantile(values,.9))))
    candidate['modelFingerprint']=hashlib.sha256(json.dumps({'policy':candidate['shootingPolicy'],'source':candidate['sourceSnapshotHash'],'models':[(r['player'],r['game'],r['model']) for r in selected],'injuryHash':injury['rawSha256'],'auditHash':hashlib.sha256((root/'forward/audit_rows.json').read_bytes()).hexdigest(),'seed':seed},sort_keys=True).encode()).hexdigest()
    provenance=dict(modelHash=candidate['modelFingerprint'],sourceHash=hashlib.sha256((json.dumps(candidate,separators=(',',':'),allow_nan=False)+'\n').encode()).hexdigest(),originalForecastHash=candidate['sourceSnapshotHash'],shootingPolicy=candidate['shootingPolicy'],sourceModel=source['model'],minutesCalibrationPolicy=source['model'],seed=seed,researchOnly=True,injurySource=injury['source'],injuryHash=injury['rawSha256'],salaryPoolHash=hashlib.sha256(pool_file.read_bytes()).hexdigest(),historicalHashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},simulatorHash=hashlib.sha256((root/'src/simulate_slate.py').read_bytes()).hexdigest(),shotlineHash=hashlib.sha256((root/'src/shooting_redistribution.py').read_bytes()).hexdigest())
    base=dict(schemaVersion=1,sport='NBA',scoring='DraftKings',projectionConditionalOnPlaying=True,publishApproved=False,capturedAt=completed.isoformat(),validUntil=pool['locksAt'],provenance=provenance)
    artifacts={'candidate.json':candidate,'paired-control.json':dict(publishApproved=False,createdAt=completed.isoformat(),sourceSnapshotHash=candidate['sourceSnapshotHash'],injuryHash=injury['rawSha256'],draws=10000,seed=seed,players=control_points,scores=control_scores,notes='Original shooting policy with the same later injury statuses; a newly frozen prospective control, separate from the original saved source.'),'basic.json':dict(base,kind='projections',players=basic),'distributions.json':dict(base,kind='distributions',players=distributions,draws=10000),'joint.json':dict(base,kind='joint',players=basic,draws=10000,joint=True,modelHash=candidate['modelFingerprint'],scores=scores)}
    for name,value in artifacts.items():(output/name).write_text(json.dumps(value,separators=(',',':'),allow_nan=False)+'\n')
    report=dict(publishApproved=False,generatedAt=completed.isoformat(),locksAt=pool['locksAt'],games=len(games),players=len(basic),drawsPerPlayer=10000,seed=seed,policy=candidate['shootingPolicy'],structuralChecksPassed=True,observedZeroAttemptGuards=support,availabilityCounts=dict(collections.Counter(r['status_asof_capture'] for r in selected)),pendingTeamReports=injury.get('pending_teams',[]),minutesNoise=noise,
        limitations=['A new prospective research candidate, not an approved release or a retrospective accuracy claim.','Shooting accuracy is exact observed makes/attempts from strictly earlier dates.','The recovered shotline function suppresses attempts in categories without observed attempts; this is a research assumption, not proof that a player cannot attempt that shot.','All minutes, non-shooting statistics, existing usage/opportunity model and preseason weighting remain unchanged.','Current injury statuses are used where explicitly matched; unlisted players are not asserted active. Known Out players have null playable projections; their source conditional statlines remain explicitly separate.','A paired control uses the original shooting policy with identical injury evidence and calibration; shared seeds do not imply identical latent draws after distribution changes.','Unmodeled salary players, model review, rotation validation and final availability remain release blockers.'])
    (output/'run-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['generatedAt','games','players','drawsPerPlayer','structuralChecksPassed','availabilityCounts','pendingTeamReports','publishApproved']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ['model-dir','snapshot','salary-pool','injury-evidence','output']:p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--seed',type=int,default=20261115);a=p.parse_args();run(a.model_dir.resolve(),a.snapshot.resolve(),a.salary_pool.resolve(),a.injury_evidence.resolve(),a.output.resolve(),a.seed)
