#!/usr/bin/env python3
"""Reconcile confirmed starter QB passing volume without treating missed games as future role loss."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
GAMES=17.0

def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except (TypeError,ValueError): return d

def score(r,rec):
    x=lambda k:num(r.get(k),0.0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'));ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'));a=ap.parse_args()
    s=pd.read_csv(a.stats);r=pd.read_csv(a.roles)
    cols=[c for c in ['name','position','attempts_per_game','projected_pass_attempts','depth_starter'] if c in r.columns]
    x=s.merge(r[cols],on=['name','position'],how='left',suffixes=('','_role'))
    mask=x['projection_status'].eq('modeled_veteran')&x['position'].eq('QB')
    for i,row in x[mask].iterrows():
        hist_pg=num(row.get('attempts_per_game')); team_att=num(row.get('projected_pass_attempts_role')); old=num(row.get('projected_pass_attempts'))
        starter=bool(row.get('depth_starter',False))
        if not starter or not np.isfinite(hist_pg) or not np.isfinite(team_att) or not np.isfinite(old) or old<=0: continue
        hist_full=hist_pg*GAMES
        team_starter=.95*team_att
        new=.65*hist_full+.35*team_starter
        new=max(new,.90*hist_full)
        new=min(new,team_att,650.0)
        ratio=new/old
        x.at[i,'projected_pass_attempts']=new
        for c in ['projected_passing_yards','projected_passing_tds','projected_interceptions']:
            x.at[i,c]=num(row.get(c),0.0)*ratio
    eligible=x['projection_status'].isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i,row in x[eligible].iterrows():
        d=row.to_dict();x.at[i,'ppr_points']=score(d,1);x.at[i,'half_ppr_points']=score(d,.5);x.at[i,'standard_points']=score(d,0)
        x.at[i,'ppr_per_game']=x.at[i,'ppr_points']/GAMES;x.at[i,'half_ppr_per_game']=x.at[i,'half_ppr_points']/GAMES;x.at[i,'standard_per_game']=x.at[i,'standard_points']/GAMES
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        x[fmt.replace('_points','_overall_rank')]=x[fmt].rank(method='min',ascending=False);pc=fmt.replace('_points','_pos_rank');x[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            m=x['position'].eq(pos)&x[fmt].notna();x.loc[m,pc]=x.loc[m,fmt].rank(method='min',ascending=False)
    x=x.drop(columns=['attempts_per_game','projected_pass_attempts_role','depth_starter'],errors='ignore');nums=x.select_dtypes(include=[np.number]).columns;x[nums]=x[nums].round(2);x.to_csv(a.stats,index=False)
    q=x[(x.position.eq('QB'))&x.ppr_points.notna()].nlargest(20,'ppr_points')
    q['projected_pass_ypa']=q['projected_passing_yards']/q['projected_pass_attempts']
    print(q[['name','ppr_points','ppr_pos_rank','projected_pass_attempts','projected_pass_ypa','projected_passing_yards','projected_passing_tds','projected_interceptions']].round(2).to_dict('records'))
if __name__=='__main__':main()
