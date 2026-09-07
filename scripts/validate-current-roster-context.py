#!/usr/bin/env python3
"""Validate that projection competition layers are keyed to current 2026 teams."""
from pathlib import Path
import argparse
import pandas as pd
TEAM_ALIASES={'JAX':'JAC','LA':'LAR','STL':'LAR','SD':'LAC','OAK':'LV'}
def team_norm(v):
    if pd.isna(v): return None
    t=str(v).strip().upper()
    if not t or t=='<NA>': return None
    return TEAM_ALIASES.get(t,t)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'))
    a=ap.parse_args()
    s=pd.read_csv(a.stats); r=pd.read_csv(a.roles)
    if 'team' in s: s['team']=s['team'].map(team_norm)
    if 'team_2026' in r: r['team_2026']=r['team_2026'].map(team_norm)
    if 'team_2025' in r: r['team_2025']=r['team_2025'].map(team_norm)
    role_cols=[c for c in ['name','position','team_2026','team_2025','changed_team','depth_rank','depth_starter'] if c in r.columns]
    m=s.merge(r[role_cols],on=['name','position'],how='left',validate='many_to_one')
    eligible=m[m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])].copy()
    if eligible['team_2026'].isna().any():
        bad=eligible[eligible.team_2026.isna()][['name','position','team']].to_dict('records')
        raise SystemExit(f'Projected players missing 2026 role team: {bad[:20]}')
    mismatch=eligible[eligible.team.astype(str).ne(eligible.team_2026.astype(str))]
    if len(mismatch):
        bad=mismatch[['name','position','team','team_2026','team_2025']].to_dict('records')
        raise SystemExit(f'Projection/current-team mismatch: {bad[:30]}')
    wr=eligible[eligible.position.eq('WR')]
    current_rooms={team:set(g.name) for team,g in wr.groupby('team')}
    changed=wr[wr.get('changed_team',False).fillna(False).astype(bool)]
    audits=[]
    for row in changed.itertuples(index=False):
        room=sorted(current_rooms.get(row.team,set())-{row.name})
        audits.append({'name':row.name,'team_2025':getattr(row,'team_2025',None),'team_2026':row.team,'current_wr_peers':room})
    print('Current-team mismatches: 0')
    print('Changed-team WRs audited:',len(changed))
    print('Changed-team current WR rooms:',audits)
if __name__=='__main__': main()
