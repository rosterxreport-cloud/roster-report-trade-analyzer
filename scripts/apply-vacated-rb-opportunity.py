#!/usr/bin/env python3
"""Allocate vacated 2025 RB opportunity to current 2026 rooms at the team level."""
from pathlib import Path
import re, unicodedata
import numpy as np
import pandas as pd
STATS=Path('data/projections/stat_projections_2026.csv'); ROLES=Path('data/projections/player_role_context_2026.csv'); FEATS=Path('data/projections/player_features_2023_2025.csv'); G=17.0
TEAM_ALIASES={'JAX':'JAC','LA':'LAR','STL':'LAR','SD':'LAC','OAK':'LV'}
def team_norm(v):
    if pd.isna(v): return None
    t=str(v).strip().upper()
    if not t or t=='<NA>': return None
    return TEAM_ALIASES.get(t,t)
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
    s['team']=s['team'].map(team_norm)
    if 'team_2026' in r:r['team_2026']=r['team_2026'].map(team_norm)
    keep=[c for c in ['name','position','team_2026','depth_rank','depth_starter','role_confidence','role_carry_share_2026','role_target_share_2026'] if c in r]
    rr=r[keep].rename(columns={'team_2026':'team'}).copy(); rr['nk']=rr['name'].map(norm)
    team_sets=rr.groupby('nk')['team'].agg(lambda x:sorted({team_norm(v) for v in x if team_norm(v)})).to_dict(); current_team={k:(v[0] if len(v)==1 else None) for k,v in team_sets.items()}
    m=s.merge(rr.drop(columns=['nk']),on=['name','position','team'],how='left',suffixes=('','_vac'))
    f=f[(f.position.eq('RB')) & pd.to_numeric(f.season,errors='coerce').eq(2025)].copy(); nc='player_display_name' if 'player_display_name' in f else 'player_name'; f['nk']=f[nc].map(norm)
    recent=f['recent_team'].astype('string').str.strip() if 'recent_team' in f else pd.Series(pd.NA,index=f.index,dtype='string'); rawteam=f['team'].astype('string').str.strip() if 'team' in f else pd.Series(pd.NA,index=f.index,dtype='string')
    old=recent.mask(recent.isna()|recent.eq('')|recent.eq('<NA>'),rawteam); f['old_team_raw']=old; f['old_team']=old.map(team_norm)
    carrycol='carries' if 'carries' in f else 'rushing_attempts'; f['carries_2025']=pd.to_numeric(f.get(carrycol),errors='coerce').fillna(0.); f['targets_2025']=pd.to_numeric(f.get('targets'),errors='coerce').fillna(0.)
    rows=[]
    for old_team,g in f.dropna(subset=['old_team']).groupby('old_team'):
        tc=float(g.carries_2025.sum()); tt=float(g.targets_2025.sum()); vc=vt=0.; names=[]
        for _,x in g.iterrows():
            candidates=team_sets.get(x.nk,[]); new=current_team.get(x.nk); departed=(len(candidates)==0) or (len(candidates)==1 and candidates[0]!=old_team)
            if departed:vc+=float(x.carries_2025); vt+=float(x.targets_2025); names.append(f"{x.get(nc,'?')}->{new or 'OUT'}")
        rows.append({'team':old_team,'rb_prev_carries':tc,'rb_prev_targets':tt,'rb_vacated_carries':vc,'rb_vacated_targets':vt,'rb_vacated_departures':'|'.join(names)})
    vac=pd.DataFrame(rows); print('VACATED_RB_TEAM_AUDIT',vac.sort_values('team').to_dict('records')); m=m.merge(vac,on='team',how='left')
    for c in ['rb_prev_carries','rb_prev_targets','rb_vacated_carries','rb_vacated_targets']:m[c]=pd.to_numeric(m[c],errors='coerce').fillna(0.)
    m['rb_vacated_departures']=m['rb_vacated_departures'].fillna(''); m['rb_vacated_opportunity_applied']=False; m['rb_vacated_opportunity_share']=0.; m['rb_vacated_inheritance_weight']=0.; m['rb_vacated_carry_delta']=0.; m['rb_vacated_target_delta']=0.; m['rb_vacated_team_carry_budget']=np.nan; m['rb_vacated_team_target_budget']=np.nan; m['rb_vacated_carry_floor']=np.nan; m['rb_vacated_target_floor']=np.nan; m['rb_vacated_floor_strength']=0.
    elig=m.position.eq('RB') & m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for tm,g in m[elig].groupby('team'):
        idx=list(g.index); prev_c=float(g.rb_prev_carries.iloc[0]); prev_t=float(g.rb_prev_targets.iloc[0]); vac_c=float(g.rb_vacated_carries.iloc[0]); vac_t=float(g.rb_vacated_targets.iloc[0])
        if prev_c<=0 or (vac_c<20 and vac_t<8):continue
        oldc=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0.).to_numpy(float); oldt=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0.).to_numpy(float); cb=float(oldc.sum()); tb=float(oldt.sum()); vac_share=max(vac_c/max(prev_c,1),vac_t/max(prev_t,1) if prev_t>0 else 0)
        weights=[]
        for i in idx:
            row=m.loc[i]; dep=max(1,int(num(row.get('depth_rank'),4))); starter=bool(row.get('depth_starter',False)); conf=float(np.clip(num(row.get('role_confidence'),.55),0,1)); rc=float(np.clip(num(row.get('role_carry_share_2026'),.10),0,.9)); rt=float(np.clip(num(row.get('role_target_share_2026'),.03),0,.35)); talent=float(np.clip(num(row.get('rb_talent_rush_multiplier'),1.),.85,1.15)); rec=float(np.clip(num(row.get('rb_talent_rec_multiplier'),1.),.85,1.15)); depth={1:1.,2:.62,3:.30,4:.14}.get(dep,.10); w=.38*depth+.20*conf+.18*np.clip(rc/.45,0,1)+.08*np.clip(rt/.12,0,1)+.10*((talent-.85)/.30)+.06*((rec-.85)/.30)+(.10 if starter and dep==1 else 0); weights.append(max(.03,w))
        w=np.asarray(weights,float); w/=w.sum(); basec=oldc/cb if cb>0 else np.ones(len(idx))/len(idx); baset=oldt/tb if tb>0 else np.ones(len(idx))/len(idx)
        retained_c=max(0.,prev_c-vac_c); retained_t=max(0.,prev_t-vac_t)
        capture_c=float(np.clip(.82+.10*vac_share,.82,.92)); capture_t=float(np.clip(.78+.10*vac_share,.78,.88))
        historical_c_floor=retained_c+vac_c*capture_c; historical_t_floor=retained_t+vac_t*capture_t
        team_c_budget=max(cb,historical_c_floor); team_t_budget=max(tb,historical_t_floor)
        team_c_budget=min(team_c_budget,prev_c*1.04); team_t_budget=min(team_t_budget,prev_t*1.08 if prev_t>0 else team_t_budget)
        blend=float(np.clip(.30+.45*vac_share,.30,.72)); target_blend=float(np.clip(blend+.04,.34,.76))
        newcs=(1-blend)*basec+blend*w; newts=(1-target_blend)*baset+target_blend*w; newc=team_c_budget*newcs/newcs.sum(); newt=team_t_budget*newts/newts.sum()
        for j,i in enumerate(idx):
            row=m.loc[i]; dep=max(1,int(num(row.get('depth_rank'),4))); starter=bool(row.get('depth_starter',False)); conf=float(np.clip(num(row.get('role_confidence'),.55),0,1)); inheritance=float(w[j])
            if dep==1 and starter and conf>=.70 and vac_share>=.35:
                strength=float(np.clip(.82+.10*vac_share+.08*inheritance,.84,.96))
            elif dep<=2 and conf>=.60 and vac_share>=.50 and inheritance>=.25:
                strength=float(np.clip(.72+.08*vac_share+.06*inheritance,.76,.86))
            else: strength=0.
            cr=newc[j]/oldc[j] if oldc[j]>0 else 1.; tr=newt[j]/oldt[j] if oldt[j]>0 else 1.; m.at[i,'projected_rush_attempts']=newc[j]; m.at[i,'projected_rushing_yards']=num(row.get('projected_rushing_yards'),0)*cr; m.at[i,'projected_rushing_tds']=num(row.get('projected_rushing_tds'),0)*cr; m.at[i,'projected_targets']=newt[j]; m.at[i,'projected_receptions']=num(row.get('projected_receptions'),0)*tr; m.at[i,'projected_receiving_yards']=num(row.get('projected_receiving_yards'),0)*tr; m.at[i,'projected_receiving_tds']=num(row.get('projected_receiving_tds'),0)*tr; m.at[i,'rb_vacated_opportunity_applied']=True; m.at[i,'rb_vacated_opportunity_share']=vac_share; m.at[i,'rb_vacated_inheritance_weight']=w[j]; m.at[i,'rb_vacated_carry_delta']=newc[j]-oldc[j]; m.at[i,'rb_vacated_target_delta']=newt[j]-oldt[j]; m.at[i,'rb_vacated_team_carry_budget']=team_c_budget; m.at[i,'rb_vacated_team_target_budget']=team_t_budget; m.at[i,'rb_vacated_floor_strength']=strength
            if strength>0:
                m.at[i,'rb_vacated_carry_floor']=newc[j]*strength; m.at[i,'rb_vacated_target_floor']=newt[j]*strength
    all_=m.position.eq('RB') & m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i in m.index[all_]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=pts(d,1); m.at[i,'half_ppr_points']=pts(d,.5); m.at[i,'standard_points']=pts(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/G; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/G; m.at[i,'standard_per_game']=m.at[i,'standard_points']/G
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    drop=[c for c in m if c.endswith('_vac') or c in {'depth_rank','depth_starter','role_confidence','role_carry_share_2026','role_target_share_2026'}]; m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['Bhayshul Tuten','TreVeyon Henderson','Rico Dowdle','Jeremiyah Love','Jadarian Price']; cols=['name','team','projected_rush_attempts','projected_targets','ppr_points','ppr_pos_rank','rb_vacated_carries','rb_vacated_targets','rb_vacated_team_carry_budget','rb_vacated_team_target_budget','rb_vacated_opportunity_share','rb_vacated_inheritance_weight','rb_vacated_carry_floor','rb_vacated_target_floor','rb_vacated_floor_strength']; print('VACATED_RB_PLAYER_AUDIT',m[m.name.isin(watch)][cols].to_dict('records'))
if __name__=='__main__':main()
