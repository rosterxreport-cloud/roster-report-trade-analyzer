#!/usr/bin/env python3
"""Optimize RB committee opportunity without player-specific overrides.

This pass runs after veteran achievability/reallocation and before role-decay/aging.
It preserves each team's current projected RB carry and target budgets, then lets genuine
committee backs earn opportunity from a blend of current role, depth proximity, rushing
merit, receiving merit, draft/age trajectory signals, and competition strength.
Clear lead backs with weak competition retain concentration; strong committees are allowed
to become much closer to merit-based splits. TD opportunity moves with its underlying
carry/target opportunity rather than being independently invented.
"""
from pathlib import Path
import re, unicodedata
import numpy as np
import pandas as pd

STATS=Path('data/projections/stat_projections_2026.csv')
ROLES=Path('data/projections/player_role_context_2026.csv')
DRAFT=Path('data/projections/draft_picks_normalized.csv')
GAMES=17.0

def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except: return d

def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    t=re.sub(r'\b(jr|sr|ii|iii|iv|v)\.?\b','',t)
    return re.sub(r'[^a-z0-9]','',t)

def score(r,rec=1.0):
    x=lambda k:num(r.get(k),0.)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def draft_score(pick):
    p=num(pick,999)
    if p<=32:return 1.0
    if p<=64:return .82
    if p<=120:return .62
    if p<=180:return .42
    if p<=257:return .25
    return .10

