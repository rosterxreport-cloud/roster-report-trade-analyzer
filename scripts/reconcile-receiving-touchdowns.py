#!/usr/bin/env python3
"""Reconcile WR/TE/RB receiving TDs to each team's projected passing-TD environment.

Allocation blends prior target share, prior TD-per-target, current projected targets,
and starter status. This lets vacated scoring opportunity move to current starters
without simply multiplying every receiver's historical TD rate.
"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

GAMES=17.0


def num(v,d=0.0):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except: return d


def points(r,rec):
    x=lambda k:num(r.get(k),0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv')); ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv')); ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv')); a=ap.parse_args()
    s=pd.read_csv(a.stats); r=pd.read_csv(a.roles)
    rolecols=[c for c in ['name','position','team_2026','rec_td_per_target','target_share','depth_starter','depth_rank'] if c in r.columns]
    rr=r[rolecols].rename(columns={'team_2026':'role_team'})
    m=s.merge(rr,on=['name','position'],how='left',suffixes=('','_role'))
    eligible=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    m['td_allocation_share']=np.nan
    for team,g in m[eligible & m.position.isin(['RB','WR','TE'])].groupby('team'):
        q=m[eligible & m.position.eq('QB') & m.team.eq(team)].copy()
        if q.empty: continue
        team_td=pd.to_numeric(q.projected_passing_tds,errors='coerce').max()
        if not np.isfinite(team_td) or team_td<=0: continue
        idx=g.index
        targets=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0)
        hist_rate=pd.to_numeric(m.loc[idx,'rec_td_per_target'],errors='coerce').fillna(.035).clip(.012,.11)
        starter=m.loc[idx,'depth_starter'].fillna(False).astype(bool)
        # Volume dominates; scoring skill and current starter role refine the allocation.
        w=targets.pow(.82)*hist_rate.pow(.38)*np.where(starter,1.10,1.0)
        w=pd.Series(w,index=idx).replace([np.inf,-np.inf],np.nan).fillna(0)
        if w.sum()<=0: continue
        share=w/w.sum()
        # Reserve a small fraction for untracked/lineman/backup scores.
        alloc_total=team_td*.94
        new_td=alloc_total*share
        # Avoid extreme single-season outcomes from a purely allocative layer.
        new_td=new_td.clip(lower=0,upper=14)
        m.loc[idx,'projected_receiving_tds']=new_td
        m.loc[idx,'td_allocation_share']=share
    for idx,row in m[eligible].iterrows():
        d=m.loc[idx].to_dict(); m.at[idx,'ppr_points']=points(d,1); m.at[idx,'half_ppr_points']=points(d,.5); m.at[idx,'standard_points']=points(d,0); m.at[idx,'ppr_per_game']=m.at[idx,'ppr_points']/GAMES; m.at[idx,'half_ppr_per_game']=m.at[idx,'half_ppr_points']/GAMES; m.at[idx,'standard_per_game']=m.at[idx,'standard_points']/GAMES
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        m[fmt.replace('_points','_overall_rank')]=m[fmt].rank(method='min',ascending=False); pc=fmt.replace('_points','_pos_rank'); m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fmt].notna(); m.loc[mask,pc]=m.loc[mask,fmt].rank(method='min',ascending=False)
    m=m.drop(columns=[c for c in ['role_team','rec_td_per_target','target_share','depth_starter','depth_rank'] if c in m.columns],errors='ignore')
    nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(a.out,index=False)
    watch=m[m.name.isin(['Emeka Egbuka','Justin Jefferson','Ladd McConkey','Jameson Williams'])]
    print(watch[['name','projected_targets','projected_receiving_tds','td_allocation_share','ppr_points','ppr_pos_rank']].sort_values('ppr_pos_rank').to_dict('records'))
    print(f'Wrote TD-reconciled projections to {a.out}')

if __name__=='__main__': main()
