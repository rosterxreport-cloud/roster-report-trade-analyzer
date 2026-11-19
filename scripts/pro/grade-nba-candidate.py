"""Grade an immutable NBA candidate/control pair; missing results never become zeroes."""
import argparse, hashlib, importlib.util, json, math
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import numpy as np


def stamp(value):
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.utcoffset() is None:
        raise ValueError('Evidence timestamps require a timezone')
    return date


def official(url):
    parsed = urlparse(url)
    return parsed.scheme == 'https' and (parsed.hostname == 'nba.com' or (parsed.hostname or '').endswith('.nba.com')) and not parsed.username and not parsed.password


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def score_box(box):
    keys = ['MIN', 'PTS', 'FGM', 'FGA', 'FG3M', 'FG3A', 'FTM', 'FTA', 'REB', 'AST', 'STL', 'BLK', 'TOV']
    if any(not finite(box.get(k)) or box[k] < 0 for k in keys):
        raise ValueError('Final observed box score is incomplete or invalid')
    if any(box[a] > box[b] for a, b in [('FGM','FGA'),('FG3M','FG3A'),('FG3M','FGM'),('FG3A','FGA'),('FTM','FTA')]):
        raise ValueError('Observed makes/attempts are inconsistent')
    if any(box[k] != int(box[k]) for k in keys if k != 'MIN') or box['PTS'] != 2*box['FGM']+box['FG3M']+box['FTM']:
        raise ValueError('Observed counting stats / point identity failed')
    categories = sum(box[k] >= 10 for k in ['PTS','REB','AST','STL','BLK'])
    return sum(box[k]*w for k,w in {'PTS':1,'FG3M':.5,'REB':1.25,'AST':1.5,'STL':2,'BLK':2,'TOV':-.5}.items())+1.5*(categories>=2)+3*(categories>=3)


