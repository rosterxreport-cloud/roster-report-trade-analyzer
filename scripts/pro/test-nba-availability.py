import importlib.util,pathlib,unittest
spec=importlib.util.spec_from_file_location('availability',pathlib.Path(__file__).with_name('nba-availability.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class AvailabilityTests(unittest.TestCase):
 def test_team_and_status_survive_page_column_shifts(self):
  text='11/16/2026   07:00 (ET)   CHI@CLE   Chicago Bulls   One, Synthetic   Out   Injury/Illness\n       Cleveland Cavaliers   Two, Synthetic   Questionable   Injury/Illness\n'
  teams=module.parse(text,'2026-11-16');self.assertEqual(teams['CHI']['players'][0],{'name':'Synthetic One','status':'Out'});self.assertEqual(teams['CLE']['players'][0]['status'],'Questionable')
 def test_not_submitted_is_not_active(self):
  teams=module.parse('Chicago Bulls   NOT YET SUBMITTED','2026-11-16');self.assertFalse(teams['CHI']['submitted'])
 def test_next_day_report_cannot_change_todays_eligibility(self):
  teams=module.parse('11/17/2026   Chicago Bulls   One, Synthetic   Out   Injury/Illness','2026-11-16');self.assertEqual(teams,{})
class FutureGameReportTests(unittest.TestCase):
 def test_current_report_contains_distinct_next_day_statuses(self):
  text='11/16/2026   Chicago Bulls   One, Synthetic   Out   Injury/Illness\n11/17/2026   Chicago Bulls   One, Synthetic   Available   Injury/Illness\n'
  self.assertEqual(module.parse(text,'2026-11-16')['CHI']['players'][0]['status'],'Out')
  self.assertEqual(module.parse(text,'2026-11-17')['CHI']['players'][0]['status'],'Available')
 def test_next_day_not_submitted_stays_unverified(self):
  text='11/16/2026   Chicago Bulls   One, Synthetic   Available   Injury/Illness\n11/17/2026   Chicago Bulls   NOT YET SUBMITTED\n'
  self.assertFalse(module.parse(text,'2026-11-17')['CHI']['submitted'])
if __name__=='__main__':unittest.main()