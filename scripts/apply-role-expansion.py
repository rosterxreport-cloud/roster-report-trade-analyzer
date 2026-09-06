#!/usr/bin/env python3
"""Shift receiving opportunity toward young starters whose roles materially expanded.

This is a generic projection-only rule, not a player override. A player qualifies when
he has one season of NFL history, remains on the same team, is a current offensive
starter, and received meaningful vacated-target opportunity. Added targets are taken
from teammates so the existing team target budget is preserved.
"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

GAMES=17.0


def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except (TypeError,ValueError): return d


def points(r,rec):
    x=lambda k:num(r.get(k),0.0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')


def scale_receiving(m,idx,ratio):
    for c in ['projected_targets','projected_receptions','projected_receiving_yards','projected_receiving_tds']:
        if c in m.columns and np.isfinite(num(m.at[idx,c],np.nan)):
            m.at[idx,c]=num(m.at[idx,c],0)*ratio


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv')); ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv')); ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv')); a=ap.parse_args()
    s=pd.read_csv(a.stats); r=pd.read_csv(a.roles)
    cols=[c for c in ['name','position','team_2026','history_season_count','changed_team','depth_starter','depth_rank','vacated_target_share_2026','role_target_share_2026','targets_per_game'] if c in r.columns]
    rr=r[cols].rename(columns={'team_2026':'role_team'})
    m=s.merge(rr,on=['name','position'],how='left',suffixes=('','_role'))
    eligible=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    m['role_expansion_applied']=False; m['role_expansion_multiplier']=1.0

    seasons=pd.to_numeric(m.get('history_season_count'),errors='coerce')
    vac=pd.to_numeric(m.get('vacated_target_share_2026'),errors='coerce').fillna(0)
    starter=m.get('depth_starter',pd.Series(False,index=m.index)).fillna(False).astype(bool)
    changed=m.get('changed_team',pd.Series(False,index=m.index)).fillna(False).astype(bool)
    # One-year players with a confirmed starting role and >=2 points of vacated target share.
    ascending=eligible & m.position.isin(['WR','TE','RB']) & seasons.le(1) & starter & ~changed & vac.ge(.02)

    for team,g in m[eligible & m.position.isin(['WR','TE','RB'])].groupby('team'):
        up=g.index.intersection(m[ascending].index)
        if len(up)==0: continue
        donors=g.index.difference(up)
        if len(donors)==0: continue
        donor_targets=pd.to_numeric(m.loc[donors,'projected_targets'],errors='coerce').fillna(0)
        # Keep at least 70% of every donor's current target projection available to them.
        donor_capacity=donor_targets*.30
        available=float(donor_capacity.sum())
        if available<=0: continue
        requests=[]
        for idx in up:
            old=num(m.at[idx,'projected_targets'],0)
            bonus=num(m.at[idx,'vacated_target_share_2026'],0)
            # 4-10% growth: strength comes from actual vacated share, not player identity.
            mult=float(np.clip(1.04+bonus*.90,1.04,1.10))
            requests.append((idx,old*(mult-1),mult))
        total_req=sum(x[1] for x in requests)
        factor=min(1.0,available/total_req) if total_req>0 else 0
        shifted=0.0
        for idx,req,mult in requests:
            add=req*factor; old=num(m.at[idx,'projected_targets'],0)
            if old<=0 or add<=0: continue
            scale_receiving(m,idx,(old+add)/old)
            m.at[idx,'role_expansion_applied']=True; m.at[idx,'role_expansion_multiplier']=(old+add)/old
            shifted+=add
        if shifted>0:
            weights=donor_capacity/donor_capacity.sum()
            for idx,w in weights.items():
                old=num(m.at[idx,'projected_targets'],0); take=shifted*float(w)
                if old>0: scale_receiving(m,idx,max(0,(old-take)/old))

    for idx,row in m[eligible].iterrows():
        d=m.loc[idx].to_dict(); m.at[idx,'ppr_points']=points(d,1); m.at[idx,'half_ppr_points']=points(d,.5); m.at[idx,'standard_points']=points(d,0); m.at[idx,'ppr_per_game']=m.at[idx,'ppr_points']/GAMES; m.at[idx,'half_ppr_per_game']=m.at[idx,'half_ppr_points']/GAMES; m.at[idx,'standard_per_game']=m.at[idx,'standard_points']/GAMES
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        m[fmt.replace('_points','_overall_rank')]=m[fmt].rank(method='min',ascending=False); pc=fmt.replace('_points','_pos_rank'); m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fmt].notna(); m.loc[mask,pc]=m.loc[mask,fmt].rank(method='min',ascending=False)
    drop=['role_team','history_season_count','changed_team','depth_starter','depth_rank','vacated_target_share_2026','role_target_share_2026','targets_per_game']
    m=m.drop(columns=[c for c in drop if c in m.columns],errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(a.out,index=False)
    watch=m[m.name.isin(['Emeka Egbuka','Justin Jefferson','Ladd McConkey','Jameson Williams'])]
    print(watch[[c for c in ['name','projected_targets','role_expansion_applied','role_expansion_multiplier','ppr_points','ppr_pos_rank'] if c in watch.columns]].sort_values('ppr_pos_rank').to_dict('records'))
    print('Role-expansion players:',int(m.role_expansion_applied.sum()))
    print(f'Wrote role-expanded projections to {a.out}')

if __name__=='__main__': main()
