#!/usr/bin/env python3
"""Reconcile RB rushing TDs using team budget, current hierarchy, workload and scoring evidence.

This prevents rushing TDs from merely scaling with stale pre-hierarchy projections.
Current carry share/depth is the anchor; historical TD rate and draft capital are supporting evidence.
"""
from pathlib import Path
import numpy as np
import pandas as pd

STATS=Path('data/projections/stat_projections_2026.csv')
ROLES=Path('data/projections/player_role_context_2026.csv')
GAMES=17.0

def num(v,d=0.0):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except (TypeError,ValueError): return d

def points(r,rec=1.0):
    x=lambda k:num(r.get(k),0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def main():
    s=pd.read_csv(STATS); roles=pd.read_csv(ROLES)
    keep=[c for c in ['name','position','team_2026','depth_rank','depth_starter','rookie','draft_pick'] if c in roles]
    rr=roles[keep].rename(columns={'team_2026':'team'})
    m=s.merge(rr,on=['name','position','team'],how='left',suffixes=('','_role'))
    elig=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']) & m.position.eq('RB')
    m['rb_rush_td_reconciled']=False; m['rb_rush_td_share']=np.nan; m['rb_rush_td_team_budget']=np.nan
    for team,g in m[elig].groupby('team'):
        idx=list(g.index)
        if not idx: continue
        old_td=pd.to_numeric(m.loc[idx,'projected_rushing_tds'],errors='coerce').fillna(0.0)
        carries=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0.0)
        if carries.sum()<=0: continue
        # Preserve the team's modeled RB rushing-TD expectation; redistribute who scores them.
        # Bound only pathological budgets, not normal team-level model opinions.
        budget=float(np.clip(old_td.sum(), max(1.5,carries.sum()*.012), max(3.0,carries.sum()*.055)))
        carry_share=(carries/carries.sum()).to_numpy()
        weights=[]
        for j,i in enumerate(idx):
            row=m.loc[i]
            rank=max(1,int(num(row.get('depth_rank'),4)))
            starter=bool(row.get('depth_starter',False))
            depth={1:1.00,2:.62,3:.34,4:.18}.get(rank,.12)
            if starter: depth*=1.10
            # Historical/model TD efficiency is supporting evidence, heavily regressed.
            c=max(num(row.get('projected_rush_attempts'),0),1.0)
            old_rate=num(row.get('projected_rushing_tds'),0)/c
            rate_signal=np.clip(old_rate/.035,.55,1.55)
            rookie=bool(row.get('rookie',False)); pick=num(row.get('draft_pick'),999)
            capital=1.12 if rookie and pick<=32 else (1.06 if rookie and pick<=64 else 1.0)
            # 65% actual reconciled carry share, 25% current hierarchy, 10% regressed scoring history.
            w=(.65*carry_share[j]+.25*(depth/1.10)+.10*rate_signal)*capital
            weights.append(max(.01,w))
        w=np.asarray(weights); w=w/w.sum()
        # A true RB1 can dominate goal-line work, but no back gets an implausible monopoly.
        if len(w)>1 and w.max()>.72:
            k=int(w.argmax()); excess=w[k]-.72; w[k]=.72
            oth=np.arange(len(w))!=k; w[oth]+=excess*w[oth]/w[oth].sum()
        for j,i in enumerate(idx):
            m.at[i,'projected_rushing_tds']=budget*w[j]
            m.at[i,'rb_rush_td_reconciled']=True
            m.at[i,'rb_rush_td_share']=w[j]
            m.at[i,'rb_rush_td_team_budget']=budget
    for i,row in m[m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])].iterrows():
        d=m.loc[i].to_dict()
        for rec,f in [(1,'ppr_points'),(.5,'half_ppr_points'),(0,'standard_points')]: m.at[i,f]=points(d,rec)
        m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for f in ['ppr_points','half_ppr_points','standard_points']:
        m[f.replace('_points','_overall_rank')]=m[f].rank(method='min',ascending=False); pc=f.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[f].notna(); m.loc[mask,pc]=m.loc[mask,f].rank(method='min',ascending=False)
    drop=[c for c in m.columns if c.endswith('_role') or c in {'depth_rank','depth_starter','rookie','draft_pick'}]
    m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['Jeremiyah Love','Tyler Allgeier','Kenneth Walker III','Josh Jacobs','David Montgomery','Rhamondre Stevenson','Justice Hill']
    print(m[m.name.isin(watch)][['name','team','projected_rush_attempts','projected_rushing_tds','rb_rush_td_share','rb_rush_td_team_budget','ppr_points','ppr_pos_rank']].sort_values(['team','ppr_pos_rank']).to_dict('records'))

if __name__=='__main__': main()
