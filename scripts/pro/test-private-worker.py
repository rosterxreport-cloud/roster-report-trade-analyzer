import importlib.util,json,os,pathlib,tempfile,unittest
from unittest.mock import patch
with patch.dict(os.environ,{'DFS_PUBLISH_URL':'https://synthetic.example','DFS_PUBLISH_TOKEN':'synthetic-private-key'}):
 spec=importlib.util.spec_from_file_location('worker',pathlib.Path(__file__).with_name('run-private-dfs.py'));worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
class IndependenceTests(unittest.TestCase):
 def test_nba_failure_does_not_prevent_nfl_source_update(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory)/'model';(root/'forward').mkdir(parents=True);calls=[]
   def run(args,**kwargs):
    calls.append(args)
    if 'capture-current-salaries' in args[1]:
     sport=args[2];target=pathlib.Path(args[3]);target.mkdir()
     (target/'salary-pool.json').write_text(json.dumps({'draftGroupId':'1','players':[],'locksAt':'2026-11-22T18:00:00Z'}))
     return type('R',(),{'returncode':0,'stdout':'{}','stderr':''})()
    return type('R',(),{'returncode':0,'stdout':'{"state":"published"}','stderr':''})()
   with patch.object(worker,'ROOT',root),patch.object(worker.shutil,'copytree',side_effect=RuntimeError('Synthetic NBA source failure')),patch.object(worker.subprocess,'run',side_effect=run):
    result=worker.execute()
   self.assertEqual(result['nba']['state'],'failed');self.assertEqual(result['slates']['NFL']['state'],'published')
   self.assertTrue(any('assemble-nfl-slate' in args[1] for args in calls))
class SlateDateTests(unittest.TestCase):
 def test_next_slate_after_evening_lock_uses_next_game_date(self):
  now=worker.datetime.datetime(2026,11,17,2,tzinfo=worker.datetime.timezone.utc)
  pool={'players':[{'startsAt':'2026-11-17T00:00:00Z'},{'startsAt':'2026-11-18T00:30:00Z'}]}
  self.assertEqual(worker.nba_slate_date(pool,now).isoformat(),'2026-11-17')
 def test_utc_midnight_preserves_eastern_game_date(self):
  now=worker.datetime.datetime(2026,11,16,20,tzinfo=worker.datetime.timezone.utc)
  self.assertEqual(worker.nba_slate_date({'players':[{'startsAt':'2026-11-17T01:00:00Z'}]},now).isoformat(),'2026-11-16')
 def test_locked_salary_pool_is_not_relabelled_as_current(self):
  now=worker.datetime.datetime(2026,11,17,2,tzinfo=worker.datetime.timezone.utc)
  with self.assertRaises(ValueError):worker.nba_slate_date({'players':[{'startsAt':'2026-11-17T00:00:00Z'}],'locksAt':'2026-11-17T00:00:00Z'},now)
if __name__=='__main__':unittest.main()
