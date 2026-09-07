#!/usr/bin/env python3
"""Final enforcement of evidence-backed vacated RB workload floors.

Runs after committee, plausibility, and aging layers. It restores carries/targets for backs whose
current-role/vacated-opportunity evidence established a floor, while preserving each team's RB
carry and target totals by taking opportunity only from teammates above their own floors.
"""
from pathlib import Path
import numpy as np
import pandas as pd
P=Path('data/projections/stat_projections_2026.csv'); G=17.0
def n(v,d=0.):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d
def pts(r,rec=1.):
    z=lambda k:n(r.get(k),0.); return .1*z('projected_rushing_yards')+6*z('projected_rushing_tds')+rec*z('projected_receptions')+.1*z('projected_receiving_yards')+6*z('projected_receiving_tds')+.04*z('projected_passing_yards')+4*z('projected_passing_tds')-2*z('projected_interceptions')
def restore_group(m,idx,vol_col,floor_col,linked_cols):
    vals=np.array([n(m.at[i,vol_col],0.) for i in idx],float); floors=np.array([n(m.at[i,floor_col],0.) for i in idx],float); total=float(vals.sum()); need=np.maximum(floors-vals,0.); need_total=float(need.sum())
    if need_total<=1e-9:return
    surplus=np.maximum(vals-floors,0.); pool=float(surplus.sum()); move=min(need_total,pool)
    if move<=1e-9:return
    gains=need*(move/need_total); losses=surplus*(move/pool)
    new=vals+gains-losses
    for j,i in enumerate(idx):
        old=vals[j]; nv=max(0.,new[j]); ratio=nv/old if old>1e-9 else 1.
        m.at[i,vol_col]=nv
        for c in linked_cols:m.at[i,c]=n(m.at[i,c],0.)*ratio
    # numerical guardrail
    drift=sum(n(m.at[i,vol_col],0.) for i in idx)-total
    if abs(drift)>1e-6:
        donors=[i for i in idx if n(m.at[i,vol_col],0.)>n(m.at[i,floor_col],0.)+abs(drift)]
        if donors:m.at[donors[0],vol_col]=n(m.at[donors[0],vol_col],0.)-drift
def main():
    m=pd.read_csv(P); elig=m.position.eq('RB')&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    m['rb_vacated_floor_enforced']=False; m['rb_vacated_floor_carry_added']=0.; m['rb_vacated_floor_target_added']=0.
    before_c=pd.to_numeric(m.get('projected_rush_attempts'),errors='coerce').fillna(0.).copy(); before_t=pd.to_numeric(m.get('projected_targets'),errors='coerce').fillna(0.).copy()
    for team,g in m[elig].groupby('team'):
        idx=list(g.index)
        if not any(n(m.at[i,'rb_vacated_floor_strength'],0.)>0 for i in idx):continue
        restore_group(m,idx,'projected_rush_attempts','rb_vacated_carry_floor',['projected_rushing_yards','projected_rushing_tds'])
        restore_group(m,idx,'projected_targets','rb_vacated_target_floor',['projected_receptions','projected_receiving_yards','projected_receiving_tds'])
    for i in m.index[elig]:
        ca=n(m.at[i,'projected_rush_attempts'],0.)-before_c.at[i]; ta=n(m.at[i,'projected_targets'],0.)-before_t.at[i]
        if ca>1e-6 or ta>1e-6:m.at[i,'rb_vacated_floor_enforced']=True
        m.at[i,'rb_vacated_floor_carry_added']=max(0.,ca); m.at[i,'rb_vacated_floor_target_added']=max(0.,ta)
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=pts(d,1); m.at[i,'half_ppr_points']=pts(d,.5); m.at[i,'standard_points']=pts(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/G; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/G; m.at[i,'standard_per_game']=m.at[i,'standard_points']/G
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(P,index=False)
    watch=['Bhayshul Tuten','TreVeyon Henderson','Rico Dowdle','Jeremiyah Love','Jadarian Price','Kenneth Walker III','Jahmyr Gibbs']
    cols=['name','team','projected_rush_attempts','projected_targets','ppr_points','ppr_pos_rank','rb_vacated_carry_floor','rb_vacated_target_floor','rb_vacated_floor_strength','rb_vacated_floor_enforced','rb_vacated_floor_carry_added','rb_vacated_floor_target_added']
    print('VACATED_RB_FLOOR_FINAL',m[m.name.isin(watch)][[c for c in cols if c in m]].to_dict('records'))
if __name__=='__main__':main()
