"""Regression checks for new-player membership and stable model priors."""
import copy, importlib.util, json, unittest
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('refresh',ROOT/'scripts/refresh-live-player-data.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class AdmissionTests(unittest.TestCase):
 def setUp(self):
  self.db=json.loads((ROOT/'players.json').read_text())
  # Tests retain a fixed incumbent universe even after live additions publish.
  self.base=json.loads((ROOT/'data/live-refresh-baseline.json').read_text())
  self.rows=[p for p in self.db['half'] if p['name'] in self.base['half'] or p['pos'] in {'K','DST'}]
  self.stats=pd.DataFrame([
   dict(player_display_name='New '+pos,player_id=pos,position=pos,recent_team='PIT',games=6,years_exp=0,
        fantasy_points=60,fantasy_points_ppr=90,carries=30 if pos=='RB' else 0,targets=30,receptions=25,
        rushing_yards=150 if pos=='RB' else 0,receiving_yards=300,receiving_tds=2)
   for pos in ['RB','WR','TE']])
  self.snaps=pd.DataFrame([dict(name_key=m.namekey(r.player_display_name),offense_snaps=200,offense_pct=.7) for _,r in self.stats.iterrows()])
  self.k={p['team']:p['name'] for p in self.rows if p['pos']=='K'}
  self.kv={t:{'score':50,'value':10} for t in self.k}
  self.dv={t:{'score':50,'value':10} for t in m.TEAMS.values()}
 def run_model(self,rows=None,injuries=None,audit=None):
  return m.update(copy.deepcopy(self.rows if rows is None else rows),'half',self.k,self.kv,self.dv,self.stats,self.snaps,False,self.base,injuries or {},8,audit)
 def test_all_positions_enter_and_compete_without_aw_grades(self):
  audit={};out=self.run_model(audit=audit)
  for pos in ['RB','WR','TE']:
   p=next(p for p in out if p['name']=='New '+pos)
   self.assertLessEqual(p['rank'],250);self.assertIsNone(p['awRank']);self.assertTrue(p['rookie'])
   self.assertIn(p['name'],audit['calculations']);self.assertIn(p['name'],audit['admissions'])
  self.assertEqual(sum(p['rank']<=250 for p in out),250)
  self.assertEqual(len({p['name'] for p in out}),len(out))
 def test_fringe_and_unmatched_roles_cannot_enter(self):
  self.snaps.loc[:,'offense_snaps']=99
  self.assertFalse(any(p['name'] in {'New RB','New WR','New TE'} for p in self.run_model()))
  self.snaps.loc[:,'offense_snaps']=200;self.stats.loc[:,'targets']=1;self.stats.loc[:,'carries']=0
  self.assertFalse(any(p['name'] in {'New RB','New WR','New TE'} for p in self.run_model()))
 def test_refresh_is_idempotent_and_keeps_admitted_injured_players(self):
  first=self.run_model();second=self.run_model(first)
  for pos in ['RB','WR','TE']:
   a=next(p for p in first if p['name']=='New '+pos);b=next(p for p in second if p['name']==a['name'])
   self.assertEqual(a,b)
  self.snaps.loc[:,'offense_snaps']=0
  injured=self.run_model(first,{'New WR':{'availability':0,'workload':0,'longTermRisk':.1}})
  p=next(p for p in injured if p['name']=='New WR');self.assertEqual(p['value'],0)
  self.assertEqual(sum(p['rank']<=250 for p in injured),250)
 def test_source_records_and_baseline_are_unchanged(self):
  before=copy.deepcopy(self.rows);base=copy.deepcopy(self.base);self.run_model()
  self.assertEqual(self.rows,before);self.assertEqual(self.base,base)
 def test_source_suffix_aliases_preserve_immutable_player_identities(self):
  canonical=next(p for p in self.rows if p['name']=='James Cook III')
  row=self.stats.iloc[0].copy();row['player_display_name']='James Cook';row['position']='RB'
  self.stats=pd.concat([self.stats,pd.DataFrame([row])],ignore_index=True)
  self.snaps=pd.concat([self.snaps,pd.DataFrame([dict(name_key=m.namekey('James Cook'),offense_snaps=200,offense_pct=.7)])],ignore_index=True)
  out=self.run_model();names={p['name'] for p in out}
  self.assertIn(canonical['name'],names);self.assertNotIn('James Cook',names)
  self.assertTrue(set(self.base['half'])<=names)
if __name__=='__main__':unittest.main()
