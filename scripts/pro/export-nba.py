"""Run the recovered PRIVATE RR simulator; export versioned deployment artifacts.
No model source or private bundle is copied into the public repository.
Unapproved sources remain unapproved. This adapter never fabricates projections.
"""
import argparse, hashlib, json, sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np


def run(model_dir, snapshot_path, output, rotation_path=None, seed=20261114):
    sys.path.insert(0, str(model_dir / 'src'))
    from simulate_slate import simulate, INDEX, FIELDS
    from draftkings_audit import DK
    raw = snapshot_path.read_bytes()
    snapshot = json.loads(raw)
    audit_path = model_dir / 'forward/audit_rows.json'
    rotations = None
    if rotation_path:
        from simulation_rotations import build_context, observed_rotation_history
        evidence = json.loads(rotation_path.read_text())
        rotations = build_context(snapshot, observed_rotation_history(model_dir), evidence.get('injury'), evidence.get('expected_starters'))
    forecasts, noise = simulate(snapshot, json.loads(audit_path.read_text()), 10000, seed, rotations)
    model_hash = snapshot.get('modelFingerprint') or hashlib.sha256(raw).hexdigest()
    base = dict(schemaVersion=1, sport='NBA', scoring='DraftKings', publishApproved=snapshot.get('publishApproved') is True,
                capturedAt=snapshot['createdAt'], validUntil=min(f['start'] for f in snapshot['fixtures']),
                provenance=dict(modelHash=model_hash, sourceHash=hashlib.sha256(raw).hexdigest(),
                                auditHash=hashlib.sha256(audit_path.read_bytes()).hexdigest(),
                                model=snapshot['model'], shootingPolicy='Recovered source policy; requires independent historical-percentage release audit',
                                simulatorHash=hashlib.sha256((model_dir/'src/simulate_slate.py').read_bytes()).hexdigest(),
                                seed=seed, researchOnly=True))
    teams=dict(enumerate('ATL BOS NOP CHI CLE DAL DEN DET GSW HOU IND LAC LAL MIA MIL MIN BKN NYK ORL PHI PHX POR SAC SAS OKC UTA WAS TOR MEM CHA'.split(),1))
    basic, distributions, scores = [], [], {}
    for (game, player), (row, box) in forecasts.items():
        if len(box) != 10000 or not np.isfinite(box).all():
            raise ValueError('Invalid joint simulation dimensions')
        categories = sum(box[:, INDEX[k]] >= 10 for k in ('PTS','REB','AST','STL','BLK'))
        fantasy = sum(box[:, INDEX[k]] * weight for k, weight in DK.items()) + 1.5*(categories>=2) + 3*(categories>=3)
        scores[str(player)] = fantasy.tolist()
        record = dict(id=str(player), name=row['name'], team=teams.get(int(row['team']),str(row['team'])), gameId=str(game), opponent=teams.get(row.get('tracking_applied',{}).get('opponent_defense',{}).get('opponent'),'Unavailable'),
                      minutes=row['model']['MIN'], statline=row['model'], projection=row['DraftKings'])
        basic.append(record)
        hist, edges = np.histogram(fantasy, bins=24)
        d = {**record, 'mean':float(fantasy.mean()), 'median':float(np.median(fantasy)),
             **{'p'+str(q):float(np.percentile(fantasy,q)) for q in (5,10,25,75,90,95)},
             'histogram':[dict(count=int(n), **{'from':float(edges[i]),'to':float(edges[i+1])}) for i,n in enumerate(hist)],
             'probabilityAtLeast':{str(n):float((fantasy>=n).mean()) for n in (20,30,40,50,60,70)},
             'simulatedStatMeans':{k:float(box[:, INDEX[k]].mean()) for k in FIELDS}}
        distributions.append(d)
    output.mkdir(parents=True, exist_ok=True)
    for name, artifact in (
        ('basic.json',dict(base,kind='projections',players=basic)),
        ('distributions.json',dict(base,kind='distributions',players=distributions,draws=10000,scoring='DraftKings')),
        ('joint.json',dict(base,kind='joint',players=basic,draws=10000,joint=True,scoring='DraftKings',modelHash=model_hash,scores=scores))):
        (output/name).write_text(json.dumps(artifact,allow_nan=False,separators=(',',':')))
    report = dict(players=len(basic),drawsPerPlayer=10000,seed=seed,sourceApproved=base['publishApproved'],
                  sourceModel=snapshot['model'],minuteNoise=noise,
                  note='Recovered joint model, not a new calibrated simulation or a public release. Source gate preserved.')
    (output/'run-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir',type=Path,required=True)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rotation-evidence',type=Path)
    args=parser.parse_args()
    run(args.model_dir.resolve(),args.snapshot.resolve(),args.output.resolve(),args.rotation_evidence)
