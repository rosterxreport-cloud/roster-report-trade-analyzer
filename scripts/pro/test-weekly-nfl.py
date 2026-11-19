import datetime,importlib.util,pathlib,unittest
root=pathlib.Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('weekly',root/'scripts/pro/create-weekly-nfl.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class CalendarTests(unittest.TestCase):
 def setUp(self):self.original=(root/'scripts/projection_week10_league_v4.py').read_text()
 def test_original_week_is_byte_identical(self):self.assertEqual(m.bind_calendar(self.original,2026,10,14),self.original)
 def test_next_week_moves_only_named_calendar_bindings(self):
  s=m.bind_calendar(self.original,2026,11,15);compile(s,'next-week','exec')
  self.assertIn('w.week.between(1,10)',s);self.assertIn('snaps.week.between(8,10)',s)
  self.assertIn('last["week"]=11',s);self.assertIn('Team.nunique()==30',s)
  self.assertIn('profile["sample_games"]>=9',s)
  self.assertIn('alpha=.45',s);self.assertIn('factor=float(np.clip(1+.15*(ratio-1),.925,1.075))',s)
 def test_unreviewed_template_is_rejected(self):
  with self.assertRaises(ValueError):m.bind_calendar(self.original+'\n',2026,11,15)
 def test_invalid_schedule_rejected(self):
  with self.assertRaises(ValueError):m.bind_calendar(self.original,2026,11,0)
class PublicationGateTests(unittest.TestCase):
 def pacific(self,stamp):return datetime.datetime.fromisoformat(stamp)
 def test_delayed_tuesday_job_still_publishes(self):
  self.assertTrue(m.publication_allowed('schedule',self.pacific('2026-11-17T14:42:00-08:00')))
 def test_summer_and_winter_start_at_eight_pacific(self):
  for stamp in ['2026-11-17T08:00:00-08:00','2026-09-08T08:00:00-07:00']:
   self.assertTrue(m.publication_allowed('schedule',self.pacific(stamp)))
  self.assertFalse(m.publication_allowed('schedule',self.pacific('2026-11-17T07:30:00-08:00')))
 def test_late_day_does_not_silently_pass_as_success(self):
  with self.assertRaisesRegex(ValueError,'missed Tuesday'):
   m.publication_allowed('schedule',self.pacific('2026-11-18T00:01:00-08:00'))
 def test_only_explicit_recovery_push_publishes(self):
  self.assertFalse(m.publication_allowed('push',recovery=False))
  self.assertTrue(m.publication_allowed('push',recovery=True))
  self.assertFalse(m.publication_allowed('pull_request',recovery=True))
  self.assertTrue(m.publication_allowed('workflow_dispatch'))
if __name__=='__main__':unittest.main()
