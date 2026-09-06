#!/usr/bin/env python3
"""Reconcile QB rushing volume and QB/RB rushing efficiency.

Veteran yards per carry comes from the 2023-2025 weighted role context, then is
regressed 35% toward the position mean. This keeps one hot/cold season from
fully driving rushing-yard projections while preserving demonstrated efficiency.
"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
GAMES=17.0
YPC_REGRESSION=.35

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
    cols=[c for c in ['name','position','carries_per_game','yards_per_carry','depth_starter'] if c in r.columns]
    x=s.merge(r[cols],on=['name','position'],how='left')

    # Position baselines are calculated from the weighted 2023-2025 veteran YPC
    # already produced by build-2026-context.py.
    ypc_means={}
    for pos in ['QB','RB']:
        vals=pd.to_numeric(r.loc[r['position'].eq(pos),'yards_per_carry'],errors='coerce')
        vals=vals[np.isfinite(vals)]
        ypc_means[pos]=float(vals.mean()) if len(vals) else (4.7 if pos=='QB' else 4.25)

    # Preserve demonstrated rushing volume for veteran QBs.
    mask=x['projection_status'].eq('modeled_veteran')&x['position'].eq('QB')
    for i,row in x[mask].iterrows():
        hist_pg=num(row.get('carries_per_game')); old=num(row.get('projected_rush_attempts'))
        if not np.isfinite(hist_pg) or not np.isfinite(old) or old<=0: continue
        hist=hist_pg*GAMES
        starter=bool(row.get('depth_starter',False))
        new=.75*hist+.25*old
        if starter:new=max(new,.85*hist)
        new=min(new,170.0)
        old_td=num(row.get('projected_rushing_tds'),0.0)
        x.at[i,'projected_rush_attempts']=new
        x.at[i,'projected_rushing_tds']=old_td*(new/old)

    # Explicitly project rushing yards from weighted historical YPC for both QBs
    # and RBs. Rookie-model rows retain their separately calibrated rookie YPC.
    eff_mask=x['projection_status'].isin(['modeled_veteran','returning_fallback'])&x['position'].isin(['QB','RB'])
    for i,row in x[eff_mask].iterrows():
        att=num(row.get('projected_rush_attempts'))
        hist_ypc=num(row.get('yards_per_carry'))
        if not np.isfinite(att) or att<0 or not np.isfinite(hist_ypc): continue
        mean=ypc_means[row['position']]
        projected_ypc=(1-YPC_REGRESSION)*hist_ypc+YPC_REGRESSION*mean
        # Guard only against corrupted/outlier source values, not normal player differences.
        projected_ypc=float(np.clip(projected_ypc,1.5,8.5))
        x.at[i,'projected_yards_per_carry']=projected_ypc
        x.at[i,'projected_rushing_yards']=att*projected_ypc

    eligible=x['projection_status'].isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i,row in x[eligible].iterrows():
        d=row.to_dict();x.at[i,'ppr_points']=score(d,1);x.at[i,'half_ppr_points']=score(d,.5);x.at[i,'standard_points']=score(d,0)
        x.at[i,'ppr_per_game']=x.at[i,'ppr_points']/GAMES;x.at[i,'half_ppr_per_game']=x.at[i,'half_ppr_points']/GAMES;x.at[i,'standard_per_game']=x.at[i,'standard_points']/GAMES
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        x[fmt.replace('_points','_overall_rank')]=x[fmt].rank(method='min',ascending=False);pc=fmt.replace('_points','_pos_rank');x[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            m=x['position'].eq(pos)&x[fmt].notna();x.loc[m,pc]=x.loc[m,fmt].rank(method='min',ascending=False)
    x=x.drop(columns=['carries_per_game','yards_per_carry','depth_starter'],errors='ignore');nums=x.select_dtypes(include=[np.number]).columns;x[nums]=x[nums].round(2);x.to_csv(a.stats,index=False)
    q=x[(x['position'].eq('QB'))&x['ppr_points'].notna()].nlargest(20,'ppr_points')
    print(q[['name','ppr_points','ppr_pos_rank','projected_rush_attempts','projected_yards_per_carry','projected_rushing_yards']].to_dict('records'))
if __name__=='__main__':main()
