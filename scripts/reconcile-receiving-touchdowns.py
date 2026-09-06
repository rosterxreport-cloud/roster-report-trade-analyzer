#!/usr/bin/env python3
"""Project receiving TDs from team environment plus individual scoring evidence.

TD v2 blends team passing-TD allocation with each player's own regressed scoring
expectation based on projected targets, historical TD/target, projected receiving
yards and current role. Team environment remains an anchor, not a hard allocator.
"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

GAMES=17.0
LEAGUE_TD_PER_TARGET=.045

def num(v,d=0.0):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d

def points(r,rec):
    x=lambda k:num(r.get(k),0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'));ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'));ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv'));a=ap.parse_args()
    s=pd.read_csv(a.stats);r=pd.read_csv(a.roles)
    rolecols=[c for c in ['name','position','team_2026','rec_td_per_target','target_share','depth_starter','depth_rank'] if c in r.columns];rr=r[rolecols].rename(columns={'team_2026':'role_team'});m=s.merge(rr,on=['name','position'],how='left',suffixes=('','_role'));eligible=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']);m['td_allocation_share']=np.nan;m['td_individual_prior']=np.nan
    for team,g in m[eligible & m.position.isin(['RB','WR','TE'])].groupby('team'):
        q=m[eligible & m.position.eq('QB') & m.team.eq(team)].copy()
        if q.empty:continue
        team_td=pd.to_numeric(q.projected_passing_tds,errors='coerce').max()
        if not np.isfinite(team_td) or team_td<=0:continue
        idx=g.index;targets=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0);yards=pd.to_numeric(m.loc[idx,'projected_receiving_yards'],errors='coerce').fillna(0);hist=pd.to_numeric(m.loc[idx,'rec_td_per_target'],errors='coerce').fillna(LEAGUE_TD_PER_TARGET).clip(.012,.11);starter=m.loc[idx,'depth_starter'].fillna(False).astype(bool);rank=pd.to_numeric(m.loc[idx,'depth_rank'],errors='coerce').fillna(9)
        # Regress noisy TD/target heavily, then add a modest yardage/red-zone proxy.
        reg_rate=.55*LEAGUE_TD_PER_TARGET+.45*hist
        volume_prior=targets*reg_rate
        yard_prior=yards/175.0
        individual=.62*volume_prior+.38*yard_prior
        role_mult=np.where(starter,1.05,np.where(rank.le(2),.96,np.where(rank.le(3),.86,.72)))
        individual=pd.Series(individual*role_mult,index=idx).clip(lower=0,upper=14)
        # Team allocation uses volume and scoring skill but is only half the final signal.
        w=targets.pow(.88)*reg_rate.pow(.28)*np.where(starter,1.08,1.0);w=pd.Series(w,index=idx).replace([np.inf,-np.inf],np.nan).fillna(0)
        if w.sum()<=0:continue
        share=w/w.sum();alloc=team_td*.97*share
        new_td=.52*alloc+.48*individual
        # Softly reconcile the room to team passing TDs while preserving individual priors.
        total=new_td.sum();budget=team_td*.99
        if total>0:
            scale=np.clip(budget/total,.90,1.12);new_td=new_td*scale
        new_td=new_td.clip(lower=0,upper=14)
        m.loc[idx,'projected_receiving_tds']=new_td;m.loc[idx,'td_allocation_share']=share;m.loc[idx,'td_individual_prior']=individual
    for idx,row in m[eligible].iterrows():
        d=m.loc[idx].to_dict();m.at[idx,'ppr_points']=points(d,1);m.at[idx,'half_ppr_points']=points(d,.5);m.at[idx,'standard_points']=points(d,0);m.at[idx,'ppr_per_game']=m.at[idx,'ppr_points']/GAMES;m.at[idx,'half_ppr_per_game']=m.at[idx,'half_ppr_points']/GAMES;m.at[idx,'standard_per_game']=m.at[idx,'standard_points']/GAMES
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        m[fmt.replace('_points','_overall_rank')]=m[fmt].rank(method='min',ascending=False);pc=fmt.replace('_points','_pos_rank');m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fmt].notna();m.loc[mask,pc]=m.loc[mask,fmt].rank(method='min',ascending=False)
    m=m.drop(columns=[c for c in ['role_team','rec_td_per_target','target_share','depth_starter','depth_rank'] if c in m.columns],errors='ignore');nums=m.select_dtypes(include=[np.number]).columns;m[nums]=m[nums].round(3);m.to_csv(a.out,index=False)
    watch=m[m.name.isin(["Ja'Marr Chase",'Justin Jefferson','CeeDee Lamb','Emeka Egbuka','Keenan Allen'])];print(watch[['name','projected_targets','projected_receiving_tds','td_individual_prior','ppr_points','ppr_pos_rank']].sort_values('ppr_pos_rank').to_dict('records'));print(f'Wrote TD-v2 projections to {a.out}')
if __name__=='__main__':main()
