import copy,hashlib,importlib.util,json,pathlib,tempfile,unittest
spec=importlib.util.spec_from_file_location('grading',pathlib.Path(__file__).with_name('grade-nba-candidate.py'))
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)


class CandidateGradeTests(unittest.TestCase):
    def fixture(self,root):
        rows=[dict(id=str(i),gameId='game',projection=20 if i==1 else None,minutes=30 if i==1 else None) for i in [1,2]]
        candidate={'predictions':[dict(game='game',start='2026-11-15T23:00Z')]}
        write=lambda name,value:(root/name).write_text(json.dumps(value)+'\n')
        write('candidate.json',candidate)
        joint=dict(sport='NBA',scoring='DraftKings',publishApproved=False,draws=10000,joint=True,capturedAt='2026-11-15T18:20Z',players=rows,scores={'1':[20]*10000,'2':[0]*10000},provenance=dict(sourceHash=hashlib.sha256((root/'candidate.json').read_bytes()).hexdigest(),originalForecastHash='original',injuryHash='injury',seed=1))
        control=dict(publishApproved=False,draws=10000,createdAt='2026-11-15T18:20Z',sourceSnapshotHash='original',injuryHash='injury',seed=1,players=[dict(player='1',projection=15),dict(player='2',projection=None)],scores={'1':[15]*10000,'2':[0]*10000})
        for name,value in [('joint.json',joint),('paired-control.json',control),('basic.json',{}),('distributions.json',{}),('run-report.json',{})]:write(name,value)
        write('SHA256.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()})
        box=dict(MIN=30,PTS=10,FGM=5,FGA=10,FG3M=0,FG3A=0,FTM=0,FTA=0,REB=0,AST=0,STL=0,BLK=0,TOV=0)
        return dict(sport='NBA',scoring='DraftKings',source='https://cdn.nba.com/official/results',capturedAt='2026-11-16T04:00Z',games=[dict(gameId='game',status='final',source='https://cdn.nba.com/official/box',rawSha256='a'*64,verifiedAt='2026-11-16T03:00Z')],players=[dict(id='1',gameId='game',identityVerified=True,sourcePlayerId='official1',status='played',statline=box),dict(id='2',gameId='game',identityVerified=True,sourcePlayerId='official2',status='DNP',statline={k:0 for k in box})])

    def test_paired_grade_separates_played_and_explicit_dnp(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);actuals=self.fixture(root);r=g.grade(root,actuals)
            self.assertTrue(r['complete']);self.assertEqual(r['allExplicitResults']['n'],2)
            self.assertEqual(r['playedOnly']['candidate']['pointAbsoluteError'],10)
            self.assertEqual(r['playedOnly']['pairedMeanMAEDifference'],5)
            self.assertIsNone(r['dnpOnly']['candidate']['pointAbsoluteError'])
            self.assertIsNone(r['dnpProbabilityCalibration']);self.assertFalse(r['publishApproved'])

    def test_missing_actual_never_becomes_zero_or_complete(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);actuals=self.fixture(root);actuals['players'].pop();r=g.grade(root,actuals)
            self.assertFalse(r['complete']);self.assertEqual(r['allExplicitResults']['n'],1);self.assertEqual(r['dnpOnly']['n'],0);self.assertEqual(len(r['missing']),1)

    def test_mutated_archive_rejects_before_grading(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);actuals=self.fixture(root);(root/'joint.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):g.grade(root,actuals)

    def test_finality_timing_identity_duplicates_and_source_reject(self):
        changes=[lambda a:a['games'][0].update(status='live'),lambda a:a['games'][0].update(verifiedAt='2026-11-15T22:00Z'),lambda a:a.update(source='https://nba.com.evil.test/box'),lambda a:a['players'][0].update(identityVerified=False),lambda a:a['players'].append(copy.deepcopy(a['players'][0])),lambda a:a['players'][1]['statline'].update(MIN=1),lambda a:a['players'][0]['statline'].update(PTS=11)]
        for change in changes:
            with tempfile.TemporaryDirectory() as d:
                root=pathlib.Path(d);actuals=self.fixture(root);change(actuals)
                with self.assertRaises(ValueError):g.grade(root,actuals)

    def test_scoring_bonuses_and_negative_fantasy_scores(self):
        box=dict(MIN=30,PTS=20,FGM=10,FGA=20,FG3M=0,FG3A=0,FTM=0,FTA=0,REB=10,AST=10,STL=0,BLK=0,TOV=4)
        self.assertEqual(g.score_box(box),50)
        box={k:0 for k in box};box.update(MIN=.1,TOV=2)
        self.assertEqual(g.score_box(box),-1)

    def test_duplicate_official_identity_cannot_inflate_matched_cohort(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);actuals=self.fixture(root);actuals['players'][1]['sourcePlayerId']='official1'
            with self.assertRaisesRegex(ValueError,'multiple model identities'):g.grade(root,actuals)


if __name__=='__main__':unittest.main()
