import unittest,tempfile,pathlib,json,hashlib,copy
from datetime import datetime,timezone
from nba_release import authorize
class ReleaseTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);(self.root/'src').mkdir()
  files={}
  for name in ['simulate_slate.py','draftkings_audit.py','model.py']:
   (self.root/'src'/name).write_text('# synthetic release fixture\n');files[name]=hashlib.sha256((self.root/'src'/name).read_bytes()).hexdigest()
  self.policy=self.root/'policy.json';self.policy.write_text(json.dumps(dict(approved=True,sport='NBA',model='incumbent',modelFingerprint='frozen',featureWeightsSha256='weights',sourceFiles=files,authorization='synthetic test')))
  self.snapshot=dict(model='incumbent',modelFingerprint='frozen',featureWeightsSha256='weights',createdAt='2026-11-16T19:00:00Z',fixtures=[{'start':'2026-11-17T00:00:00Z'}],publishApproved=False)
  self.now=datetime(2026,11,16,20,tzinfo=timezone.utc)
 def tearDown(self):self.temp.cleanup()
 def test_delegated_authorization_preserves_original_snapshot(self):
  before=copy.deepcopy(self.snapshot);receipt=authorize(self.root,self.snapshot,self.policy,self.now)
  self.assertEqual(before,self.snapshot);self.assertFalse(receipt['sourcePublishApproved']);self.assertEqual(len(receipt['policyHash']),64)
 def test_experimental_policy_cannot_inherit_incumbent_approval(self):
  self.snapshot['modelFingerprint']='experimental'
  with self.assertRaises(ValueError):authorize(self.root,self.snapshot,self.policy,self.now)
 def test_changed_private_source_cannot_inherit_approval(self):
  (self.root/'src/model.py').write_text('# modified fixture\n')
  with self.assertRaises(ValueError):authorize(self.root,self.snapshot,self.policy,self.now)
 def test_approval_cannot_revive_locked_source(self):
  with self.assertRaises(ValueError):authorize(self.root,self.snapshot,self.policy,datetime(2026,11,17,1,tzinfo=timezone.utc))
if __name__=='__main__':unittest.main()
