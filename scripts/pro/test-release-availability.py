import importlib.util,pathlib,unittest
s=importlib.util.spec_from_file_location('a',pathlib.Path(__file__).with_name('nba-release-availability.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class ReleaseTests(unittest.TestCase):
 def test_out_players_excluded_without_changing_remaining_forecasts(self):
  players=[{'name':'Kawhi Leonard','team':'TOR','projection':40},{'name':'Jusuf Nurkić','team':'UTA','projection':33},{'name':'Synthetic','team':'TOR','projection':12}]
  a={'players':players};report={k:'synthetic' for k in ['source','reportAsOf','capturedAt','sha256','gameDate']};report['teams']={'TOR':{'submitted':True,'players':[{'name':'Kawhi Leonard','status':'Out'}]},'UTA':{'submitted':True,'players':[{'name':'Jusuf Nurkic','status':'Out'}]}}
  result=m.apply(a,report);self.assertEqual([p['name'] for p in result['players']],['Synthetic']);self.assertEqual(result['players'][0]['projection'],12);self.assertEqual(len(a['players']),3)
 def test_missing_team_report_is_not_active(self):
  report={k:'synthetic' for k in ['source','reportAsOf','capturedAt','sha256','gameDate']};report['teams']={}
  result=m.apply({'players':[{'name':'Synthetic','team':'TOR'}]},report);self.assertEqual(result['players'][0]['status'],'unverified')
if __name__=='__main__':unittest.main()
