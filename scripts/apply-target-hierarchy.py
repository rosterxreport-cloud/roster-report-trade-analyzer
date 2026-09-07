#!/usr/bin/env python3
"""Reallocate receiving opportunity using current-offense target evidence.

Projection-only layer. In-season acquisitions receive a meaningful continuity
discount because some of their prior-season target history came in another offense.
Established offseason movers retain most of their demonstrated target-earning signal.
Team target totals remain preserved and individual changes remain bounded.
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
        if c in m.columns and np.isfinite(num(m.at[idx,c])):m.at[idx,c]=num(m.at[idx,c],0)*ratio

def pts(r,rec):
    x=lambda k:num(r.get(k),0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'));ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'));ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv'));a=ap.parse_args()
    s=pd.read_csv(a.stats);r=pd.read_csv(a.roles)
    cols=[c for c in ['name','position','team_2026','recent_team','targets_per_game','target_share','games','depth_starter','depth_rank','changed_team'] if c in r.columns]
    m=s.merge(r[cols].rename(columns={'team_2026':'role_team'}),on=['name','position'],how='left',suffixes=('','_hier'))
    eligible=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']) & m.position.isin(['WR','TE','RB'])
    m['target_hierarchy_multiplier']=1.0;m['current_offense_evidence_weight']=1.0
    for team,g in m[eligible].groupby('team'):
        idx=g.index;cur=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0)
        if cur.sum()<=0:continue
        pg=pd.to_numeric(m.loc[idx,'targets_per_game'],errors='coerce').fillna(0);share=pd.to_numeric(m.loc[idx,'target_share'],errors='coerce').fillna(0);games=pd.to_numeric(m.loc[idx,'games'],errors='coerce').fillna(0)
        starter=m.loc[idx,'depth_starter'].fillna(False).astype(bool);rank=pd.to_numeric(m.loc[idx,'depth_rank'],errors='coerce').fillna(9);changed=m.loc[idx,'changed_team'].fillna(False).astype(bool)
        recent_team=m.loc[idx,'recent_team'].fillna('') if 'recent_team' in m.columns else pd.Series('',index=idx)
        continuity=pd.Series(1.0,index=idx,dtype=float)
        for i in idx:
            if not changed.loc[i]: continue
            # If the 2025 recent team already equals the 2026 team, this was likely an
            # in-season acquisition and the current-offense sample is partial.
            if str(recent_team.loc[i])==str(team):
                continuity.loc[i]=float(np.clip(.48+.025*games.loc[i],.58,.78))
            else:
                # Offseason movers should retain most of proven target-earning ability.
                # Established volume earners are near the top of the 0.80-0.90 band.
                volume=float(np.clip((pg.loc[i]-4.0)/4.0,0,1))
                share_strength=float(np.clip((share.loc[i]-.14)/.14,0,1))
                continuity.loc[i]=float(np.clip(.80+.06*volume+.04*share_strength,.80,.90))
        adj_pg=pg*continuity;adj_share=share*continuity
        recent=(adj_pg/adj_pg.max() if adj_pg.max()>0 else adj_pg)*.58+(adj_share/adj_share.max() if adj_share.max()>0 else adj_share)*.42
        role=np.where(starter,1.0,np.where(rank.le(2),.90,np.where(rank.le(3),.78,.62)))
        sample=np.clip(games/12.0,.45,1.0)
        score=pd.Series(recent*role*sample,index=idx).clip(lower=.04)
        current_share=cur/cur.sum();desired=score/score.sum()
        blended=.62*current_share+.38*desired
        mult=(blended/current_share.replace(0,np.nan)).replace([np.inf,-np.inf],np.nan).fillna(1).clip(.72,1.28)
        new=cur*mult;new*=cur.sum()/new.sum()
        for i in idx:
            old=num(m.at[i,'projected_targets'],0);nt=float(new.loc[i])
            if old>0:
                ratio=nt/old;scale(m,i,ratio);m.at[i,'target_hierarchy_multiplier']=ratio;m.at[i,'current_offense_evidence_weight']=continuity.loc[i]
    for i in m[eligible].index:
        d=m.loc[i].to_dict();m.at[i,'ppr_points']=pts(d,1);m.at[i,'half_ppr_points']=pts(d,.5);m.at[i,'standard_points']=pts(d,0);m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES;m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES;m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        m[fmt.replace('_points','_overall_rank')]=m[fmt].rank(method='min',ascending=False);pc=fmt.replace('_points','_pos_rank');m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fmt].notna();m.loc[mask,pc]=m.loc[mask,fmt].rank(method='min',ascending=False)
    drop=['role_team','recent_team','targets_per_game','target_share','games','depth_starter','depth_rank','changed_team'];m=m.drop(columns=[c for c in drop if c in m.columns],errors='ignore');nums=m.select_dtypes(include=[np.number]).columns;m[nums]=m[nums].round(3);m.to_csv(a.out,index=False)
    watch=m[m.name.isin(['A.J. Brown','Jaylen Waddle','DJ Moore','Jameson Williams','Christian Watson'])];print(watch[['name','projected_targets','target_hierarchy_multiplier','current_offense_evidence_weight','projected_receiving_tds','ppr_points','ppr_pos_rank']].sort_values('ppr_pos_rank').to_dict('records'));print(f'Wrote current-offense hierarchy projections to {a.out}')
if __name__=='__main__':main()
