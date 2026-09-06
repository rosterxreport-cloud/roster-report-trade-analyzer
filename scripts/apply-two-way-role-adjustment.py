#!/usr/bin/env python3
"""Apply conservative offensive participation ceilings to two-way players.

This exists because defensive depth status cannot be used as offensive role
status. Two-way WRs may still have packages and meaningful touches, but their
season-long target volume must reflect the snap competition created by a major
defensive role.
"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
GAMES=17.0

def num(v,d=np.nan):
    try:
        x=float(v);return x if np.isfinite(x) else d
    except (TypeError,ValueError):return d

def points(r,rec):
    x=lambda k:num(r.get(k),0.0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'));ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'));a=ap.parse_args()
    s=pd.read_csv(a.stats);r=pd.read_csv(a.roles)
    keep=[c for c in ['name','position','two_way_player','offensive_depth_rank','depth_rank','projected_pass_attempts'] if c in r.columns]
    x=s.merge(r[keep],on=['name','position'],how='left',suffixes=('','_role'))
    mask=x['two_way_player'].fillna(False)&x['position'].eq('WR')&x['projection_status'].isin(['rookie_model','modeled_veteran'])
    for i,row in x[mask].iterrows():
        rank=num(row.get('offensive_depth_rank'),num(row.get('depth_rank'),4))
        # Even a nominal WR1 slot does not imply full-time offensive snaps when
        # the player is expected to play the majority of snaps on defense.
        share_cap={1:.10,2:.10,3:.075,4:.05}.get(min(max(int(rank),1),4),.05)
        team_pass=num(row.get('projected_pass_attempts_role'),num(row.get('projected_pass_attempts'),np.nan))
        old=num(row.get('projected_targets'),np.nan)
        if not np.isfinite(team_pass) or not np.isfinite(old) or old<=0:continue
        cap=team_pass*share_cap
        new=min(old,cap)
        ratio=new/old
        x.at[i,'projected_targets']=new
        for c in ['projected_receptions','projected_receiving_yards','projected_receiving_tds']:
            x.at[i,c]=num(row.get(c),0)*ratio
        x.at[i,'role_confidence']=min(num(row.get('role_confidence'),.5),.50)
        x.at[i,'two_way_target_share_cap']=share_cap
    eligible=x['projection_status'].isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i,row in x[eligible].iterrows():
        d=row.to_dict();x.at[i,'ppr_points']=points(d,1);x.at[i,'half_ppr_points']=points(d,.5);x.at[i,'standard_points']=points(d,0)
        x.at[i,'ppr_per_game']=x.at[i,'ppr_points']/GAMES;x.at[i,'half_ppr_per_game']=x.at[i,'half_ppr_points']/GAMES;x.at[i,'standard_per_game']=x.at[i,'standard_points']/GAMES
    for f in ['ppr_points','half_ppr_points','standard_points']:
        x[f.replace('_points','_overall_rank')]=x[f].rank(method='min',ascending=False);pc=f.replace('_points','_pos_rank');x[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            m=x['position'].eq(pos)&x[f].notna();x.loc[m,pc]=x.loc[m,f].rank(method='min',ascending=False)
    hunter=x[x['name'].eq('Travis Hunter')][[c for c in ['name','projected_targets','projected_receptions','projected_receiving_yards','projected_receiving_tds','ppr_points','ppr_pos_rank','two_way_target_share_cap'] if c in x]]
    if len(hunter):print('Hunter adjusted:',hunter.to_dict('records'))
    x=x.drop(columns=[c for c in ['two_way_player','offensive_depth_rank','depth_rank','projected_pass_attempts_role'] if c in x],errors='ignore')
    nums=x.select_dtypes(include=[np.number]).columns;x[nums]=x[nums].round(2);x.to_csv(a.stats,index=False)
    print(f'Two-way WRs adjusted: {int(mask.sum())}')
if __name__=='__main__':main()
