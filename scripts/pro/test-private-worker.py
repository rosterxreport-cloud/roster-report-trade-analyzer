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
if __name__=='__main__':unittest.main()
