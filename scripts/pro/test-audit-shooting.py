import importlib.util, pathlib, unittest
spec=importlib.util.spec_from_file_location('audit',pathlib.Path(__file__).with_name('audit-shooting.py'))
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
class HistoryTests(unittest.TestCase):
    def test_target_day_future_and_other_players_excluded(self):
        rows=[dict(player='a',season=2027,period=d,FGA=d) for d in [1,2,3]]
        rows.append(dict(player='b',season=2027,period=1,FGA=9))
        result=audit.prior_history(rows,{'2027':'2026-10-19'},'a','2026-10-21')
        self.assertEqual([r['FGA'] for r in result],[1])
        self.assertNotIn('player',result[0]);self.assertNotIn('season',result[0])
    def test_only_completed_unmapped_seasons_accepted(self):
        rows=[dict(player='a',season=y,period=1,FGA=y) for y in [2025,2027,2028]]
        result=audit.prior_history(rows,{},'a','2026-10-21')
        self.assertEqual([r['FGA'] for r in result],[2025])
if __name__=='__main__':unittest.main()
