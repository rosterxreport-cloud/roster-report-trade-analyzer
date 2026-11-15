import importlib.util,pathlib,unittest,tempfile,json
from unittest.mock import patch
import pandas as pd
spec=importlib.util.spec_from_file_location('validation',pathlib.Path(__file__).with_name('validate-nfl-archive.py'))
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
class NFLArchiveTests(unittest.TestCase):
    def run_fixture(self,predictions,captured='2026-11-08T09:00:00Z'):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory);forecast=root/'forecast.csv';actual=root/'actual.parquet';schedule=root/'schedule.csv'
            pd.DataFrame(predictions).to_csv(forecast,index=False);actual.write_bytes(b'synthetic fixture')
            pd.DataFrame([dict(season=2026,week=9,game_type='REG',gameday='2026-11-08',gametime='13:00',game_id='qa',home_team='AAA',away_team='BBB')]).to_csv(schedule,index=False)
            observations=pd.DataFrame([dict(season=2026,week=9,season_type='REG',player_display_name='QA Player',team='AAA',opponent_team='BBB',position='QB',game_id='qa',fantasy_points_ppr=15.)])
            with patch.object(v.pd,'read_parquet',return_value=observations):return v.run(forecast,actual,schedule,2026,9,captured)
    def row(self,name='QA Player'):return dict(Player=name,Team='AAA',Opponent='BBB',Position='QB',PPR=20.)
    def test_missing_actual_never_assumes_zero(self):
        result=self.run_fixture([self.row(),self.row('Missing')]);self.assertEqual(result['metrics']['n'],1);self.assertEqual(result['metrics']['mae'],5.);self.assertEqual(len(result['excluded']),1);self.assertFalse(result['publishApproved'])
    def test_forecast_at_or_after_kickoff_excluded(self):
        result=self.run_fixture([self.row()],'2026-11-08T18:00:00Z');self.assertEqual(result['metrics']['n'],0)
    def test_duplicate_identity_and_naive_capture_rejected(self):
        with self.assertRaises(ValueError):self.run_fixture([self.row(),self.row()])
        with self.assertRaises(ValueError):self.run_fixture([self.row()],'2026-11-08T09:00:00')
if __name__=='__main__':unittest.main()
