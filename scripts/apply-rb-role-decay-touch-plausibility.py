#!/usr/bin/env python3
"""RB negative-role receiving decay + total-touch plausibility.

Veteran historical ceilings are useful only after a player has established a multi-year NFL role.
Second-year RBs use current hierarchy/role evidence as the authoritative workload baseline; rookie
usage is a weak prior and cannot impose a veteran-style touch ceiling. No player-specific overrides.
"""
from pathlib import Path
import re, unicodedata
import numpy as np, pandas as pd
P=Path('data/projections/stat_projections_2026.csv'); R=Path('data/projections/player_role_context_2026.csv'); F=Path('data/projections/player_features_2023_2025.csv'); G=17.; W={2023:.15,2024:.30,2025:.55}
def n(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d
def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower(); t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t); return re.sub(r'[^a-z0-9]','',t)
def pts(r,rec=1.):
    z=lambda k:n(r.get(k),0.); return .1*z('projected_rushing_yards')+6*z('projected_rushing_tds')+rec*z('projected_receptions')+.1*z('projected_receiving_yards')+6*z('projected_receiving_tds')+.04*z('projected_passing_yards')+4*z('projected_passing_tds')-2*z('projected_interceptions')
def main():
    m=pd.read_csv(P); roles=pd.read_csv(R); f=pd.read_csv(F,low_memory=False)
    keep=[c for c in ['name','position','team_2026','depth_rank','depth_starter','role_confidence'] if c in roles]; rr=roles[keep].rename(columns={'team_2026':'team'}); m=m.merge(rr,on=['name','position','team'],how='left',suffixes=('','_rtp'))
    f=f[(f.position.eq('RB'))&f.season.isin(W)].copy(); nc='player_display_name' if 'player_display_name' in f else 'player_name'; f['nk']=f[nc].map(norm); hist={}
    for nk,g in f.groupby('nk'):
        games=pd.to_numeric(g.get('games'),errors='coerce').fillna(0); seasons=sorted(set(pd.to_numeric(g.loc[games.gt(0),'season'],errors='coerce').dropna().astype(int))); wt=g.season.map(W).fillna(0)*np.sqrt(games.clip(lower=1)/12).clip(upper=1); ok=wt.gt(0)&games.gt(0)
        def av(cols):
            for c in cols:
                if c in g:
                    x=pd.to_numeric(g[c],errors='coerce')/games.where(games>0); good=ok&x.notna()
                    if good.any():return float(np.average(x[good],weights=wt[good]))
            return np.nan
        hist[nk]={'cpg':av(['carries','rushing_attempts']),'tpg':av(['targets']),'seasons':seasons,'nseasons':len(seasons)}
    for c in ['rb_negative_role_decay_applied','rb_negative_role_target_multiplier','rb_touch_plausibility_applied','rb_touch_plausibility_cap','rb_touch_plausibility_multiplier','rb_touch_plausibility_second_year','rb_hierarchy_baseline_protected']:
        m[c]=False if c.endswith('_applied') or c.endswith('_year') or c.endswith('_protected') else np.nan
    elig=m.position.eq('RB')&m.projection_status.isin(['modeled_veteran','returning_fallback'])
    for i in m.index[elig]:
        row=m.loc[i]; h=hist.get(norm(row['name'])); rank=max(1,int(n(row.get('depth_rank'),4))); starter=bool(row.get('depth_starter',False)); conf=np.clip(n(row.get('role_confidence'),.6),0,1); cc=np.clip(n(row.get('rb_competition_carry_score'),.5),0,1); tc=np.clip(n(row.get('rb_competition_target_score'),.5),0,1); second=bool(h and h.get('nseasons')==1 and h.get('seasons')==[2025]); hierarchy=np.clip(n(row.get('rb_hierarchy_lead_evidence'),row.get('rb_committee_rb1_protection_score',0)),0,1); vac=np.clip(n(row.get('rb_vacated_floor_strength'),0),0,1)
        m.at[i,'rb_touch_plausibility_second_year']=second
        # Receiving-role decay remains role-sensitive, but sophomore RB1s are not punished for rookie receiving usage.
        if rank>=3:tm=.48
        elif rank==2:tm=np.clip(.76-.30*tc+.08*conf,.48,.76)
        elif starter:tm=np.clip(1.04-.22*max(0,tc-.42),.82,1.04)
        else:tm=np.clip(.88-.22*tc,.62,.84)
        if second and rank==1 and starter:tm=max(tm,np.clip(.94+.06*conf-.04*max(0,tc-.55),.92,1.0))
        if tm<.995:
            for c in ['projected_targets','projected_receptions','projected_receiving_yards','projected_receiving_tds']:m.at[i,c]=n(m.at[i,c],0)*tm
            m.at[i,'rb_negative_role_decay_applied']=True
        m.at[i,'rb_negative_role_target_multiplier']=tm
        touch_mult=1.; cap=np.inf; cur=n(m.at[i,'projected_rush_attempts'],0)+n(m.at[i,'projected_targets'],0)
        if second:
            # Current evidence, not rookie total, defines Year-2 achievability. Only trim genuinely implausible
            # totals, and make the allowed ceiling expand with RB1/hierarchy/vacated-role evidence.
            role_strength=np.clip(.30*(rank==1)+.20*starter+.18*conf+.17*hierarchy+.15*vac,0,1)
            cap=np.clip(235+105*role_strength-42*cc-30*tc,215,330)
            raw=min(1.,cap/max(cur,1e-9)); touch_mult=.70+.30*raw if raw<1 else 1.
            if rank==1 and starter and (hierarchy>=.55 or vac>=.55):touch_mult=max(touch_mult,.94); m.at[i,'rb_hierarchy_baseline_protected']=True
        elif h and h.get('nseasons',0)>=2 and np.isfinite(n(h.get('cpg'))) and np.isfinite(n(h.get('tpg'))):
            base=(n(h['cpg'],0)+n(h['tpg'],0))*G
            if rank==1 and starter:growth=np.clip(1.16-.18*cc-.14*tc+.06*conf,.94,1.16)
            elif rank==2:growth=np.clip(.84-.12*cc-.12*tc,.62,.82)
            else:growth=.60
            cap=base*growth; raw=min(1.,cap/max(cur,1e-9)); touch_mult=.30+.70*raw if raw<1 else 1.
        if touch_mult<.995:
            for c in ['projected_rush_attempts','projected_rushing_yards','projected_targets','projected_receptions','projected_receiving_yards']:m.at[i,c]=n(m.at[i,c],0)*touch_mult
            td_mult=.65+.35*touch_mult; m.at[i,'projected_rushing_tds']=n(m.at[i,'projected_rushing_tds'],0)*td_mult; m.at[i,'projected_receiving_tds']=n(m.at[i,'projected_receiving_tds'],0)*td_mult; m.at[i,'rb_touch_plausibility_applied']=True
        m.at[i,'rb_touch_plausibility_cap']=cap if np.isfinite(cap) else np.nan; m.at[i,'rb_touch_plausibility_multiplier']=touch_mult
    all_=m.position.eq('RB')&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i in m.index[all_]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=pts(d,1); m.at[i,'half_ppr_points']=pts(d,.5); m.at[i,'standard_points']=pts(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/G; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/G; m.at[i,'standard_per_game']=m.at[i,'standard_points']/G
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    m=m.drop(columns=[c for c in m if c.endswith('_rtp') or c in {'depth_rank','depth_starter','role_confidence'}],errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(P,index=False)
    watch=['Bhayshul Tuten','Jeremiyah Love','TreVeyon Henderson','Rico Dowdle','Kenneth Walker III','Jahmyr Gibbs']; cols=['name','projected_rush_attempts','projected_targets','ppr_points','ppr_pos_rank','rb_touch_plausibility_second_year','rb_hierarchy_baseline_protected','rb_touch_plausibility_cap','rb_touch_plausibility_multiplier','rb_negative_role_target_multiplier']; print('RB_ROLE_DECAY_AUDIT',m[m.name.isin(watch)][cols].to_dict('records'))
if __name__=='__main__':main()
