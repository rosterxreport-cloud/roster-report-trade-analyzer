#!/usr/bin/env python3
"""Apply bounded RB bell-cow and play-caller rushing concentration priors.

Uses current depth hierarchy, prior healthy-game carry dominance, and the existing
2026 coaching/play-caller context. Rookie RB1s use draft capital + depth certainty
instead of being penalized for having no NFL history. Team RB carry budget is preserved.
"""
from pathlib import Path
import numpy as np
import pandas as pd

STATS=Path('data/projections/stat_projections_2026.csv')
ROLES=Path('data/projections/player_role_context_2026.csv')
COACH=Path('data/projections/coaching_scheme_context_2026.csv')

def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except (TypeError,ValueError): return d

def score(r,rec=1.0):
    x=lambda k:num(r.get(k),0.0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def main():
    s=pd.read_csv(STATS); r=pd.read_csv(ROLES); c=pd.read_csv(COACH) if COACH.exists() else pd.DataFrame()
    keep=[x for x in ['name','position','team_2026','depth_rank','depth_starter','role_confidence','carries_per_game'] if x in r]
    rr=r[keep].rename(columns={'team_2026':'team'})
    m=s.merge(rr,on=['name','position','team'],how='left',suffixes=('','_role'))
    elig=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']) & m.position.eq('RB')
    coach={row.team:row for _,row in c.iterrows()} if len(c) else {}
    for team,g in m[elig].groupby('team'):
        idx=list(g.index); old=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0.0)
        budget=float(old.sum())
        if budget<=0 or len(idx)<2: continue
        shares=(old/budget).to_numpy(copy=True); ranks=[]; starters=[]; rook=[]; picks=[]; hist=[]
        for i in idx:
            row=m.loc[i]; ranks.append(max(1,int(num(row.get('depth_rank'),4)))); starters.append(bool(row.get('depth_starter',False)))
            rook.append(row.get('projection_status')=='rookie_model'); picks.append(num(row.get('rb_workload_draft_pick'),999)); hist.append(max(0,num(row.get('carries_per_game'),0)))
        leads=[j for j,(rk,st) in enumerate(zip(ranks,starters)) if rk==1 and st]
        if len(leads)!=1: continue
        k=leads[0]
        cr=coach.get(team); rush_scheme=1.0
        if cr is not None:
            pri=num(cr.get('coach_pass_rate_index'),1.0); pvi=num(cr.get('coach_pass_volume_index'),1.0); conf=np.clip(num(cr.get('coaching_confidence'),0),0,1)
            rush_scheme=float(np.clip(1 + conf*(.55*(1-pri)+.25*(1-pvi)), .94, 1.08))
        backup_hist=max([hist[j] for j in range(len(idx)) if j!=k] or [0])
        floor=.55
        if hist[k]>=14: floor=.62
        if hist[k]>=16: floor=.66
        if hist[k]>=18: floor=.69
        if rook[k]:
            if picks[k]<=32: floor=max(floor,.64)
            elif picks[k]<=64: floor=max(floor,.61)
            elif picks[k]<=120: floor=max(floor,.58)
            if backup_hist<8: floor=min(.70,floor+.03)
        floor=float(np.clip(floor + .35*(rush_scheme-1), .53, .70))
        if shares[k]<floor:
            need=floor-shares[k]; others=np.arange(len(shares))!=k; pool=shares[others].sum()
            if pool>0:
                shares[others]*=max(0,pool-need)/pool; shares[k]=floor
        for j,i in enumerate(idx):
            row=m.loc[i]; oc=max(num(row.get('projected_rush_attempts'),0),1e-6); nc=budget*shares[j]; ratio=nc/oc
            m.at[i,'projected_rush_attempts']=nc
            for col in ['projected_rushing_yards','projected_rushing_tds']: m.at[i,col]=num(row.get(col),0)*ratio
            m.at[i,'rb_bellcow_scheme_applied']=True; m.at[i,'rb_bellcow_carry_share']=shares[j]; m.at[i,'rb_bellcow_lead_floor']=floor if j==k else np.nan; m.at[i,'rb_rush_scheme_multiplier']=rush_scheme
    all_elig=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i in m.index[all_elig]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0)
        m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/17; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/17; m.at[i,'standard_per_game']=m.at[i,'standard_points']/17
    for f in ['ppr_points','half_ppr_points','standard_points']:
        m[f.replace('_points','_overall_rank')]=m[f].rank(method='min',ascending=False); pc=f.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[f].notna(); m.loc[mask,pc]=m.loc[mask,f].rank(method='min',ascending=False)
    drop=[x for x in m.columns if x.endswith('_role') or x in {'depth_rank','depth_starter','role_confidence','carries_per_game'}]
    m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['Jeremiyah Love','Jadarian Price','Omarion Hampton','Kenneth Walker III','Bijan Robinson','Jahmyr Gibbs','Ashton Jeanty']
    cols=['name','team','projected_rush_attempts','projected_targets','ppr_points','ppr_pos_rank','rb_bellcow_carry_share','rb_bellcow_lead_floor','rb_rush_scheme_multiplier']
    print(m[m.name.isin(watch)][cols].to_dict('records'))
if __name__=='__main__': main()
