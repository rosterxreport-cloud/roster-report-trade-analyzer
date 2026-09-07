#!/usr/bin/env python3
"""Final enforcement of evidence-backed vacated RB workload floors plus role-contradiction audit."""
from pathlib import Path
import numpy as np, pandas as pd
P=Path('data/projections/stat_projections_2026.csv'); G=17.
def n(v,d=0.):
    try:x=float(v); return x if np.isfinite(x) else d
    except:return d
def pts(r,rec=1.):
    z=lambda k:n(r.get(k),0.); return .1*z('projected_rushing_yards')+6*z('projected_rushing_tds')+rec*z('projected_receptions')+.1*z('projected_receiving_yards')+6*z('projected_receiving_tds')+.04*z('projected_passing_yards')+4*z('projected_passing_tds')-2*z('projected_interceptions')
def restore(m,idx,vol,floor,linked):
    vals=np.array([n(m.at[i,vol]) for i in idx]); floors=np.array([n(m.at[i,floor]) for i in idx]); total=vals.sum(); need=np.maximum(floors-vals,0); surplus=np.maximum(vals-floors,0); move=min(need.sum(),surplus.sum())
    if move<=1e-9:return
    new=vals+need*(move/max(need.sum(),1e-9))-surplus*(move/max(surplus.sum(),1e-9))
    for j,i in enumerate(idx):
        old=vals[j]; nv=max(0,new[j]); ratio=nv/old if old>1e-9 else 1; m.at[i,vol]=nv
        for c in linked:m.at[i,c]=n(m.at[i,c])*ratio
    drift=sum(n(m.at[i,vol]) for i in idx)-total
    if abs(drift)>1e-6:
        donors=[i for i in idx if n(m.at[i,vol])>n(m.at[i,floor])+abs(drift)]
        if donors:m.at[donors[0],vol]=n(m.at[donors[0],vol])-drift
def main():
    m=pd.read_csv(P); elig=m.position.eq('RB')&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']); m['rb_vacated_floor_enforced']=False; m['rb_vacated_floor_carry_added']=0.; m['rb_vacated_floor_target_added']=0.; m['rb_role_contradiction_flag']=False
    bc=pd.to_numeric(m.projected_rush_attempts,errors='coerce').fillna(0).copy(); bt=pd.to_numeric(m.projected_targets,errors='coerce').fillna(0).copy()
    for team,g in m[elig].groupby('team'):
        idx=list(g.index)
        if not any(n(m.at[i,'rb_vacated_floor_strength'])>0 for i in idx):continue
        restore(m,idx,'projected_rush_attempts','rb_vacated_carry_floor',['projected_rushing_yards','projected_rushing_tds']); restore(m,idx,'projected_targets','rb_vacated_target_floor',['projected_receptions','projected_receiving_yards','projected_receiving_tds'])
    for i in m.index[elig]:
        ca=n(m.at[i,'projected_rush_attempts'])-bc.at[i]; ta=n(m.at[i,'projected_targets'])-bt.at[i]; m.at[i,'rb_vacated_floor_enforced']=ca>1e-6 or ta>1e-6; m.at[i,'rb_vacated_floor_carry_added']=max(0,ca); m.at[i,'rb_vacated_floor_target_added']=max(0,ta)
        # Flag high-confidence RB1s when committee logic still contradicts the protected role by >10% of carries.
        protected=bool(m.at[i,'rb_committee_rb1_protected']) if 'rb_committee_rb1_protected' in m else False; tier=str(m.at[i,'rb_committee_tier']) if 'rb_committee_tier' in m else ''; delta=n(m.at[i,'rb_committee_carry_delta']) if 'rb_committee_carry_delta' in m else 0
        pre=max(n(m.at[i,'projected_rush_attempts'])-ca-delta,1e-9); contradiction=protected and tier=='true_committee' and delta/pre < -.10; m.at[i,'rb_role_contradiction_flag']=contradiction
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=pts(d,1); m.at[i,'half_ppr_points']=pts(d,.5); m.at[i,'standard_points']=pts(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/G; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/G; m.at[i,'standard_per_game']=m.at[i,'standard_points']/G
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(P,index=False)
    flags=m[m.rb_role_contradiction_flag]; print('RB_ROLE_CONTRADICTION_AUDIT',flags[['name','team','ppr_points','ppr_pos_rank','rb_committee_tier','rb_committee_rb1_protection_score','rb_committee_carry_delta']].to_dict('records'))
if __name__=='__main__':main()
