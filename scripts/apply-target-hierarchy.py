#!/usr/bin/env python3
"""Reallocate receiving opportunity using recent same-team target hierarchy.

Projection-only layer. Recent production earned with the player's current team/QB
gets more weight than older production accumulated elsewhere. Current starter role
still matters, and total team targets are preserved.
"""
from pathlib import Path
import argparse, numpy as np, pandas as pd
GAMES=17.0

def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d

def scale(m,idx,ratio):
    for c in ['projected_targets','projected_receptions','projected_receiving_yards','projected_receiving_tds']:
        if c in m.columns and np.isfinite(num(m.at[idx,c])): m.at[idx,c]=num(m.at[idx,c],0)*ratio

def pts(r,rec):
    x=lambda k:num(r.get(k),0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'));ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'));ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv'));a=ap.parse_args()
    s=pd.read_csv(a.stats);r=pd.read_csv(a.roles)
    cols=[c for c in ['name','position','team_2026','recent_team','targets_per_game','target_share','games','depth_starter','depth_rank','changed_team'] if c in r.columns]
    m=s.merge(r[cols].rename(columns={'team_2026':'role_team'}),on=['name','position'],how='left',suffixes=('','_hier'))
    eligible=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']) & m.position.isin(['WR','TE','RB'])
    m['target_hierarchy_multiplier']=1.0;m['same_team_hierarchy_weight']=0.0
    for team,g in m[eligible].groupby('team'):
        idx=g.index;cur=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0)
        if cur.sum()<=0:continue
        pg=pd.to_numeric(m.loc[idx,'targets_per_game'],errors='coerce').fillna(0);share=pd.to_numeric(m.loc[idx,'target_share'],errors='coerce').fillna(0);games=pd.to_numeric(m.loc[idx,'games'],errors='coerce').fillna(0)
        starter=m.loc[idx,'depth_starter'].fillna(False).astype(bool);rank=pd.to_numeric(m.loc[idx,'depth_rank'],errors='coerce').fillna(9);changed=m.loc[idx,'changed_team'].fillna(False).astype(bool)
        recent_team=m.loc[idx,'recent_team'].fillna('') if 'recent_team' in m.columns else pd.Series('',index=idx)
        same_team=recent_team.eq(team) | (~changed)
        recent=(pg/pg.max() if pg.max()>0 else pg)*.58+(share/share.max() if share.max()>0 else share)*.42
        role=np.where(starter,1.0,np.where(rank.le(2),.90,np.where(rank.le(3),.78,.62)))
        sample=np.clip(games/12.0,.45,1.0)
        # Same-team/QB evidence gets full credit. Players whose history is largely from
        # another offense receive a meaningful discount until current-team evidence builds.
        continuity=np.where(same_team,1.12,np.where(changed,.76,.96))
        score=pd.Series(recent*role*sample*continuity,index=idx).clip(lower=.04)
        current_share=cur/cur.sum();desired=score/score.sum()
        # Expose 34% of distribution when same-team evidence exists; still bounded.
        blended=.66*current_share+.34*desired
        mult=(blended/current_share.replace(0,np.nan)).replace([np.inf,-np.inf],np.nan).fillna(1).clip(.76,1.24)
        new=cur*mult;new*=cur.sum()/new.sum()
        for i in idx:
            old=num(m.at[i,'projected_targets'],0);nt=float(new.loc[i])
            if old>0:
                ratio=nt/old;scale(m,i,ratio);m.at[i,'target_hierarchy_multiplier']=ratio;m.at[i,'same_team_hierarchy_weight']=float(continuity[list(idx).index(i)])
    for i in m[eligible].index:
        d=m.loc[i].to_dict();m.at[i,'ppr_points']=pts(d,1);m.at[i,'half_ppr_points']=pts(d,.5);m.at[i,'standard_points']=pts(d,0);m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES;m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES;m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        m[fmt.replace('_points','_overall_rank')]=m[fmt].rank(method='min',ascending=False);pc=fmt.replace('_points','_pos_rank');m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fmt].notna();m.loc[mask,pc]=m.loc[mask,fmt].rank(method='min',ascending=False)
    drop=['role_team','recent_team','targets_per_game','target_share','games','depth_starter','depth_rank','changed_team'];m=m.drop(columns=[c for c in drop if c in m.columns],errors='ignore');nums=m.select_dtypes(include=[np.number]).columns;m[nums]=m[nums].round(3);m.to_csv(a.out,index=False)
    watch=m[m.name.isin(['Parker Washington','Jakobi Meyers','Brian Thomas Jr.','Ladd McConkey'])];print(watch[['name','projected_targets','target_hierarchy_multiplier','same_team_hierarchy_weight','ppr_points','ppr_pos_rank']].sort_values('ppr_pos_rank').to_dict('records'));print(f'Wrote same-team target-hierarchy projections to {a.out}')
if __name__=='__main__':main()
