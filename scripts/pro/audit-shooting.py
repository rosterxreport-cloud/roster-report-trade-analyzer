"""Paired retrospective historical-shooting challenger; never changes saved forecasts."""
import argparse, collections, hashlib, json, sys
from datetime import date, timedelta
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec


def load_policy(root):
    spec=spec_from_file_location('rr_historical_shooting',root/'src/shooting_policy.py')
    module=module_from_spec(spec);spec.loader.exec_module(module)
    return module.apply_historical_shooting


def prior_history(rows, origins, player, cutoff):
    """Use calendar dates, excluding the target day and all later observations."""
    return [{k:v for k,v in row.items() if k not in ('player','season')}
            for row in rows if str(row['player'])==str(player)
            and (date.fromisoformat(origins[str(row['season'])])+timedelta(days=row['period'])<date.fromisoformat(cutoff)
                 if str(row['season']) in origins else date(int(row['season']),7,1)<date.fromisoformat(cutoff))]


def audit(root):
    sys.path.insert(0,str(root/'src'))
    from model import YAHOO, points
    apply=load_policy(root)
    origins=json.loads((root/'data/period_origins.json').read_text())['origins']
    paths=sorted((root/'data').glob('observed_archive_*.json'))+[root/'data/live_observed_games.json']
    observations={}
    for path in paths:
        for row in json.loads(path.read_text())['games']:
            key=(str(row['season']),str(row['game']),str(row['player']))
            if key in observations and any(observations[key][field]!=row[field] for field in ['FGM','FGA','FG3M','FG3A','FTM','FTA']):
                raise ValueError('Conflicting observed shooting counts')
            observations[key]=row
    by_player=collections.defaultdict(list)
    for row in observations.values():by_player[str(row['player'])].append(row)
    source=root/'forward/audit_rows.json';groups=collections.defaultdict(lambda:dict(errors=[],missing=0))
    for row in json.loads(source.read_text()):
        if row['actual']['MIN']<=0 or row['model']['MIN']<=0:continue
        group=groups[row['modelVersion']]
        history=prior_history(by_player[str(row['player'])],origins,row['player'],row['date'])
        challenger=apply(row['model'],history)
        if challenger is None:group['missing']+=1;continue
        if any(challenger[k]!=row['model'][k] for k in ['MIN','FGA','FG3A','FTA','AST','REB','STL','BLK','TOV']):
            raise ValueError('Challenger changed non-shooting inputs')
        actual=points(row['actual'],YAHOO)
        group['errors'].append((points(row['model'],YAHOO)-actual,points(challenger,YAHOO)-actual))
    mean=lambda values:sum(values)/len(values) if values else None
    result={}
    for policy,g in groups.items():
        errors=g['errors'];old=mean([abs(a) for a,b in errors]);new=mean([abs(b) for a,b in errors])
        result[policy]=dict(paired_n=len(errors),missing_history=g['missing'],incumbent_yahoo_mae=old,
            historical_shooting_yahoo_mae=new,mae_change=None if old is None else new-old,
            historical_shooting_bias=mean([b for a,b in errors]))
    return dict(publishApproved=False,sourceAuditHash=hashlib.sha256(source.read_bytes()).hexdigest(),
        sourceHashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},policies=result,
        limitations=['Retrospective paired sensitivity analysis, not a frozen prospective challenger test.',
                    'Observed history is filtered strictly before each target calendar date; source snapshots were recovered later.',
                    'Minutes, opportunity volumes, counting stats and preseason weighting are unchanged.',
                    'DraftKings is omitted: changing shooting changes double-double probabilities; archived incumbent bonuses cannot validate challenger bonuses.',
                    'Missing shooting history is excluded and reported; no generic shooting percentages are substituted.'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=audit(args.model_dir.resolve());args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
