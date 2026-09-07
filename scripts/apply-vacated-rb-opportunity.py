#!/usr/bin/env python3
"""Reallocate vacated 2025 RB opportunity to current 2026 rooms with identity auditing."""
from pathlib import Path
import re, unicodedata
import numpy as np
import pandas as pd
STATS=Path('data/projections/stat_projections_2026.csv'); ROLES=Path('data/projections/player_role_context_2026.csv'); FEATS=Path('data/projections/player_features_2023_2025.csv'); G=17.0
def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d
def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower(); t=re.sub(r'\b(jr|sr|ii|iii|iv|v)\.?\b','',t); return re.sub(r'[^a-z0-9]','',t)
def pts(r,rec=1.):
    x=lambda k:num(r.get(k),0.); return .1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')+.04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')
def main():
    s=pd.read_csv(STATS); r=pd.read_csv(ROLES); f=pd.read_csv(FEATS,low_memory=False)
    keep=[c for c in ['name','position','team_2026','depth_rank','depth_starter','role_confidence','role_carry_share_2026','role_target_share_2026'] if c in r]
    rr=r[keep].rename(columns={'team_2026':'team'}).copy(); rr['nk']=rr['name'].map(norm)
    # Preserve every current-team candidate per normalized name. Duplicate-name collisions are audited rather than silently overwritten.
    team_sets=rr.groupby('nk')['team'].agg(lambda x: sorted({str(v).strip() for v in x if pd.notna(v) and str(v).strip()})).to_dict()
    current_team={k:(v[0] if len(v)==1 else None) for k,v in team_sets.items()}
    m=s.merge(rr.drop(columns=['nk']),on=['name','position','team'],how='left',suffixes=('','_vac'))
    f=f[(f.position.eq('RB')) & pd.to_numeric(f.season,errors='coerce').eq(2025)].copy(); nc='player_display_name' if 'player_display_name' in f else 'player_name'; f['nk']=f[nc].map(norm)
    # Use the explicit season team. nflverse recent_team is authoritative when populated.
    recent=f['recent_team'].astype('string').str.strip() if 'recent_team' in f else pd.Series(pd.NA,index=f.index,dtype='string')
    team=f['team'].astype('string').str.strip() if 'team' in f else pd.Series(pd.NA,index=f.index,dtype='string')
    old=recent.mask(recent.isna()|recent.eq('')|recent.eq('<NA>'),team); f['old_team']=old
    carrycol='carries' if 'carries' in f else 'rushing_attempts'; f['carries_2025']=pd.to_numeric(f.get(carrycol),errors='coerce').fillna(0.); f['targets_2025']=pd.to_numeric(f.get('targets'),errors='coerce').fillna(0.)
    # Identity audit: print every meaningful 2025 RB row with old/current teams, plus exact Etienne/Tuten diagnostics.
    audit=f.loc[(f.carries_2025>=20)|(f.targets_2025>=8),[c for c in [nc,'player_id','nk','recent_team','team','old_team','carries_2025','targets_2025'] if c in f]].copy()
    audit['current_team_candidates']=audit['nk'].map(lambda k:'|'.join(team_sets.get(k,[])))
    audit['resolved_current_team']=audit['nk'].map(current_team)
    audit['is_departed']=audit.apply(lambda x: x['resolved_current_team']!=x['old_team'],axis=1)
    print('RB_2025_IDENTITY_AUDIT',audit.sort_values(['old_team',nc]).to_dict('records'))
    focal=audit[audit[nc].astype(str).str.contains('Etienne|Tuten',case=False,na=False)]
    print('ETIENNE_TUTEN_IDENTITY_TRACE',focal.to_dict('records'))
    collisions={k:v for k,v in team_sets.items() if len(v)>1}; print('CURRENT_RB_NAME_COLLISIONS',collisions)
    rows=[]
    for old_team,g in f.dropna(subset=['old_team']).groupby('old_team'):
        tc=float(g.carries_2025.sum()); tt=float(g.targets_2025.sum()); vc=vt=0.; names=[]
        for _,x in g.iterrows():
            candidates=team_sets.get(x.nk,[]); new=current_team.get(x.nk)
            # A unique different current team or no current roster entry means the old workload is vacated.
            departed=(len(candidates)==0) or (len(candidates)==1 and candidates[0]!=str(old_team))
            # Ambiguous normalized-name collisions are not guessed; flag them in the audit and conservatively leave unvacated.
            if departed:
                vc+=float(x.carries_2025); vt+=float(x.targets_2025); names.append(f"{x.get(nc,'?')}->{new or 'OUT'}")
        rows.append({'team':str(old_team),'rb_prev_carries':tc,'rb_prev_targets':tt,'rb_vacated_carries':vc,'rb_vacated_targets':vt,'rb_vacated_departures':'|'.join(names)})
    vac=pd.DataFrame(rows); print('VACATED_RB_TEAM_AUDIT',vac.sort_values('team').to_dict('records'))
    m=m.merge(vac,on='team',how='left')
    for c in ['rb_prev_carries','rb_prev_targets','rb_vacated_carries','rb_vacated_targets']:m[c]=pd.to_numeric(m[c],errors='coerce').fillna(0.)
    m['rb_vacated_departures']=m['rb_vacated_departures'].fillna(''); m['rb_vacated_opportunity_applied']=False; m['rb_vacated_opportunity_share']=0.; m['rb_vacated_inheritance_weight']=0.; m['rb_vacated_carry_delta']=0.; m['rb_vacated_target_delta']=0.
    elig=m.position.eq('RB') & m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for tm,g in m[elig].groupby('team'):
        idx=list(g.index); prev_c=float(g.rb_prev_carries.iloc[0]); prev_t=float(g.rb_prev_targets.iloc[0]); vac_c=float(g.rb_vacated_carries.iloc[0]); vac_t=float(g.rb_vacated_targets.iloc[0])
        if prev_c<=0 or (vac_c<20 and vac_t<8): continue
        oldc=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0.).to_numpy(float); oldt=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0.).to_numpy(float); cb=float(oldc.sum()); tb=float(oldt.sum()); vac_share=max(vac_c/max(prev_c,1),vac_t/max(prev_t,1) if prev_t>0 else 0)
        weights=[]
        for i in idx:
            row=m.loc[i]; dep=max(1,int(num(row.get('depth_rank'),4))); starter=bool(row.get('depth_starter',False)); conf=float(np.clip(num(row.get('role_confidence'),.55),0,1)); rc=float(np.clip(num(row.get('role_carry_share_2026'),.10),0,.9)); rt=float(np.clip(num(row.get('role_target_share_2026'),.03),0,.35)); talent=float(np.clip(num(row.get('rb_talent_rush_multiplier'),1.),.85,1.15)); rec=float(np.clip(num(row.get('rb_talent_rec_multiplier'),1.),.85,1.15)); depth={1:1.,2:.58,3:.28,4:.14}.get(dep,.10); w=.38*depth+.20*conf+.18*np.clip(rc/.45,0,1)+.08*np.clip(rt/.12,0,1)+.10*((talent-.85)/.30)+.06*((rec-.85)/.30)+(.10 if starter and dep==1 else 0); weights.append(max(.03,w))
        w=np.asarray(weights,float); w/=w.sum(); basec=oldc/cb if cb>0 else np.ones(len(idx))/len(idx); baset=oldt/tb if tb>0 else np.ones(len(idx))/len(idx); blend=float(np.clip(.18+.42*vac_share,.18,.58)); newcs=(1-blend)*basec+blend*w; bt=min(.62,blend+.04); newts=(1-bt)*baset+bt*w; target_cb=max(cb,min(prev_c,cb*1.12)) if cb>0 else prev_c; target_tb=max(tb,min(prev_t,tb*1.15)) if tb>0 else prev_t; newc=target_cb*newcs/newcs.sum(); newt=target_tb*newts/newts.sum()
        for j,i in enumerate(idx):
            row=m.loc[i]; cr=newc[j]/oldc[j] if oldc[j]>0 else 1.; tr=newt[j]/oldt[j] if oldt[j]>0 else 1.; m.at[i,'projected_rush_attempts']=newc[j]; m.at[i,'projected_rushing_yards']=num(row.get('projected_rushing_yards'),0)*cr; m.at[i,'projected_rushing_tds']=num(row.get('projected_rushing_tds'),0)*cr; m.at[i,'projected_targets']=newt[j]; m.at[i,'projected_receptions']=num(row.get('projected_receptions'),0)*tr; m.at[i,'projected_receiving_yards']=num(row.get('projected_receiving_yards'),0)*tr; m.at[i,'projected_receiving_tds']=num(row.get('projected_receiving_tds'),0)*tr; m.at[i,'rb_vacated_opportunity_applied']=True; m.at[i,'rb_vacated_opportunity_share']=vac_share; m.at[i,'rb_vacated_inheritance_weight']=w[j]; m.at[i,'rb_vacated_carry_delta']=newc[j]-oldc[j]; m.at[i,'rb_vacated_target_delta']=newt[j]-oldt[j]
    all_=m.position.eq('RB') & m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i in m.index[all_]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=pts(d,1); m.at[i,'half_ppr_points']=pts(d,.5); m.at[i,'standard_points']=pts(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/G; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/G; m.at[i,'standard_per_game']=m.at[i,'standard_points']/G
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    drop=[c for c in m if c.endswith('_vac') or c in {'depth_rank','depth_starter','role_confidence','role_carry_share_2026','role_target_share_2026'}]; m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['Bhayshul Tuten','TreVeyon Henderson','Rico Dowdle','Jeremiyah Love','Jadarian Price']; cols=['name','team','projected_rush_attempts','projected_targets','ppr_points','ppr_pos_rank','rb_vacated_carries','rb_vacated_targets','rb_vacated_departures','rb_vacated_opportunity_share','rb_vacated_inheritance_weight','rb_vacated_carry_delta','rb_vacated_target_delta']; print('VACATED_RB_PLAYER_AUDIT',m[m.name.isin(watch)][cols].to_dict('records'))
if __name__=='__main__':main()
