"""Compare the instrumented model with the inspected upstream implementation."""
import argparse, copy, importlib.util, json, subprocess, types
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
BASE='7c66e8e854d639d8e8b29014eebee07da8e1da45'
ap=argparse.ArgumentParser();ap.add_argument('--reference',type=Path);args=ap.parse_args()
source=args.reference.read_text() if args.reference else subprocess.check_output(['git','show',BASE+':scripts/refresh-live-player-data.py'],cwd=ROOT,text=True)
original=types.ModuleType('reference');exec(compile(source,'reference','exec'),original.__dict__)
spec=importlib.util.spec_from_file_location('instrumented',ROOT/'scripts/refresh-live-player-data.py');current=importlib.util.module_from_spec(spec);spec.loader.exec_module(current)
players=json.loads((ROOT/'players.json').read_text());ev=json.loads((ROOT/'data/player-evidence.json').read_text());baseline=json.loads((ROOT/'data/live-refresh-baseline.json').read_text());injuries=json.loads((ROOT/'injury-adjustments.json').read_text())['players']
rows=[];snaps=[]
for e in ev['players'].values():
 games=[w for w in e['weekly'] if not w.get('statsMissing')]
 if not games:continue
 row={'player_id':e['id'],'player_display_name':e['name'],'position':e['position'],'games':len(games)}
 for c in games[0]:
  if c not in {'week','statsMissing'}:row[c]=sum(float(w.get(c) or 0) for w in games)
 rows.append(row);snaps.append({'name_key':current.namekey(e['name']),'offense_snaps':len(games)*40,'offense_pct':.6})
f=pd.DataFrame(rows);sn=pd.DataFrame(snaps)
kickers={p['team']:p['name'] for p in players['half'] if p['pos']=='K'}
kvals={tm:{'score':50,'value':10} for tm in kickers};dvals={tm:{'score':50,'value':10} for tm in current.TEAMS.values()}
for scoring in current.FORMATS:
 audit={}
 assert original.live_scores(f.copy(),scoring)==current.live_scores(f.copy(),scoring,audit)
 assert audit['signals'];assert any(not m['observed'] for r in audit['signals'].values() for m in r['metrics'].values())
 missing_audit={};current.live_scores(f.drop(columns=['passing_epa','rushing_epa','receiving_epa'],errors='ignore'),scoring,missing_audit)
 for r in missing_audit['signals'].values():
  for metric,m in r['metrics'].items():
   if 'epa' in metric:assert not m['observed'] and m['input'] is None
 for current_week in [2,3,7]:
  before=copy.deepcopy(players[scoring]);audit={}
  common=(scoring,kickers,kvals,dvals,f.copy(),sn.copy(),False,baseline,injuries,current_week)
  a=original.update(copy.deepcopy(before),*common);b=current.update(copy.deepcopy(before),*common,evidence=audit)
  assert a==b,(scoring,current_week,'model outputs changed')
  assert before==players[scoring],'source records mutated'
  assert audit['calculations']
print('Exact model parity: 3 scoring formats × 3 season stages; neutral inputs remain marked unobserved.')
