#!/usr/bin/env python3
"""Optimize RB opportunity only after independently classifying a backfield as a true committee.

Committee classification does NOT use the projection being modified. It is driven by current
depth-chart position/confidence, independent 2026 role shares, prior healthy-game usage,
draft capital/trajectory, receiving role, teammate talent and coaching/backfield context.
Once a committee is identified, projected team RB carries/targets are preserved and redistributed
using merit. Clear lead backs remain untouched. No player-specific overrides.
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
    keep=[c for c in ['name','position','team_2026','depth_rank','depth_starter','role_confidence','rookie',
                      'role_carry_share_2026','role_target_share_2026','carries_per_game','targets_per_game',
                      'projected_rush_attempts','projected_pass_attempts'] if c in r]
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
    defaults={'rb_committee_optimizer_applied':False,'rb_committee_gate_passed':False}
    for c in ['rb_committee_optimizer_applied','rb_committee_gate_passed','rb_committee_merit_score','rb_committee_carry_share',
              'rb_committee_target_share','rb_committee_strength','rb_committee_carry_delta','rb_committee_target_delta',
              'rb_committee_evidence_score','rb_committee_second_claim','rb_committee_lead_security']:
        m[c]=defaults.get(c,np.nan)

    for team,g in m[elig].groupby('team'):
        idx=list(g.index)
        if len(idx)<2: continue
        oldc=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0.).to_numpy(float)
        oldt=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0.).to_numpy(float)
        cb=float(oldc.sum()); tb=float(oldt.sum())
        if cb<=0: continue
        base_c=oldc/cb; base_t=oldt/tb if tb>0 else np.ones(len(idx))/len(idx)

        merits=[]; rec_merits=[]; independent=[]; depths=[]; starters=[]; confs=[]; role_cs=[]; role_ts=[]; cpgs=[]; tpgs=[]; picks=[]; rookie_flags=[]
        for i in idx:
            row=m.loc[i]; dep=max(1,int(num(row.get('depth_rank'),4))); st=bool(row.get('depth_starter',False)); cf=float(np.clip(num(row.get('role_confidence'),.55),0,1))
            role_c=float(np.clip(num(row.get('role_carry_share_2026'),.10),0,.90)); role_t=float(np.clip(num(row.get('role_target_share_2026'),.03),0,.35))
            cpg=max(0.,num(row.get('carries_per_game'),0.)); tpg=max(0.,num(row.get('targets_per_game'),0.))
            rush_talent=float(np.clip(num(row.get('rb_talent_rush_multiplier'),1.),.82,1.18)); rec_talent=float(np.clip(num(row.get('rb_talent_rec_multiplier'),1.),.82,1.18))
            rel_eff=float(np.clip(num(row.get('rb_relative_efficiency_score'),0.),-2,2)); pick=num(row.get('committee_draft_pick'),999); ds=draft_score(pick)
            rookie=bool(row.get('rookie_committee',row.get('rookie',False))) or row.get('projection_status')=='rookie_model'
            age=num(row.get('rb_age_2026'),np.nan); trajectory=.64+.24*ds if rookie else (.54 if np.isfinite(age) and age>=30 else .69)
            depth_component={1:1.0,2:.72,3:.44,4:.26}.get(dep,.16)
            rush_merit=.16*depth_component+.14*cf+.28*((rush_talent-.82)/.36)+.28*np.clip((rel_eff+2)/4,0,1)+.14*trajectory
            rec_merit=.16*depth_component+.14*cf+.30*((rec_talent-.82)/.36)+.24*np.clip(role_t/.12,0,1)+.16*trajectory
            # Independent opportunity claim: only contextual/historical evidence; never current projection share.
            hist_c=np.clip(cpg/13.0,0,1); hist_t=np.clip(tpg/4.5,0,1)
            role_c_sig=np.clip(role_c/.35,0,1); role_t_sig=np.clip(role_t/.10,0,1)
            depth_sig={1:1.0,2:.82,3:.48,4:.28}.get(dep,.18)
            current_claim=.25*role_c_sig+.17*role_t_sig+.18*hist_c+.12*hist_t+.12*depth_sig+.08*cf+.08*ds
            if rookie: current_claim += .05*ds
            independent.append(float(np.clip(current_claim,0,1.15)))
            merits.append(max(.05,rush_merit)); rec_merits.append(max(.05,rec_merit)); depths.append(dep); starters.append(st); confs.append(cf); role_cs.append(role_c); role_ts.append(role_t); cpgs.append(cpg); tpgs.append(tpg); picks.append(pick); rookie_flags.append(rookie)

        merits=np.asarray(merits,float); rec_merits=np.asarray(rec_merits,float); independent=np.asarray(independent,float)
        # Identify nominal lead independently: current depth first, then independent claim.
        depth1=[j for j,(d,st) in enumerate(zip(depths,starters)) if d==1 and st]
        lead=depth1[0] if len(depth1)==1 else int(np.argmax(independent))
        others=[j for j in range(len(idx)) if j!=lead]
        second=max(others,key=lambda j: independent[j])
        second_claim=float(independent[second]); lead_claim=float(independent[lead])
        claim_ratio=float(second_claim/max(lead_claim,1e-9))
        merit_ratio=float(merits[second]/max(merits[lead],1e-9))

        # Lead security is independent evidence that the nominal RB1 owns the backfield.
        lead_security=(.27*np.clip(role_cs[lead]/.45,0,1)+.18*np.clip(cpgs[lead]/15,0,1)+.14*np.clip(role_ts[lead]/.10,0,1)+
                       .13*(1.0 if depths[lead]==1 else .35)+.10*confs[lead]+.10*(1-np.clip(second_claim,.0,1))+.08*(1-draft_score(picks[second])))
        # Committee evidence asks whether RB2 has a credible independent workload/talent case.
        committee_evidence=(.30*second_claim+.20*np.clip(claim_ratio,0,1)+.18*np.clip(merit_ratio,0,1)+
                            .12*np.clip(role_cs[second]/.30,0,1)+.08*np.clip(role_ts[second]/.09,0,1)+
                            .07*(1.0 if depths[second]<=2 else .35)+.05*confs[second])
        committee_evidence=float(np.clip(committee_evidence,0,1)); lead_security=float(np.clip(lead_security,0,1))

        # True committee requires substantial independent RB2 evidence AND insufficient lead security.
        strong_second = second_claim>=.46 or (second_claim>=.38 and merit_ratio>=.92) or (role_cs[second]>=.27 and confs[second]>=.45)
        protected_lead = lead_security>=.70 and second_claim<.46
        gate = strong_second and committee_evidence>=.55 and not protected_lead
        m.loc[idx,'rb_committee_evidence_score']=committee_evidence; m.loc[idx,'rb_committee_second_claim']=second_claim; m.loc[idx,'rb_committee_lead_security']=lead_security
        if not gate: continue

        m.loc[idx,'rb_committee_gate_passed']=True
        merit_c=merits/merits.sum(); merit_t=rec_merits/rec_merits.sum()
        # Blend strength is tied to independent committee evidence, not projected share.
        blend_c=float(np.clip(.20+.24*committee_evidence,.20,.44)); blend_t=float(np.clip(.22+.26*committee_evidence,.22,.48))
        new_c=(1-blend_c)*base_c+blend_c*merit_c; new_t=(1-blend_t)*base_t+blend_t*merit_t

        # Strong second backs earn floors only after independent committee classification.
        if depths[second]<=2 and merit_ratio>=.88:
            rush_floor=float(np.clip(.29+.08*merit_ratio,.29,.37)); target_ratio=float(rec_merits[second]/max(rec_merits[lead],1e-9)); target_floor=float(np.clip(.23+.09*target_ratio,.23,.33))
            if new_c[second]<rush_floor:
                need=rush_floor-new_c[second]; new_c[lead]=max(.01,new_c[lead]-need); new_c[second]=rush_floor
            if new_t[second]<target_floor:
                need=target_floor-new_t[second]; new_t[lead]=max(.01,new_t[lead]-need); new_t[second]=target_floor
        if new_c[lead]<new_c[second]:
            avg=(new_c[lead]+new_c[second])/2; new_c[lead]=avg+.0125; new_c[second]=avg-.0125
        new_c/=new_c.sum(); new_t/=new_t.sum()

        for j,i in enumerate(idx):
            row=m.loc[i]; nc=cb*new_c[j]; nt=tb*new_t[j]; oc=max(oldc[j],1e-9); ot=max(oldt[j],1e-9)
            cr=nc/oc if oldc[j]>0 else 1.; tr=nt/ot if oldt[j]>0 else 1.
            m.at[i,'projected_rush_attempts']=nc; m.at[i,'projected_rushing_yards']=num(row.get('projected_rushing_yards'),0.)*cr; m.at[i,'projected_rushing_tds']=num(row.get('projected_rushing_tds'),0.)*cr
            m.at[i,'projected_targets']=nt; m.at[i,'projected_receptions']=num(row.get('projected_receptions'),0.)*tr; m.at[i,'projected_receiving_yards']=num(row.get('projected_receiving_yards'),0.)*tr; m.at[i,'projected_receiving_tds']=num(row.get('projected_receiving_tds'),0.)*tr
            m.at[i,'rb_committee_optimizer_applied']=True; m.at[i,'rb_committee_merit_score']=merits[j]; m.at[i,'rb_committee_carry_share']=new_c[j]; m.at[i,'rb_committee_target_share']=new_t[j]; m.at[i,'rb_committee_strength']=committee_evidence; m.at[i,'rb_committee_carry_delta']=nc-oldc[j]; m.at[i,'rb_committee_target_delta']=nt-oldt[j]

    for i in m.index[elig]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    drop=[c for c in m.columns if c.endswith('_committee') or c in {'depth_rank','depth_starter','role_confidence','role_carry_share_2026','role_target_share_2026','carries_per_game','targets_per_game','committee_draft_pick'}]
    m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['Christian McCaffrey','Jahmyr Gibbs','Bijan Robinson','De\'Von Achane','Kenneth Walker III','Omarion Hampton','TreVeyon Henderson','Rico Dowdle','Bhayshul Tuten','RJ Harvey','Jordan Mason','Bucky Irving','Jeremiyah Love','Jadarian Price']
    cols=['name','team','projected_rush_attempts','projected_targets','ppr_points','ppr_pos_rank','rb_committee_gate_passed','rb_committee_evidence_score','rb_committee_second_claim','rb_committee_lead_security','rb_committee_carry_delta','rb_committee_target_delta']
    print(m[m.name.isin(watch)][[c for c in cols if c in m]].to_dict('records'))

if __name__=='__main__': main()
