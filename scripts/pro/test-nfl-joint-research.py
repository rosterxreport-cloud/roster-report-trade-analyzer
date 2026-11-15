import copy,hashlib,importlib.util,json,pathlib,tempfile,unittest
import numpy as np
import pandas as pd
spec=importlib.util.spec_from_file_location('joint',pathlib.Path(__file__).with_name('nfl-joint-research.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class JointTests(unittest.TestCase):
 def fixture(self):
  players=[]
  for team in ['AAA','BBB']:
   for position in ['QB','WR','RB']:
    r={k:0. for k in m.FEATURES+['Targets','Receptions','Rec_Yds','Rec_TD','Rush_Yds','PPR']};r.update(id=team+position,Team=team,Position=position,week=2)
    if position=='QB':r.update(Pass_Att=20,Pass_Yds=200,Pass_TD=1,INT=1)
    if position=='WR':r.update(Targets=10,Receptions=6,Rec_Yds=100,Rec_TD=1)
    if position=='RB':r.update(Rush_Att=10,Rush_Yds=50,Rush_TD=1)
    players.append(r)
  base=dict(game_id='qa',season=2026,season_type='REG',week=1,home_team='AAA',away_team='BBB',posteam='AAA',defteam='BBB',play_type='pass',pass_attempt=1,complete_pass=0,yards_gained=0,passer_player_id='sourceQBA',receiver_player_id='sourceWRA')
  plays=[dict(base,play_id=1,complete_pass=1,touchdown=1,pass_touchdown=1,td_team='AAA',yards_gained=50,total_home_score=6,total_away_score=0),dict(base,play_id=2,posteam='BBB',defteam='AAA',passer_player_id='sourceQBB',interception=1,touchdown=1,return_touchdown=1,td_team='AAA',total_home_score=12,total_away_score=0),dict(base,play_id=3,sack=1,fumble=1,fumbled_1_team='AAA',fumbled_1_player_id='sourceQBA',fumble_recovery_1_team='BBB',touchdown=1,return_touchdown=1,td_team='BBB',total_home_score=12,total_away_score=6)]
  frame=pd.DataFrame([dict(p,game_id='qa'+str(i)) for i in range(20) for p in plays]);return players,m.templates(frame,2026,2),frame
 def test_event_identities_and_repeatability(self):
  players,pool,_=self.fixture();r=m.simulate(pool,players,['AAA','BBB'],256,7);again=m.simulate(pool,players,['AAA','BBB'],256,7)
  self.assertTrue(np.array_equal(r['scores'],again['scores']));self.assertEqual(r['scores'].shape,(256,6));self.assertTrue(all(v for k,v in r['checks'].items() if k!='draws'));self.assertTrue(np.isfinite(r['dstScores']).all())
 def test_corrupted_interception_sack_and_fumble_events_reject(self):
  players,pool,_=self.fixture();r=m.simulate(pool,players,['AAA','BBB'],128,7)
  for key in ['Interceptions','Sacks','Fumble_Recoveries']:
   dst=copy.deepcopy(r['dstEvents']);dst[key][0,0]+=1
   with self.assertRaises(ValueError):m.validate(r['box'],players,['AAA','BBB'],dst,r['unmodeled'])
 def test_passing_receiving_identity_and_opportunities_reject(self):
  players,pool,_=self.fixture();r=m.simulate(pool,players,['AAA','BBB'],128,7)
  for field in ['Pass_Yds','Pass_TD','Receptions']:
   box=r['box'].copy();box[0,0,m.FIELDS.index(field)]+=100
   with self.assertRaises(ValueError):m.validate(box,players,['AAA','BBB'],r['dstEvents'],r['unmodeled'])
 def test_target_and_future_templates_cannot_enter_simulation(self):
  players,pool,_=self.fixture();pool[0]['week']=2
  with self.assertRaises(ValueError):m.simulate(pool,players,['AAA','BBB'],128)
 def test_source_forecasts_unchanged_and_invalid_inputs_reject(self):
  players,pool,_=self.fixture();original=copy.deepcopy(players);m.simulate(pool,players,['AAA','BBB'],128);self.assertEqual(players,original)
  for change in [lambda p:p[0].update(Pass_Att=-1),lambda p:p[0].update(id=p[1]['id']),lambda p:p[1].update(Receptions=11)]:
   test=copy.deepcopy(players);change(test)
   with self.assertRaises(ValueError):m.simulate(pool,test,['AAA','BBB'],128)
 def test_density_backoff_prevents_weight_collapse(self):
  players,pool,_=self.fixture();r=m.simulate(pool,players,['AAA','BBB'],512,7);r['box'][:]=0
  for value in r['dstEvents'].values():value[:]=0
  for value in r['unmodeled'].values():value[:]=0
  r['box'][:5,0,m.FIELDS.index('Pass_Att')]=5;r['box'][:5,0,m.FIELDS.index('INT')]=5;r['dstEvents']['Interceptions'][:5,1]=5;r['scores']=m.dk(r['box'])
  target=copy.deepcopy(players)
  for p in target:
   for field in m.FIELDS:p[field]=0.
  target[0].update(Pass_Att=1,INT=1)
  _,diagnostic=m.align_moments(r,target,['AAA','BBB'],42)
  self.assertLess(diagnostic['temperature'],1);self.assertGreaterEqual(diagnostic['effectiveDraws'],200-1e-6)
 def test_draftkings_bonuses_are_per_player_not_team(self):
  box=np.zeros((1,2,len(m.FIELDS)));box[:,:,m.FIELDS.index('Pass_Yds')]=200
  self.assertEqual(m.dk(box).tolist(),[[8,8]])
  box[0,0,m.FIELDS.index('Pass_Yds')]=300;box[0,0,m.FIELDS.index('Rush_Yds')]=100;box[0,0,m.FIELDS.index('Rec_Yds')]=100
  self.assertEqual(m.dk(box)[0,0],41)
 def test_future_play_by_play_is_excluded_before_template_construction(self):
  _,pool,frame=self.fixture();future=frame.copy();future['week']=2;future['game_id']='future';future['yards_gained']=9999
  again=m.templates(pd.concat([frame,future],ignore_index=True),2026,2)
  self.assertEqual(len(pool),len(again));self.assertTrue(np.array_equal(np.array([r['features'] for r in pool]),np.array([r['features'] for r in again])))
 def test_whole_outcome_moment_alignment_preserves_events_and_source(self):
  players,pool,_=self.fixture();r=m.simulate(pool,players,['AAA','BBB'],512,7)
  targets=copy.deepcopy(players)
  for i,p in enumerate(targets):
   for field in m.FIELDS:p[field]=float(r['box'][:,i,m.FIELDS.index(field)].mean())
  targets[1]['Rec_TD']+=1;original=copy.deepcopy(targets)
  aligned,diagnostic=m.align_moments(r,targets,['AAA','BBB'],42)
  self.assertTrue(diagnostic['accepted']);self.assertGreaterEqual(diagnostic['effectiveDraws'],200);self.assertTrue(diagnostic['receiverTDTargetChanges']);self.assertEqual(targets,original)
  self.assertEqual(aligned['checks']['draws'],512);self.assertTrue(np.allclose(aligned['scores'],m.dk(aligned['box'])))
 def artifact(self,root):
  players,pool,_=self.fixture();r=m.simulate(pool,players,['AAA','BBB'],128,7);name='1234567890abcdef.npz'
  arrays=dict(box=r['box'],scores=r['scores'],player_ids=np.array([p['id'] for p in players]),player_teams=np.array([p['Team'] for p in players]),teams=np.array(['AAA','BBB']),dst_scores=r['dstScores'],**{'dst_'+k:v for k,v in r['dstEvents'].items()},**{'unmodeled_'+k:v for k,v in r['unmodeled'].items()},**{'scoring_'+k:v for k,v in r['scoringEvents'].items()})
  np.savez_compressed(root/name,**arrays)
  summaries=[dict(id=p['id'],team=p['Team'],mean=float(r['scores'][:,i].mean()),median=float(np.median(r['scores'][:,i])),p10=float(np.quantile(r['scores'][:,i],.1)),p90=float(np.quantile(r['scores'][:,i],.9)),meanStats=dict(zip(m.FIELDS,r['box'][:,i,:].mean(axis=0).tolist()))) for i,p in enumerate(players)]
  report=dict(publishApproved=False,kind='joint-research',sport='NFL',scoring='DraftKings',joint=True,draws=128,players=summaries,gameChecks=[dict(game='synthetic-qa',teams=['AAA','BBB'],drawArtifact=name,drawArtifactHash=hashlib.sha256((root/name).read_bytes()).hexdigest())],scores={**{p['id']:r['scores'][:,i].tolist() for i,p in enumerate(players)},**{'DST:'+t:r['dstScores'][:,i].tolist() for i,t in enumerate(['AAA','BBB'])}})
  (root/'joint-research.json').write_text(json.dumps(report));return arrays,report,name
 def test_saved_artifacts_verify_and_hash_or_summary_tampering_rejects(self):
  validator=m.helper('validate-nfl-joint')
  for mode in ['valid','bytes','scores','summary','approval']:
   with tempfile.TemporaryDirectory() as directory:
    root=pathlib.Path(directory);arrays,report,name=self.artifact(root)
    if mode=='bytes':(root/name).write_bytes((root/name).read_bytes()+b'tamper')
    if mode=='scores':report['scores']['AAAQB'][0]+=1
    if mode=='summary':report['players'][0]['meanStats']['INT']+=1
    if mode=='approval':report['publishApproved']=True
    (root/'joint-research.json').write_text(json.dumps(report))
    if mode=='valid':self.assertEqual(validator.verify(root,128)['scoreVectors'],8)
    else:
     with self.assertRaises(ValueError):validator.verify(root,128)
 def test_physical_tampering_rejects_even_with_recomputed_file_hash(self):
  validator=m.helper('validate-nfl-joint')
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);arrays,report,name=self.artifact(root);arrays['dst_Interceptions'][0,0]+=1;np.savez_compressed(root/name,**arrays);report['gameChecks'][0]['drawArtifactHash']=hashlib.sha256((root/name).read_bytes()).hexdigest();(root/'joint-research.json').write_text(json.dumps(report))
   with self.assertRaises(ValueError):validator.verify(root,128)
if __name__=='__main__':unittest.main()
