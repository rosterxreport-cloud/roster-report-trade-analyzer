#!/usr/bin/env python3
"""Reallocate opportunity removed by veteran RB achievability within each backfield.

The achievability layer can suppress an overly optimistic veteran projection. This pass keeps
team RB opportunity conserved by transferring a competition-weighted share of removed carries,
targets and TDs to other active projected RBs. Recipient weights favor depth proximity, role
confidence and relative rushing/receiving talent. No player-specific overrides.
"""
from pathlib import Path
import numpy as np, pandas as pd
P=Path('data/projections/stat_projections_2026.csv')
def n(v,d=0.):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except: return d
def score(r,rec=1.):
    return .1*n(r.get('projected_rushing_yards'))+6*n(r.get('projected_rushing_tds'))+rec*n(r.get('projected_receptions'))+.1*n(r.get('projected_receiving_yards'))+6*n(r.get('projected_receiving_tds'))+.04*n(r.get('projected_passing_yards'))+4*n(r.get('projected_passing_tds'))-2*n(r.get('projected_interceptions'))
def main():
    m=pd.read_csv(P)
    # Achievability diagnostics let us infer pre-cap opportunity without changing the previous layer.
    for c in ['rb_achievability_reallocated','rb_reallocated_carries','rb_reallocated_targets','rb_reallocated_rush_tds','rb_reallocated_rec_tds']:
        m[c]=False if c=='rb_achievability_reallocated' else 0.
    elig=m.position.eq('RB') & m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for team,idxs in m[elig].groupby('team').groups.items():
        idxs=list(idxs)
        donors=[]
        for i in idxs:
            pm=n(m.at[i,'rb_achievability_ppr_multiplier'],1.) if 'rb_achievability_ppr_multiplier' in m else 1.
            jm=n(m.at[i,'rb_achievability_joint_multiplier'],1.) if 'rb_achievability_joint_multiplier' in m else 1.
            # Only final achievability suppression creates transferable opportunity.
            mult=min(1.,pm)
            if mult < .995:
                cur_c=n(m.at[i,'projected_rush_attempts']); cur_t=n(m.at[i,'projected_targets']); cur_rt=n(m.at[i,'projected_rushing_tds']); cur_et=n(m.at[i,'projected_receiving_tds'])
                donors.append((i,cur_c*(1/mult-1),cur_t*(1/mult-1),cur_rt*(1/mult-1),cur_et*(1/mult-1)))
        if not donors: continue
        for di,dc,dt,drt,det in donors:
            recips=[j for j in idxs if j!=di]
            if not recips: continue
            # Stronger competition means more of suppressed opportunity should remain in the RB room.
            comp=max(n(m.at[di,'rb_competition_carry_score'],.5) if 'rb_competition_carry_score' in m else .5,n(m.at[di,'rb_competition_target_score'],.5) if 'rb_competition_target_score' in m else .5)
            transfer=np.clip(.55+.35*comp,.55,.88)
            def weights(kind):
                vals=[]
                for j in recips:
                    depth=max(1,n(m.at[j,'depth_rank'],2) if 'depth_rank' in m else 2)
                    conf=n(m.at[j,'role_confidence'],.65) if 'role_confidence' in m else .65
                    if kind=='carry': talent=n(m.at[j,'rb_talent_rush_multiplier'],1.) if 'rb_talent_rush_multiplier' in m else 1.
                    else: talent=n(m.at[j,'rb_talent_rec_multiplier'],1.) if 'rb_talent_rec_multiplier' in m else 1.
                    vals.append((1/depth)**1.4 * (.55+.45*conf) * np.clip(talent,.8,1.25))
                a=np.array(vals,float); return a/a.sum() if a.sum()>0 else np.ones(len(a))/len(a)
            cw=weights('carry'); tw=weights('target')
            for k,j in enumerate(recips):
                addc=dc*transfer*cw[k]; addt=dt*transfer*tw[k]; addrt=drt*transfer*cw[k]; addet=det*transfer*tw[k]
                oldc=max(n(m.at[j,'projected_rush_attempts']),1e-9); oldt=max(n(m.at[j,'projected_targets']),1e-9)
                ypc=n(m.at[j,'projected_rushing_yards'])/oldc; catch=n(m.at[j,'projected_receptions'])/oldt; ypt=n(m.at[j,'projected_receiving_yards'])/oldt
                m.at[j,'projected_rush_attempts']=oldc+addc; m.at[j,'projected_rushing_yards']=n(m.at[j,'projected_rushing_yards'])+addc*ypc; m.at[j,'projected_rushing_tds']=n(m.at[j,'projected_rushing_tds'])+addrt
                m.at[j,'projected_targets']=oldt+addt; m.at[j,'projected_receptions']=n(m.at[j,'projected_receptions'])+addt*catch; m.at[j,'projected_receiving_yards']=n(m.at[j,'projected_receiving_yards'])+addt*ypt; m.at[j,'projected_receiving_tds']=n(m.at[j,'projected_receiving_tds'])+addet
                m.at[j,'rb_achievability_reallocated']=True; m.at[j,'rb_reallocated_carries']+=addc; m.at[j,'rb_reallocated_targets']+=addt; m.at[j,'rb_reallocated_rush_tds']+=addrt; m.at[j,'rb_reallocated_rec_tds']+=addet
    for i in m.index[elig]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/17; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/17; m.at[i,'standard_per_game']=m.at[i,'standard_points']/17
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        pc=fc.replace('_points','_pos_rank'); oc=fc.replace('_points','_overall_rank'); m[oc]=m[fc].rank(method='min',ascending=False); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(P,index=False)
    watch=['Rhamondre Stevenson','TreVeyon Henderson','Jaylen Warren','Rico Dowdle','Tony Pollard','Alvin Kamara']
    print(m[m.name.isin(watch)][['name','team','projected_rush_attempts','projected_targets','ppr_points','ppr_pos_rank','rb_reallocated_carries','rb_reallocated_targets']].to_dict('records'))
if __name__=='__main__': main()
