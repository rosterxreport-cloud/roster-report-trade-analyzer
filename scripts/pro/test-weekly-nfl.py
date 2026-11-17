import importlib.util,pathlib,unittest
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
if __name__=='__main__':unittest.main()
