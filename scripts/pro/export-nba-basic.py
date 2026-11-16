"""Copy existing RR point forecasts for dated preview review, without recalculation."""
import argparse,hashlib,importlib.util,json,math
from pathlib import Path
FIELDS=['MIN','PTS','REB','AST','STL','BLK','TOV','FGA','FG3A','FTA','FGM','FG3M','FTM']
def export(source):
    raw=source.read_bytes();snapshot=json.loads(raw)
    spec=importlib.util.spec_from_file_location('teams',Path(__file__).with_name('pair-salary-research.py'));mapping=importlib.util.module_from_spec(spec);spec.loader.exec_module(mapping)
    games={}
    for r in snapshot['predictions']:games.setdefault(str(r['game']),set()).add(r['team'])
    players=[];seen=set()
    for r in snapshot['predictions']:
        if len(games[str(r['game'])])!=2 or str(r['player']) in seen:raise ValueError('Ambiguous player or game identity')
        seen.add(str(r['player']));stats={k:r['model'][k] for k in FIELDS}
        if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in list(stats.values())+[r['DraftKings']]):raise ValueError('Invalid source statline')
        other=next(t for t in games[str(r['game'])] if t!=r['team'])
        players.append(dict(id=str(r['player']),name=r['name'],team=mapping.NBA_TEAMS[r['team']],opponent=mapping.NBA_TEAMS[other],gameId=str(r['game']),startsAt=r['start'],minutes=stats['MIN'],statline=stats,projection=r['DraftKings'],availability='Unverified'))
    return dict(schemaVersion=1,purpose='existing-model-preview',modelUnchanged=True,capturedAt=snapshot['createdAt'],model=snapshot['model'],sourceHash=hashlib.sha256(raw).hexdigest(),players=players)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=export(a.source);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n');print(json.dumps({'players':len(r['players']),'model':r['model'],'sourceHash':r['sourceHash']}))
