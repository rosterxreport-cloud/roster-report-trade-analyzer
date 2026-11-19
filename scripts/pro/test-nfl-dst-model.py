import copy,importlib.util,pathlib,unittest
import pandas as pd
spec=importlib.util.spec_from_file_location('dst',pathlib.Path(__file__).with_name('nfl-dst-model.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class DSTTests(unittest.TestCase):
 def play(self,**changes):
  row=dict(game_id='qa',play_id=1,season_type='REG',season=2026,week=1,home_team='AAA',away_team='BBB',posteam='AAA',defteam='BBB',total_home_score=0,total_away_score=0,play_type='pass',sack=0,interception=0,safety=0,touchdown=0)
  row.update(changes);return row
 def records(self,*plays):return {r['Team']:r for r in m.ledger(pd.DataFrame(plays),1)[0]}
 def test_pick_six_excluded_but_extra_point_counts(self):
  a=self.play(interception=1,touchdown=1,td_team='BBB',return_touchdown=1,total_away_score=6)
  b=self.play(play_id=2,posteam='BBB',defteam='AAA',play_type='extra_point',extra_point_attempt=1,extra_point_result='good',total_away_score=7)
  r=self.records(a,b);self.assertEqual(r['AAA']['Points_Allowed'],1);self.assertEqual(r['BBB']['Interceptions'],1);self.assertEqual(r['BBB']['Interception_Return_TD'],1)
 def test_kick_return_counts_against_dst(self):
  r=self.records(self.play(play_type='kickoff',touchdown=1,td_team='AAA',return_touchdown=1,total_home_score=6))
  self.assertEqual(r['AAA']['Return_TD'],1);self.assertEqual(r['BBB']['Points_Allowed'],6)
 def test_conversion_return_and_blocked_pat_score_once(self):
  r=self.records(self.play(play_type='extra_point',extra_point_attempt=1,extra_point_result='blocked',defensive_two_point_conv=1,defensive_extra_point_conv=1,total_away_score=2))
  self.assertEqual(r['BBB']['Blocked_Kicks'],1);self.assertEqual(r['BBB']['Conversion_Returns'],1);self.assertEqual(r['AAA']['Points_Allowed'],2)
 def test_penalty_safety_is_not_lost_with_no_play(self):
  r=self.records(self.play(play_type='no_play',safety=1,total_away_score=2))
  self.assertEqual(r['BBB']['Safeties'],1);self.assertEqual(r['AAA']['Points_Allowed'],0)
 def test_two_recoveries_including_offense_recovers_defensive_fumble(self):
  r=self.records(self.play(fumbled_1_team='AAA',fumble_recovery_1_team='BBB',fumbled_2_team='BBB',fumble_recovery_2_team='AAA'))
  self.assertEqual(r['AAA']['Fumble_Recoveries'],1);self.assertEqual(r['BBB']['Fumble_Recoveries'],1)
 def test_duplicate_or_unreconciled_score_rejects(self):
  with self.assertRaises(ValueError):self.records(self.play(),self.play())
  with self.assertRaises(ValueError):self.records(self.play(total_home_score=3))
 def test_prior_cutoff_probabilities_and_whole_row_dependence(self):
  rows=[]
  for team,opp in [('AAA','BBB'),('CCC','DDD')]:
   for week in range(1,5):
    r=dict(Team=team,Opponent=opp,season=2026,week=week,Points_Allowed=0 if week%2 else 35,**{k:0 for k in m.WEIGHTS});r['Sacks']=10 if week%2 else 0;r['DraftKings']=m.score(r);rows.append(r)
  a=m.forecast(rows,'AAA','DDD',2026,5);future=copy.deepcopy(rows[0]);future.update(week=5,DraftKings=9999)
  self.assertEqual(a,m.forecast(rows+[future],'AAA','DDD',2026,5));self.assertEqual(set(a['scores']),{-4,20});self.assertAlmostEqual(sum(a['modeledInputs']['Points_Allowed_Probabilities'].values()),1);self.assertFalse(a['publishApproved'])
 def test_points_allowed_boundaries(self):
  for pa,score in [(0,10),(1,7),(6,7),(7,4),(13,4),(14,1),(20,1),(21,0),(27,0),(28,-1),(34,-1),(35,-4)]:self.assertEqual(m.score(dict(Points_Allowed=pa,**{k:0 for k in m.WEIGHTS})),score)
if __name__=='__main__':unittest.main()
