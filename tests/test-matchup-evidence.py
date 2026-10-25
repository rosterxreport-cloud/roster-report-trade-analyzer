"""Replayable synthetic fixtures test aggregation, ranks and pregame role assignment."""
import importlib.util, unittest
from pathlib import Path
import pandas as pd

spec = importlib.util.spec_from_file_location('matchups', Path(__file__).resolve().parents[1] / 'scripts/build-matchup-evidence.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fixture():
    rows = []
    for defense in range(32):
        for week in range(1, 5):
            for pos in ['QB', 'RB', 'WR', 'TE']:
                row = dict.fromkeys(m.FIELDS, 0.)
                row.update(player_id=f'{defense}-{pos}', position=pos, team=f'T{defense}', opponent_team=f'D{defense}', season=2026, season_type='REG', week=week, game_id=f'{defense}-{week}')
                row.update(targets=4., receptions=2., receiving_yards=20., fantasy_points_ppr=float(defense))
                rows.append(row)
    return pd.DataFrame(rows)

class Matchups(unittest.TestCase):
    def test_totals_game_denominators_and_tied_ranks(self):
        rows = fixture()
        # A second RB is production in the same game, not another defensive game.
        extra = rows[(rows.position == 'RB') & (rows.opponent_team == 'D0')].copy()
        extra.player_id = 'extra-rb'
        extra.fantasy_points_ppr = 1.
        result = m.build(pd.concat([rows, extra]), 2026, 4, 'a'*64, 'stamp')
        rb = result['positions']['RB']['D0']
        self.assertEqual(rb['games'], 4)
        self.assertEqual(rb['perGame']['fantasy_points_ppr'], 1.)
        self.assertEqual(rb['mostPointsRank'], result['positions']['RB']['D1']['mostPointsRank'])
        self.assertEqual(result['positions']['RB']['D31']['mostPointsRank'], 1)

    def test_leader_uses_prior_weeks_and_excludes_ties_and_week_one(self):
        rows = fixture()
        extra = rows[(rows.position == 'WR') & (rows.team == 'T0')].copy()
        extra.player_id = 'new-leader'
        extra.targets = [0., 0., 30., 1.]
        extra.receiving_yards = [0., 0., 300., 40.]
        extra.fantasy_points_ppr = [0., 0., 40., 5.]
        result = m.build(pd.concat([rows, extra]), 2026, 4, 'a'*64, 'stamp')
        lead = result['leadingWR']['D0']
        self.assertEqual(lead['games'], 3)
        # Week 3's breakout cannot retrospectively make the player its pregame leader.
        self.assertAlmostEqual(lead['perGame']['receiving_yards'], 80/3, places=5)
        self.assertEqual(result['currentLeaders']['T0'], 'new-leader')
        tied = pd.concat([rows, rows[(rows.position == 'WR') & (rows.team == 'T0')].assign(player_id='tied')])
        self.assertNotIn('T0', m.leaders(tied))

    def test_future_games_cannot_leak_and_invalid_sources_fail(self):
        rows = fixture()
        future = rows[rows.week == 4].copy()
        future.week = 5
        future.fantasy_points_ppr = 99999.
        a = m.build(rows, 2026, 4, 'a'*64, 'stamp')
        b = m.build(pd.concat([rows, future]), 2026, 4, 'a'*64, 'stamp')
        self.assertEqual(a, b)
        for invalid in [pd.concat([rows, rows.iloc[[0]]]), rows[rows.week != 2], rows.assign(targets=float('nan'))]:
            with self.assertRaises(ValueError):
                m.build(invalid, 2026, 4, 'a'*64, 'stamp')

if __name__ == '__main__':
    unittest.main()
