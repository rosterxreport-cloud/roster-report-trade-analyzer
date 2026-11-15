import copy,importlib.util,pathlib,unittest
spec=importlib.util.spec_from_file_location('events',pathlib.Path(__file__).with_name('nfl-event-candidate.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class EventsTests(unittest.TestCase):
 def fixture(self):
  row=dict(Position='QB',Pass_Att=20,Pass_Yds=250,Pass_TD=2,INT=1,Rush_Att=2,Rush_Yds=10,Rush_TD=0,Targets=0,Receptions=0,Rec_Yds=0,Rec_TD=0)
  prior=[]
  for week,yards in enumerate([100,200,300,400],1):
   r={k:0 for k in m.EVENTS};r.update(season=2026,season_type='REG',week=week,attempts=20,carries=2,targets=0,receptions=0,passing_yards=yards,rushing_yards=10,receiving_yards=0);prior.append(r)
  return row,prior
 def test_prior_only_ignores_target_and_future_outcomes(self):
  row,prior=self.fixture();a=m.extend(row,prior,2026,5);future=copy.deepcopy(prior[0]);future.update(week=5,passing_yards=9999);b=m.extend(row,prior+[future],2026,5);self.assertEqual(a,b);self.assertEqual(a['throughWeek'],4)
 def test_threshold_probability_is_not_threshold_of_mean(self):
  row,prior=self.fixture();r=m.extend(row,prior,2026,5);self.assertEqual(r['events']['Pass_300_Probability'],.5);self.assertFalse(r['publishApproved']);self.assertEqual(row['Pass_Yds'],250)
 def test_missing_history_events_and_unsupported_usage_reject(self):
  row,prior=self.fixture()
  with self.assertRaises(ValueError):m.extend(row,prior[:3],2026,5)
  del prior[0]['fumbles_lost_total']
  with self.assertRaises(ValueError):m.extend(row,prior,2026,5)
  row,prior=self.fixture();row['Targets']=1
  with self.assertRaises(ValueError):m.extend(row,prior,2026,5)
 def test_fumbles_and_two_point_events_follow_observed_opportunity(self):
  row,prior=self.fixture();prior[0]['fumbles_lost_total']=1;prior[0]['passing_2pt_conversions']=1;r=m.extend(row,prior,2026,5);self.assertAlmostEqual(r['events']['Fumbles_Lost'],.25);self.assertAlmostEqual(r['events']['Two_Point_Conversions'],.25)
if __name__=='__main__':unittest.main()