def main():
    s=pd.read_csv(STATS); r=pd.read_csv(ROLES)
    keep=[c for c in ['name','position','team_2026','depth_rank','depth_starter','role_confidence','rookie','role_carry_share_2026','role_target_share_2026'] if c in r]
    rr=r[keep].rename(columns={'team_2026':'team'}).copy(); rr['nk']=rr['name'].map(norm)
    if DRAFT.exists():
        d=pd.read_csv(DRAFT,low_memory=False)
        if {'full_name','pick'}.issubset(d.columns):
            d=d.copy(); d['nk']=d['full_name'].map(norm); d['committee_draft_pick']=pd.to_numeric(d['pick'],errors='coerce')
            if 'season' in d:
                yr=pd.to_numeric(d['season'],errors='coerce'); d=d[yr.isin([2025,2026])]
            d=d.sort_values('committee_draft_pick').drop_duplicates('nk',keep='first')
            rr=rr.merge(d[['nk','committee_draft_pick']],on='nk',how='left')
    if 'committee_draft_pick' not in rr: rr['committee_draft_pick']=np.nan
    m=s.merge(rr.drop(columns=['nk']),on=['name','position','team'],how='left',suffixes=('','_committee'))
    elig=m.position.eq('RB') & m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for c in ['rb_committee_optimizer_applied','rb_committee_merit_score','rb_committee_carry_share','rb_committee_target_share','rb_committee_strength','rb_committee_carry_delta','rb_committee_target_delta']:
        m[c]=False if c=='rb_committee_optimizer_applied' else np.nan

    for team,g in m[elig].groupby('team'):
        idx=list(g.index)
        if len(idx)<2: continue
        oldc=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0.).to_numpy(float)
        oldt=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0.).to_numpy(float)
        cb=float(oldc.sum()); tb=float(oldt.sum())
        if cb<=0: continue
        base_c=oldc/cb; base_t=oldt/tb if tb>0 else np.ones(len(idx))/len(idx)

        depths=[]; starters=[]; conf=[]; merits=[]; rec_merits=[]; youth=[]
        for i in idx:
            row=m.loc[i]; dep=max(1,int(num(row.get('depth_rank'),4))); st=bool(row.get('depth_starter',False)); cf=float(np.clip(num(row.get('role_confidence'),.55),0,1))
            rush_talent=float(np.clip(num(row.get('rb_talent_rush_multiplier'),1.),.82,1.18))
            rec_talent=float(np.clip(num(row.get('rb_talent_rec_multiplier'),1.),.82,1.18))
            rel_eff=float(np.clip(num(row.get('rb_relative_efficiency_score'),0.),-2,2))
            draft=draft_score(row.get('committee_draft_pick'))
            rookie=bool(row.get('rookie_committee',row.get('rookie',False))) or row.get('projection_status')=='rookie_model'
            age=num(row.get('rb_age_2026'),np.nan)
            trajectory=.62+.23*draft if rookie else (.58 if np.isfinite(age) and age>=30 else .68)
            depth_component={1:1.0,2:.82,3:.56,4:.34}.get(dep,.22)
            # Rushing merit intentionally gives real weight to efficiency/explosiveness proxies already
            # embedded upstream in rb_relative_efficiency_score and talent multipliers.
            rush_merit=(.30*depth_component+.18*cf+.22*((rush_talent-.82)/.36)+.18*np.clip((rel_eff+2)/4,0,1)+.12*trajectory)
            receive_role=np.clip(num(row.get('role_target_share_2026'),.04)/.12,0,1)
            rec_merit=.28*depth_component+.18*cf+.24*((rec_talent-.82)/.36)+.18*receive_role+.12*trajectory
            depths.append(dep); starters.append(st); conf.append(cf); merits.append(max(.05,rush_merit)); rec_merits.append(max(.05,rec_merit)); youth.append(trajectory)
        merits=np.asarray(merits,float); rec_merits=np.asarray(rec_merits,float)
        merit_c=merits/merits.sum(); merit_t=rec_merits/rec_merits.sum()

        # Committee strength is high when the top two merit scores are close and the nominal RB2 has
        # credible role evidence. This is what lets explosive 1Bs earn share without inventing volume.
        order=np.argsort(-merits); top,second=order[0],order[1]
        closeness=float(np.clip(merits[second]/max(merits[top],1e-9),0,1))
        second_role=float(np.clip(base_c[second]/.35,0,1))
        committee=float(np.clip(.58*closeness+.42*second_role,0,1))

        # In strong committees merit can explain up to 38% of the final carry split; weak committees
        # remain mostly anchored to the existing role projection.
        blend_c=float(np.clip(.10+.28*committee,.10,.38)); blend_t=float(np.clip(.12+.30*committee,.12,.42))
        new_c=(1-blend_c)*base_c+blend_c*merit_c; new_t=(1-blend_t)*base_t+blend_t*merit_t

        # True lead-back concentration: if the depth-chart leader faces weak competition, preserve a
        # meaningful lead. Strong committees do not receive this artificial floor.
        lead=[j for j,(d,st) in enumerate(zip(depths,starters)) if d==1 and st]
        if len(lead)==1:
            k=lead[0]
            floor=float(np.clip(.72-.18*committee,.54,.72))
            if new_c[k]<floor:
                need=floor-new_c[k]; oth=np.arange(len(new_c))!=k; pool=new_c[oth].sum()
                if pool>0: new_c[oth]*=max(0,pool-need)/pool; new_c[k]=floor
            tfloor=float(np.clip(.50-.16*committee,.34,.50))
            if new_t[k]<tfloor:
                need=tfloor-new_t[k]; oth=np.arange(len(new_t))!=k; pool=new_t[oth].sum()
                if pool>0: new_t[oth]*=max(0,pool-need)/pool; new_t[k]=tfloor

        new_c/=new_c.sum(); new_t/=new_t.sum()
        for j,i in enumerate(idx):
            row=m.loc[i]
            nc=cb*new_c[j]; nt=tb*new_t[j]
            oc=max(oldc[j],1e-9); ot=max(oldt[j],1e-9)
            cr=nc/oc if oldc[j]>0 else 1.; tr=nt/ot if oldt[j]>0 else 1.
            # Keep per-opportunity efficiency and scoring rates intact while redistributing opportunity.
            m.at[i,'projected_rush_attempts']=nc
            m.at[i,'projected_rushing_yards']=num(row.get('projected_rushing_yards'),0.)*cr
            m.at[i,'projected_rushing_tds']=num(row.get('projected_rushing_tds'),0.)*cr
            m.at[i,'projected_targets']=nt
            m.at[i,'projected_receptions']=num(row.get('projected_receptions'),0.)*tr
            m.at[i,'projected_receiving_yards']=num(row.get('projected_receiving_yards'),0.)*tr
            m.at[i,'projected_receiving_tds']=num(row.get('projected_receiving_tds'),0.)*tr
            m.at[i,'rb_committee_optimizer_applied']=True; m.at[i,'rb_committee_merit_score']=merits[j]
            m.at[i,'rb_committee_carry_share']=new_c[j]; m.at[i,'rb_committee_target_share']=new_t[j]; m.at[i,'rb_committee_strength']=committee
            m.at[i,'rb_committee_carry_delta']=nc-oldc[j]; m.at[i,'rb_committee_target_delta']=nt-oldt[j]

    for i in m.index[elig]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0)
        m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    drop=[c for c in m.columns if c.endswith('_committee') or c in {'depth_rank','depth_starter','role_confidence','role_carry_share_2026','role_target_share_2026','committee_draft_pick'}]
    m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['Kenneth Walker III','Omarion Hampton','Jeremiyah Love','Jadarian Price','TreVeyon Henderson','Rico Dowdle','Bhayshul Tuten','RJ Harvey','Jordan Mason','Bucky Irving']
    cols=['name','team','projected_rush_attempts','projected_targets','ppr_points','ppr_pos_rank','rb_committee_carry_delta','rb_committee_target_delta','rb_committee_strength']
    print(m[m.name.isin(watch)][[c for c in cols if c in m]].to_dict('records'))

if __name__=='__main__': main()
