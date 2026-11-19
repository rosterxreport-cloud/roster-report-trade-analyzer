import importlib.util,pathlib,unittest
import numpy as np
spec=importlib.util.spec_from_file_location('validation',pathlib.Path(__file__).with_name('validate-simulations.py'))
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
INDEX={key:i for i,key in enumerate(['MIN','FGA','FG3A','FTA','FGM','FG3M','FTM','PTS','REB','AST','STL','BLK','TOV'])}
class SimulationValidationTests(unittest.TestCase):
    def fixture(self):
        result={}
        for team in [1,2]:
            for player in range(5):
                box=np.zeros((2,len(INDEX)));box[:,INDEX['MIN']]=48;box[:,INDEX['FGA']]=10;box[:,INDEX['FGM']]=5;box[:,INDEX['PTS']]=10
                result[('game',str(team)+'-'+str(player))]=({'team':team},box)
        return result
    def test_draftkings_scores_both_bonuses_once(self):
        box=np.zeros((1,len(INDEX)))
        for k,val in {'PTS':20,'REB':10,'AST':10,'FG3M':2,'TOV':4}.items():box[:,INDEX[k]]=val
        self.assertEqual(v.score(box,INDEX)[0],51.)
        box[:,INDEX['AST']]=9;self.assertEqual(v.score(box,INDEX)[0],46.5)
    def test_crps_matches_pairwise_definition_and_point_mass(self):
        a=np.array([0.,2.,4.]);actual=3.
        expected=np.abs(a-actual).mean()-.5*np.abs(a[:,None]-a[None,:]).mean()
        self.assertAlmostEqual(v.crps(a,actual),expected)
        self.assertEqual(v.crps(np.array([2.,2.]),5),3.)
    def test_valid_joint_boxes_and_float_tolerance(self):
        fixture=self.fixture();fixture['game','1-0'][1][:,INDEX['MIN']]+=1e-12
        self.assertEqual(v.validate_boxes(fixture,INDEX,2),1)
    def test_impossible_points_attempts_team_and_player_minutes_reject(self):
        for key,value in [('PTS',11),('FG3A',11),('MIN',49)]:
            fixture=self.fixture();fixture['game','1-0'][1][:,INDEX[key]]=value
            with self.assertRaises(ValueError):v.validate_boxes(fixture,INDEX,2)
        fixture=self.fixture();fixture['game','1-0'][1][:,INDEX['MIN']]=49;fixture['game','1-1'][1][:,INDEX['MIN']]=47
        with self.assertRaisesRegex(ValueError,'Player exceeds'):v.validate_boxes(fixture,INDEX,2)
if __name__=='__main__':unittest.main()
