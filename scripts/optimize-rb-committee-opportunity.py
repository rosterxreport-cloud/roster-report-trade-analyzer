#!/usr/bin/env python3
"""RB committee optimizer.
A talented RB2 may earn complementary work, but true-committee status requires independent hierarchy evidence.
"""
from pathlib import Path
import re, unicodedata
import numpy as np, pandas as pd
STATS=Path('data/projections/stat_projections_2026.csv'); ROLES=Path('data/projections/player_role_context_2026.csv'); DRAFT=Path('data/projections/draft_picks_normalized.csv'); GAMES=17.
def num(v,d=np.nan):
    try:x=float(v); return x if np.isfinite(x) else d
    except:return d
def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower(); t=re.sub(r'\b(jr|sr|ii|iii|iv|v)\.?\b','',t); return re.sub(r'[^a-z0-9]','',t)
def score(r,rec=1.):
    x=lambda k:num(r.get(k),0.); return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')
def draft_score(p):
    p=num(p,999); return 1. if p<=32 else .82 if p<=64 else .62 if p<=120 else .42 if p<=180 else .25 if p<=257 else .10
def main():
    s=pd.read_csv(STATS); r=pd.read_csv(ROLES); keep=[c for c in ['name','position','team_2026','depth_rank','depth_starter','role_confidence','rookie','role_carry_share_2026','role_target_share_2026','carries_per_game','targets_per_game'] if c in r]; rr=r[keep].rename(columns={'team_2026':'team'}).copy(); rr['nk']=rr.name.map(norm)
    if DRAFT.exists():
        d=pd.read_csv(DRAFT,low_memory=False)
        if {'full_name','pick'}.issubset(d):
            d['nk']=d.full_name.map(norm); d['committee_draft_pick']=pd.to_numeric(d.pick,errors='coerce')
            if 'season' in d:d=d[pd.to_numeric(d.season,errors='coerce').isin([2025,2026])]
            d=d.sort_values('committee_draft_pick').drop_duplicates('nk'); rr=rr.merge(d[['nk','committee_draft_pick']],on='nk',how='left')
    if 'committee_draft_pick' not in rr:rr['committee_draft_pick']=np.nan
    m=s.merge(rr.drop(columns='nk'),on=['name','position','team'],how='left',suffixes=('','_committee')); elig=m.position.eq('RB')&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for c in ['rb_committee_optimizer_applied','rb_committee_gate_passed']:m[c]=False
    for c in ['rb_committee_merit_score','rb_committee_carry_share','rb_committee_target_share','rb_committee_strength','rb_committee_carry_delta','rb_committee_target_delta','rb_committee_evidence_score','rb_committee_second_claim','rb_committee_lead_security','rb_committee_response_strength','rb_committee_rb1_protection_score','rb_committee_continuous_protection','rb_committee_effective_evidence','rb_committee_hierarchy_evidence','rb_committee_max_carry_loss_rate','rb_committee_max_target_loss_rate','rb_committee_rb2_hierarchy_score','rb_committee_rb2_talent_score']:m[c]=np.nan
    m['rb_committee_tier']='clear_lead'; m['rb_committee_rb1_protected']=False
    for team,g in m[elig].groupby('team'):
        idx=list(g.index)
        if len(idx)<2:continue
        oldc=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0).to_numpy(float); oldt=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0).to_numpy(float); cb=oldc.sum(); tb=oldt.sum()
        if cb<=0:continue
        basec=oldc/cb; baset=oldt/tb if tb>0 else np.ones(len(idx))/len(idx); merits=[]; rmer=[]; claims=[]; hier=[]; depths=[]; starters=[]; confs=[]; rcs=[]; rts=[]; cpgs=[]; tpgs=[]; picks=[]; floors=[]
        for i in idx:
            row=m.loc[i]; dep=max(1,int(num(row.get('depth_rank'),4))); st=bool(row.get('depth_starter',False)); cf=np.clip(num(row.get('role_confidence'),.55),0,1); rc=np.clip(num(row.get('role_carry_share_2026'),.10),0,.9); rt=np.clip(num(row.get('role_target_share_2026'),.03),0,.35); cpg=max(0,num(row.get('carries_per_game'),0)); tpg=max(0,num(row.get('targets_per_game'),0)); rush=np.clip(num(row.get('rb_talent_rush_multiplier'),1),.82,1.18); rec=np.clip(num(row.get('rb_talent_rec_multiplier'),1),.82,1.18); eff=np.clip(num(row.get('rb_relative_efficiency_score'),0),-2,2); pick=num(row.get('committee_draft_pick'),999); ds=draft_score(pick); rookie=bool(row.get('rookie_committee',row.get('rookie',False))) or row.get('projection_status')=='rookie_model'; age=num(row.get('rb_age_2026'),np.nan); traj=.64+.24*ds if rookie else (.54 if np.isfinite(age) and age>=30 else .69); depth={1:1.,2:.72,3:.44,4:.26}.get(dep,.16)
            talent=max(.05,.16*depth+.14*cf+.28*((rush-.82)/.36)+.28*np.clip((eff+2)/4,0,1)+.14*traj); merits.append(talent); rmer.append(max(.05,.16*depth+.14*cf+.30*((rec-.82)/.36)+.24*np.clip(rt/.12,0,1)+.16*traj)); claims.append(np.clip(.25*np.clip(rc/.35,0,1)+.17*np.clip(rt/.10,0,1)+.18*np.clip(cpg/13,0,1)+.12*np.clip(tpg/4.5,0,1)+.12*({1:1.,2:.82,3:.48,4:.28}.get(dep,.18))+.08*cf+.08*ds+(.05*ds if rookie else 0),0,1.15))
            # Hierarchy evidence deliberately excludes efficiency/talent. A good backup is not automatically a co-lead.
            hier.append(np.clip(.30*np.clip(rc/.35,0,1)+.20*np.clip(cpg/13,0,1)+.15*np.clip(rt/.10,0,1)+.10*np.clip(tpg/4.5,0,1)+.12*({1:1.,2:.72,3:.36,4:.18}.get(dep,.10))+.08*cf+.05*ds,0,1))
            depths.append(dep); starters.append(st); confs.append(cf); rcs.append(rc); rts.append(rt); cpgs.append(cpg); tpgs.append(tpg); picks.append(pick); floors.append(np.clip(num(row.get('rb_vacated_floor_strength'),0),0,1))
        merits=np.array(merits); rmer=np.array(rmer); claims=np.array(claims); hier=np.array(hier); depth1=[j for j,(d,st) in enumerate(zip(depths,starters)) if d==1 and st]; lead=depth1[0] if len(depth1)==1 else int(np.argmax(hier)); others=[j for j in range(len(idx)) if j!=lead]; second=max(others,key=lambda j:hier[j]); sc=float(claims[second]); hs=float(hier[second]); lh=float(hier[lead]); hratio=hs/max(lh,1e-9); mr=float(merits[second]/max(merits[lead],1e-9)); security=np.clip(.30*np.clip(rcs[lead]/.45,0,1)+.18*np.clip(cpgs[lead]/15,0,1)+.14*np.clip(rts[lead]/.10,0,1)+.15*(1 if depths[lead]==1 else .35)+.11*confs[lead]+.12*(1-hs),0,1)
        evidence=np.clip(.38*hs+.24*np.clip(hratio,0,1)+.14*np.clip(rcs[second]/.30,0,1)+.09*np.clip(rts[second]/.09,0,1)+.08*(1 if depths[second]<=2 else .30)+.07*confs[second],0,1)
        protection=np.clip(.28*(depths[lead]==1)+.20*starters[lead]+.20*confs[lead]+.16*np.clip(rcs[lead]/.50,0,1)+.10*np.clip(rts[lead]/.12,0,1)+.06*floors[lead],0,1); cp=float(np.clip((protection-.42)/.48,0,1)); effective_evidence=float(np.clip(evidence*(1-.48*cp),0,1)); challenge=float(np.clip(.50*hs+.25*hratio+.15*evidence+.10*np.clip(sc,0,1),0,1)); hurdle=.60+.22*cp
        # True committee requires hierarchy parity. Talent/efficiency can strengthen a 1B role but cannot create co-lead status by itself.
        true=(hs>=.52 and hratio>=.76 and evidence>=.58 and security<.67 and challenge>=hurdle and effective_evidence>=.40); oneb=(not true) and ((hs>=.34 and evidence>=.44) or (depths[second]<=2 and hs>=.30 and mr>=.88)) and security<.86; tier='true_committee' if true else ('lead_plus_1b' if oneb else 'clear_lead'); protected=cp>=.50
        hierarchy=np.clip(num(m.at[idx[lead],'rb_lead_evidence_score'],0),0,1) if 'rb_lead_evidence_score' in m else 0.; max_loss_rate=float(np.clip(.16-.13*hierarchy,.03,.16)); max_target_loss=float(np.clip(.18-.12*hierarchy,.05,.18))
        m.loc[idx,'rb_committee_evidence_score']=evidence; m.loc[idx,'rb_committee_effective_evidence']=effective_evidence; m.loc[idx,'rb_committee_second_claim']=sc; m.loc[idx,'rb_committee_lead_security']=security; m.loc[idx,'rb_committee_rb1_protection_score']=protection; m.loc[idx,'rb_committee_continuous_protection']=cp; m.loc[idx,'rb_committee_rb1_protected']=protected; m.loc[idx,'rb_committee_tier']=tier; m.loc[idx,'rb_committee_hierarchy_evidence']=hierarchy; m.loc[idx,'rb_committee_max_carry_loss_rate']=max_loss_rate; m.loc[idx,'rb_committee_max_target_loss_rate']=max_target_loss; m.loc[idx,'rb_committee_rb2_hierarchy_score']=hs; m.loc[idx,'rb_committee_rb2_talent_score']=mr
        if tier=='clear_lead':continue
        m.loc[idx,'rb_committee_gate_passed']=True; mc=merits/merits.sum(); mt=rmer/rmer.sum(); damp=1-.68*cp
        if tier=='lead_plus_1b':bc=np.clip((.055+.065*evidence)*damp,.02,.11); bt=np.clip((.07+.075*evidence)*damp,.025,.14); maxcl=min((.065*(1-.65*cp)+.015),max_loss_rate)*oldc[lead]; maxtl=min((.085*(1-.65*cp)+.02),max_target_loss)*oldt[lead]
        else:bc=np.clip((.24+.26*evidence)*damp,.08,.50); bt=np.clip((.26+.28*evidence)*damp,.09,.54); maxcl=min((.32*(1-.58*cp)+.05),max_loss_rate)*oldc[lead]; maxtl=min((.36*(1-.58*cp)+.06),max_target_loss)*oldt[lead]
        nc=(1-bc)*basec+bc*mc; nt=(1-bt)*baset+bt*mt
        if tier=='true_committee' and depths[second]<=2 and mr>=.88:
            rf=np.clip((.30+.08*mr)*(1-.30*cp),.22,.38); tr=np.clip((.24+.09*(rmer[second]/max(rmer[lead],1e-9)))*(1-.28*cp),.18,.34)
            if nc[second]<rf:need=rf-nc[second]; nc[lead]=max(.01,nc[lead]-need); nc[second]=rf
            if nt[second]<tr:need=tr-nt[second]; nt[lead]=max(.01,nt[lead]-need); nt[second]=tr
        nc/=nc.sum(); nt/=nt.sum(); minc=max(0,oldc[lead]-maxcl)/cb; mint=max(0,oldt[lead]-maxtl)/tb if tb>0 else nt[lead]
        if nc[lead]<minc:
            add=minc-nc[lead]; pool=sum(nc[j] for j in others)
            if pool>0:
                for j in others:nc[j]-=add*nc[j]/pool
                nc[lead]=minc
        if tb>0 and nt[lead]<mint:
            add=mint-nt[lead]; pool=sum(nt[j] for j in others)
            if pool>0:
                for j in others:nt[j]-=add*nt[j]/pool
                nt[lead]=mint
        nc=np.clip(nc,.001,None); nt=np.clip(nt,.001,None); nc/=nc.sum(); nt/=nt.sum(); m.loc[idx,'rb_committee_response_strength']=max(bc,bt)
        for j,i in enumerate(idx):
            row=m.loc[i]; c=cb*nc[j]; t=tb*nt[j]; cr=c/max(oldc[j],1e-9) if oldc[j]>0 else 1; tr=t/max(oldt[j],1e-9) if oldt[j]>0 else 1; m.at[i,'projected_rush_attempts']=c; m.at[i,'projected_rushing_yards']=num(row.get('projected_rushing_yards'),0)*cr; m.at[i,'projected_rushing_tds']=num(row.get('projected_rushing_tds'),0)*cr; m.at[i,'projected_targets']=t; m.at[i,'projected_receptions']=num(row.get('projected_receptions'),0)*tr; m.at[i,'projected_receiving_yards']=num(row.get('projected_receiving_yards'),0)*tr; m.at[i,'projected_receiving_tds']=num(row.get('projected_receiving_tds'),0)*tr; m.at[i,'rb_committee_optimizer_applied']=True; m.at[i,'rb_committee_merit_score']=merits[j]; m.at[i,'rb_committee_carry_share']=nc[j]; m.at[i,'rb_committee_target_share']=nt[j]; m.at[i,'rb_committee_strength']=evidence; m.at[i,'rb_committee_carry_delta']=c-oldc[j]; m.at[i,'rb_committee_target_delta']=t-oldt[j]
    for i in m.index[elig]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    m=m.drop(columns=[c for c in m if c.endswith('_committee') or c in {'depth_rank','depth_starter','role_confidence','role_carry_share_2026','role_target_share_2026','carries_per_game','targets_per_game','committee_draft_pick'}],errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['Bhayshul Tuten','TreVeyon Henderson','Rico Dowdle','Jeremiyah Love','Jadarian Price','Kenneth Walker III','Jahmyr Gibbs']; cols=['name','team','projected_rush_attempts','projected_targets','ppr_points','ppr_pos_rank','rb_committee_tier','rb_committee_rb2_hierarchy_score','rb_committee_rb2_talent_score','rb_committee_hierarchy_evidence','rb_committee_carry_delta','rb_committee_target_delta']; print('RB_COMMITTEE_AUDIT',m[m.name.isin(watch)][cols].to_dict('records'))
if __name__=='__main__':main()