def verify_bundle(root):
    manifest = json.loads((root/'SHA256.json').read_text())
    names = ['candidate.json','basic.json','distributions.json','joint.json','paired-control.json','run-report.json']
    for name in names:
        if manifest.get(name) != hashlib.sha256((root/name).read_bytes()).hexdigest():
            raise ValueError('Frozen bundle hash mismatch: '+name)
    values = {name:json.loads((root/name).read_text()) for name in names}
    joint, control, candidate = (values[k] for k in ['joint.json','paired-control.json','candidate.json'])
    if joint.get('publishApproved') is not False or control.get('publishApproved') is not False or joint.get('draws') != 10000 or control.get('draws') != 10000:
        raise ValueError('A frozen 10,000-draw research pair is required')
    if joint.get('scoring') != 'DraftKings' or joint.get('sport') != 'NBA' or not joint.get('joint'):
        raise ValueError('Unexpected simulation scoring or sport')
    if joint['provenance']['sourceHash'] != manifest['candidate.json'] or joint['provenance']['originalForecastHash'] != control['sourceSnapshotHash'] or joint['provenance']['injuryHash'] != control['injuryHash'] or joint['provenance']['seed'] != control['seed']:
        raise ValueError('Candidate and control evidence do not match')
    starts = {str(r['game']):stamp(r['start']) for r in candidate['predictions']}
    if not starts or stamp(joint['capturedAt']) >= min(starts.values()) or stamp(control['createdAt']) >= min(starts.values()):
        raise ValueError('Research pair was not frozen before first lock')
    rows = joint['players']; ids = [r['id'] for r in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(control['scores']) or set(ids) != set(joint['scores']):
        raise ValueError('Research pair player coverage differs')
    for artifact in [joint,control]:
        for scores in artifact['scores'].values():
            if len(scores) != 10000 or any(not finite(x) for x in scores):
                raise ValueError('Invalid joint score vector')
    return values, manifest, starts


def grade(root, actuals):
    values, hashes, starts = verify_bundle(root)
    joint, control = values['joint.json'], values['paired-control.json']
    if actuals.get('sport') != 'NBA' or actuals.get('scoring') != 'DraftKings' or not official(actuals.get('source','')):
        raise ValueError('Dated official NBA results are required')
    captured = stamp(actuals['capturedAt'])
    games = {}
    for game in actuals['games']:
        gid = str(game['gameId'])
        if gid in games or gid not in starts or game.get('status') != 'final' or not official(game.get('source','')) or len(game.get('rawSha256','')) != 64 or any(c not in '0123456789abcdef' for c in game['rawSha256']):
            raise ValueError('Invalid, duplicate, non-final or unmatched game evidence')
        # Finality is a source fact, never inferred from elapsed wall-clock time.
        if captured < stamp(game['verifiedAt']) or stamp(game['verifiedAt']) <= starts[gid]:
            raise ValueError('Final result evidence predates game start or capture')
        games[gid] = game
    observed = {}; source_identities = set()
    for row in actuals['players']:
        identity = (str(row['gameId']),str(row['id']))
        if identity in observed or row.get('identityVerified') is not True or not row.get('sourcePlayerId'):
            raise ValueError('Duplicate or unverified player crosswalk')
        source_identity = (identity[0],str(row['sourcePlayerId']))
        if source_identity in source_identities:
            raise ValueError('Official player is mapped to multiple model identities')
        source_identities.add(source_identity)
        if identity[0] not in games or row.get('status') not in ['played','DNP']:
            raise ValueError('Player result lacks a verified final game')
        points = score_box(row['statline'])
        if (row['status']=='DNP' and any(row['statline'].values())) or (row['status']=='played' and row['statline']['MIN']<=0):
            raise ValueError('Played/DNP status conflicts with observed statistics')
        observed[identity] = (row,points)
    spec = importlib.util.spec_from_file_location('simulation_metrics',Path(__file__).with_name('validate-simulations.py'))
    metrics = importlib.util.module_from_spec(spec);spec.loader.exec_module(metrics)
    control_points = {r['player']:r['projection'] for r in control['players']}
    details=[];missing=[]
    for row in joint['players']:
        key=(str(row['gameId']),row['id']);actual=observed.get(key)
        if actual is None:
            missing.append({'id':row['id'],'gameId':row['gameId'],'reason':'No explicit final player result; not assumed zero'});continue
        result,points=actual;candidate=np.array(joint['scores'][row['id']]);incumbent=np.array(control['scores'][row['id']])
        item={'id':row['id'],'gameId':row['gameId'],'status':result['status'],'actual':points,'minutesActual':result['statline']['MIN']}
        for label,draws,point in [('candidate',candidate,row['projection']),('control',incumbent,control_points[row['id']])]:
            p10,p90=np.quantile(draws,[.1,.9]);item[label]={'meanAbsoluteError':float(abs(draws.mean()-points)),'bias':float(draws.mean()-points),'crps':metrics.crps(draws,points),'inside80':bool(p10<=points<=p90),'pointAbsoluteError':abs(point-points) if finite(point) and result['status']=='played' else None}
        item['minutesAbsoluteError']=abs(row['minutes']-result['statline']['MIN']) if finite(row['minutes']) and result['status']=='played' else None
        details.append(item)
    def aggregate(rows):
        if not rows:return {'n':0}
        mean=lambda array:float(np.mean(array)) if array else None
        summary={'n':len(rows),'games':len({r['gameId'] for r in rows})}
        for label in ['candidate','control']:
            summary[label]={k:mean([r[label][k] for r in rows if r[label][k] is not None]) for k in ['meanAbsoluteError','bias','crps','inside80','pointAbsoluteError']}
        summary['pairedMeanMAEDifference']=mean([r['candidate']['meanAbsoluteError']-r['control']['meanAbsoluteError'] for r in rows])
        summary['minutesMAE']=mean([r['minutesAbsoluteError'] for r in rows if r['minutesAbsoluteError'] is not None])
        return summary
    complete=not missing and set(games)==set(starts)
    return {'publishApproved':False,'complete':complete,'status':'final-research-grade' if complete else 'partial-do-not-claim-complete-validation','frozenAt':joint['capturedAt'],'actualsCapturedAt':actuals['capturedAt'],'frozenHashes':hashes,'actualsHash':hashlib.sha256(json.dumps(actuals,sort_keys=True).encode()).hexdigest(),'allExplicitResults':aggregate(details),'playedOnly':aggregate([r for r in details if r['status']=='played']),'dnpOnly':aggregate([r for r in details if r['status']=='DNP']),'dnpProbabilityCalibration':None,'missing':missing,'details':details,'limitations':['Research score validation only; no salaries, eligible lineup replay, payouts or profitability are established.','Finality and explicit DNP come from source evidence. Missing player records are excluded, never imputed as zero.','Point MAE uses played appearances; all-outcome simulation MAE/coverage includes explicit DNP.','The original frozen bundle does not retain per-draw participation flags; zero fantasy scores are not assumed to mean DNP. DNP probability calibration and conditional-on-playing simulation MAE remain unavailable.','Negative paired mean MAE difference favors the candidate on this sample; one slate does not establish improvement.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--actuals',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=grade(a.bundle,json.loads(a.actuals.read_text()));a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps({k:result[k] for k in ['status','allExplicitResults','playedOnly','dnpOnly']},indent=2))
