"""Audit recovered RR forecast snapshots without changing model weights or inputs."""
import argparse, collections, hashlib, json, sys
from pathlib import Path
from datetime import datetime


def stamp(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.utcoffset() is None:
        raise ValueError('Naive source timestamp')
    return result


def audit(root):
    sys.path.insert(0,str(root/'src'))
    from model import YAHOO, points
    from draftkings_audit import DK, actual_bonus
    audit_file=root/'forward/audit_rows.json'
    rows=json.loads(audit_file.read_text())
    saved={}
    for file in sorted((root/'forward/predictions').glob('*.json')):
        snapshot=json.loads(file.read_text())
        for row in snapshot['predictions']:
            key=(str(row['game']),str(row['player']))
            if key in saved:
                raise ValueError('Repeated saved forecast identity')
            saved[key]=(snapshot,row)
    groups=collections.defaultdict(list)
    seen=set()
    for row in rows:
        key=(str(row['game']),str(row['player']))
        if key in seen:
            raise ValueError('Repeated audit identity')
        seen.add(key)
        snapshot,prediction=saved[key]
        if snapshot['model']!=row['modelVersion'] or stamp(snapshot['createdAt'])>=stamp(prediction['start']):
            raise ValueError('Model policy mismatch or forecast at/after lock')
        model,actual=row['model'],row['actual']
        if actual['MIN']<=0 or model['MIN']<=0:
            continue
        expected=points(model,YAHOO);observed=points(actual,YAHOO)
        rate_hat=expected/model['MIN'];rate=observed/actual['MIN']
        minutes_component=(model['MIN']-actual['MIN'])*rate_hat
        rate_component=actual['MIN']*(rate_hat-rate)
        if abs(minutes_component+rate_component-(expected-observed))>1e-7:
            raise ValueError('Per-minute error identity failed')
        bonus=prediction.get('expected_DK_bonus')
        dk_error=None if bonus is None else points(model,DK)+bonus-points(actual,DK)-actual_bonus(actual)
        groups[row['modelVersion']].append(dict(date=row['date'],game=row['game'],error=expected-observed,
            minutes_error=model['MIN']-actual['MIN'],minutes_component=minutes_component,rate_component=rate_component,
            dk_error=dk_error,captured=snapshot['createdAt']))
    mean=lambda values:sum(values)/len(values) if values else None
    output={}
    for policy,group in groups.items():
        dk=[r['dk_error'] for r in group if r['dk_error'] is not None]
        output[policy]=dict(n=len(group),dates=len({r['date'] for r in group}),games=len({r['game'] for r in group}),
            first_date=min(r['date'] for r in group),last_date=max(r['date'] for r in group),
            yahoo_mae=mean([abs(r['error']) for r in group]),yahoo_bias=mean([r['error'] for r in group]),
            minutes_mae=mean([abs(r['minutes_error']) for r in group]),minutes_bias=mean([r['minutes_error'] for r in group]),
            minutes_component_mean_absolute=mean([abs(r['minutes_component']) for r in group]),
            rate_component_mean_absolute=mean([abs(r['rate_component']) for r in group]),
            draftkings_paired_n=len(dk),draftkings_mae=mean(list(map(abs,dk))),draftkings_bias=mean(dk),
            meets_existing_review_sample=len({r['game'] for r in group})>=200 and len({r['date'] for r in group})>=14)
    return dict(sourceAuditHash=hashlib.sha256(audit_file.read_bytes()).hexdigest(),policies=output,
        limitations=['Saved paired played rows only; DNP/participation accuracy is not established.',
                    'Policies are evaluated separately; changes in their cohorts prevent a causal comparison.',
                    'Absolute minute and rate contributions do not add to total MAE because signed errors can offset.',
                    'DK rows lacking an archived expected bonus are omitted rather than assigned an invented bonus.',
                    'The sample threshold is an existing research review rule, not a production-accuracy guarantee.'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=audit(args.model_dir.resolve());args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
