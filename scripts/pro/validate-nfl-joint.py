"""Verify saved NFL research draws against hashes, events, scores and summaries."""
import argparse,hashlib,importlib.util,json,re
from pathlib import Path
import numpy as np

def verify(root,expected_draws=10000):
    report=json.loads((root/'joint-research.json').read_text())
    if report.get('publishApproved') is not False or report.get('kind')!='joint-research' or report.get('sport')!='NFL' or report.get('scoring')!='DraftKings' or report.get('joint') is not True or report.get('draws')!=expected_draws:raise ValueError('Expected explicitly unapproved NFL research artifact')
    spec=importlib.util.spec_from_file_location('joint_validation',Path(__file__).with_name('nfl-joint-research.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    source={p['id']:p for p in report['players']}
    if len(source)!=len(report['players']):raise ValueError('Duplicate summary identity')
    seen=set();seen_games=set()
    for game in report['gameChecks']:
        name=game['drawArtifact']
        if not re.fullmatch(r'[0-9a-f]{16}\.npz',name) or game['game'] in seen_games:raise ValueError('Invalid artifact path or duplicate game')
        seen_games.add(game['game']);path=root/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=game['drawArtifactHash']:raise ValueError('Draw artifact hash mismatch')
        with np.load(path,allow_pickle=False) as data:
            box=data['box'];scores=data['scores'];teams=data['teams'].tolist();ids=data['player_ids'].tolist();player_teams=data['player_teams'].tolist()
            if teams!=game['teams'] or len(teams)!=2 or len(set(teams))!=2 or len(ids)!=len(set(ids)) or box.shape!=(expected_draws,len(ids),len(m.FIELDS)) or scores.shape!=(expected_draws,len(ids)):raise ValueError('Invalid game dimensions/identities')
            players=[dict(id=pid,Team=team) for pid,team in zip(ids,player_teams)]
            if any(p['Team'] not in teams for p in players):raise ValueError('Player outside game teams')
            dst={k:data['dst_'+k] for k in list(m.helper('nfl-dst-model').WEIGHTS)+['Points_Allowed']};unmodeled={k:data['unmodeled_'+k] for k in ['Fumbles_Lost','Return_TD','Offensive_Fumble_Recovery_TD']};scoring={k:data['scoring_'+k] for k in ['FieldGoalsMade','ExtraPointsMade','TwoPointScores']}
            for values in list(dst.values())+list(unmodeled.values())+list(scoring.values()):
                if values.shape!=(expected_draws,2) or not np.isfinite(values).all() or (values<0).any() or not np.equal(values,np.floor(values)).all():raise ValueError('Invalid team scoring events')
            m.validate(box,players,teams,dst,unmodeled,scoring)
            if not np.array_equal(m.dk(box),scores):raise ValueError('Player fantasy scoring mismatch')
            weights=m.helper('nfl-dst-model').WEIGHTS;pa=dst['Points_Allowed'];band=np.select([pa==0,pa<=6,pa<=13,pa<=20,pa<=27,pa<=34],[10,7,4,1,0,-1],default=-4)
            dst_scores=sum(dst[k]*w for k,w in weights.items())+band
            if not np.array_equal(dst_scores,data['dst_scores']):raise ValueError('DST fantasy scoring mismatch')
            for i,pid in enumerate(ids):
                if pid in seen or pid not in source:raise ValueError('Duplicate or missing player summary')
                seen.add(pid);summary=source[pid]
                if summary['team']!=player_teams[i] or not np.array_equal(scores[:,i],np.array(report['scores'][pid])):raise ValueError('Player score vector/identity mismatch')
                if any(not np.isclose(box[:,i,j].mean(),summary['meanStats'][key],rtol=0,atol=1e-9) for j,key in enumerate(m.FIELDS)):raise ValueError('Stat summary mismatch')
                for field,value in [('mean',scores[:,i].mean()),('median',np.median(scores[:,i])),('p10',np.quantile(scores[:,i],.1)),('p90',np.quantile(scores[:,i],.9))]:
                    if not np.isclose(summary[field],value,rtol=0,atol=1e-9):raise ValueError('Distribution summary mismatch')
            for side,team in enumerate(teams):
                pid='DST:'+team
                if pid in seen or not np.array_equal(dst_scores[:,side],np.array(report['scores'][pid])):raise ValueError('DST vector/identity mismatch')
                seen.add(pid)
    if seen!=set(report['scores']) or set(source)!=(seen-{pid for pid in seen if pid.startswith('DST:')}):raise ValueError('Unmatched or absent score vectors')
    return dict(publishApproved=False,verified=True,games=len(seen_games),offensivePlayers=len(source),scoreVectors=len(seen),draws=expected_draws,reportHash=hashlib.sha256((root/'joint-research.json').read_bytes()).hexdigest())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);a=p.parse_args();print(json.dumps(verify(a.directory),indent=2))
