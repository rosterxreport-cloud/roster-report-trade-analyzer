#!/usr/bin/env python3
"""Committee-only RB opportunity optimizer.

Runs after achievability reallocation and before role-decay/aging. It preserves each
team's current RB carry/target budgets, but ONLY activates when the backfield shows
strong evidence of a real committee. Clear lead backs are left untouched. Within true
committees, opportunity can shift toward efficient/explosive/receiving-capable backs
without inventing volume or hard-coding names.
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
    for c in ['rb_committee_optimizer_applied','rb_committee_merit_score','rb_committee_carry_share','rb_committee_target_share','rb_committee_strength','rb_committee_carry_delta','rb_committee_target_delta','rb_committee_gate_passed']:
        m[c]=False if c in {'rb_committee_optimizer_applied','rb_committee_gate_passed'} else np.nan

    for team,g in m[elig].groupby('team'):
        idx=list(g.index)
        if len(idx)<2: continue
        oldc=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0.).to_numpy(float)
        oldt=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0.).to_numpy(float)
        cb=float(oldc.sum()); tb=float(oldt.sum())
        if cb<=0: continue
        base_c=oldc/cb; base_t=oldt/tb if tb>0 else np.ones(len(idx))/len(idx)

        depths=[]; starters=[]; conf=[]; merits=[]; rec_merits=[]
        for i in idx:
            row=m.loc[i]; dep=max(1,int(num(row.get('depth_rank'),4))); st=bool(row.get('depth_starter',False)); cf=float(np.clip(num(row.get('role_confidence'),.55),0,1))
            rush_talent=float(np.clip(num(row.get('rb_talent_rush_multiplier'),1.),.82,1.18))
            rec_talent=float(np.clip(num(row.get('rb_talent_rec_multiplier'),1.),.82,1.18))
            rel_eff=float(np.clip(num(row.get('rb_relative_efficiency_score'),0.),-2,2))
            draft=draft_score(row.get('committee_draft_pick'))
            rookie=bool(row.get('rookie_committee',row.get('rookie',False))) or row.get('projection_status')=='rookie_model'
            age=num(row.get('rb_age_2026'),np.nan)
            trajectory=.62+.23*draft if rookie else (.56 if np.isfinite(age) and age>=30 else .68)
            depth_component={1:1.0,2:.74,3:.46,4:.28}.get(dep,.18)
            # More merit, less depth-chart inertia in true committees.
            rush_merit=(.18*depth_component+.16*cf+.26*((rush_talent-.82)/.36)+.26*np.clip((rel_eff+2)/4,0,1)+.14*trajectory)
            receive_role=np.clip(num(row.get('role_target_share_2026'),.04)/.12,0,1)
            rec_merit=.18*depth_component+.14*cf+.28*((rec_talent-.82)/.36)+.24*receive_role+.16*trajectory
            depths.append(dep); starters.append(st); conf.append(cf); merits.append(max(.05,rush_merit)); rec_merits.append(max(.05,rec_merit))
        merits=np.asarray(merits,float); rec_merits=np.asarray(rec_merits,float)
        order=np.argsort(-merits); top,second=order[0],order[1]
        closeness=float(np.clip(merits[second]/max(merits[top],1e-9),0,1))
        second_c=float(base_c[second]); second_t=float(base_t[second])
        lead_share=float(base_c[top]); lead_tshare=float(base_t[top])
        second_depth=depths[second]
        second_conf=conf[second]

        # STRICT COMMITTEE GATE:
        # - credible RB2 volume already exists, OR
        # - top-two merit is very close and RB2 has current-role support.
        # Clear bell cows (>=68% carries with weak RB2 share) never activate.
        clear_lead = lead_share>=.68 and second_c<.27 and second_t<.25
        volume_committee = second_c>=.30 or second_t>=.30
        merit_committee = closeness>=.84 and second_depth<=2 and second_conf>=.35 and (second_c>=.22 or second_t>=.22)
        gate = (volume_committee or merit_committee) and not clear_lead
        if not gate:
            continue

        m.loc[idx,'rb_committee_gate_passed']=True
        merit_c=merits/merits.sum(); merit_t=rec_merits/rec_merits.sum()
        # Once gated, merit can materially reshape the split.
        committee=float(np.clip(.55*closeness+.30*np.clip(second_c/.40,0,1)+.15*np.clip(second_t/.40,0,1),0,1))
        blend_c=float(np.clip(.24+.24*committee,.24,.48)); blend_t=float(np.clip(.26+.26*committee,.26,.52))
        new_c=(1-blend_c)*base_c+blend_c*merit_c; new_t=(1-blend_t)*base_t+blend_t*merit_t

        # Earned floors for strong RB2s in true committees.
        # These prevent talented backs from collapsing to ~140 carries / 20 targets.
        if second_depth<=2 and closeness>=.82:
            rush_floor=float(np.clip(.30+.08*closeness,.30,.38))
            target_floor=float(np.clip(.24+.10*(rec_merits[second]/max(rec_merits[top],1e-9)),.24,.34))
            if new_c[second]<rush_floor:
                need=rush_floor-new_c[second]; new_c[top]=max(.01,new_c[top]-need); new_c[second]=rush_floor
            if new_t[second]<target_floor:
                need=target_floor-new_t[second]; new_t[top]=max(.01,new_t[top]-need); new_t[second]=target_floor

        # Preserve a nominal RB1 edge unless merit clearly says near-even.
        if new_c[top]<new_c[second]:
            avg=(new_c[top]+new_c[second])/2; new_c[top]=avg+.015; new_c[second]=avg-.015
        new_c/=new_c.sum(); new_t/=new_t.sum()

        for j,i in enumerate(idx):
            row=m.loc[i]
            nc=cb*new_c[j]; nt=tb*new_t[j]
            oc=max(oldc[j],1e-9); ot=max(oldt[j],1e-9)
            cr=nc/oc if oldc[j]>0 else 1.; tr=nt/ot if oldt[j]>0 else 1.
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
    watch=['Christian McCaffrey','Jahmyr Gibbs','Bijan Robinson','De\'Von Achane','Kenneth Walker III','Omarion Hampton','TreVeyon Henderson','Rico Dowdle','Bhayshul Tuten','RJ Harvey','Jordan Mason']
    cols=['name','team','projected_rush_attempts','projected_targets','ppr_points','ppr_pos_rank','rb_committee_gate_passed','rb_committee_carry_delta','rb_committee_target_delta','rb_committee_strength']
    print(m[m.name.isin(watch)][[c for c in cols if c in m]].to_dict('records'))

if __name__=='__main__': main()
