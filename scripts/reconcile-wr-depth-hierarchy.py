#!/usr/bin/env python3
"""Reconcile same-team WR target hierarchy with the current depth chart.

Projection-only layer. Current depth rank is treated as meaningful evidence, but
not an absolute ordering rule. A lower-ranked WR may still project for more volume
when his historical target earning is materially stronger. Team WR target totals
are preserved exactly.
"""
from pathlib import Path
import argparse, re, unicodedata
import numpy as np
import pandas as pd


def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t)
    return re.sub(r'[^a-z0-9]','',t)

def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except: return d

def scale_receiving(m,i,ratio):
    for c in ['projected_targets','projected_receptions','projected_receiving_yards','projected_receiving_tds']:
        if c in m.columns and np.isfinite(num(m.at[i,c])):
            m.at[i,c]=num(m.at[i,c],0)*ratio

def points(r,rec):
    x=lambda k:num(r.get(k),0)
    return (.04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+
            .1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+
            .1*x('projected_receiving_yards')+6*x('projected_receiving_tds'))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'))
    ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    a=ap.parse_args()
    s=pd.read_csv(a.stats); r=pd.read_csv(a.roles)
    cols=[c for c in ['name','position','team_2026','depth_rank','depth_starter','role_confidence','target_share','targets_per_game'] if c in r.columns]
    rr=r[cols].copy()
    m=s.merge(rr,on=['name','position'],how='left',suffixes=('','_depth'))
    m['wr_depth_hierarchy_multiplier']=1.0
    m['wr_depth_hierarchy_applied']=False
    m['wr_depth_evidence_score']=np.nan

    eligible=(m.position.eq('WR') & m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']))
    team_key='team' if 'team' in m.columns else 'team_2026'
    for team,g in m[eligible].groupby(team_key):
        idx=g.index
        if len(idx)<2: continue
        cur=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0)
        total=float(cur.sum())
        if total<=0: continue
        rank=pd.to_numeric(m.loc[idx,'depth_rank'],errors='coerce').fillna(9)
        starter=m.loc[idx,'depth_starter'].fillna(False).astype(bool)
        conf=pd.to_numeric(m.loc[idx,'role_confidence'],errors='coerce').fillna(.5).clip(0,1)
        share=pd.to_numeric(m.loc[idx,'target_share'],errors='coerce').fillna(0).clip(lower=0)
        tpg=pd.to_numeric(m.loc[idx,'targets_per_game'],errors='coerce').fillna(0).clip(lower=0)

        # Historical earning evidence, scaled to roughly comparable magnitude.
        hist=(.58*(share*30.0)+.42*tpg).clip(lower=.25)
        # Current depth evidence: WR1 > WR2 > WR3, with starter/confidence support.
        depth_base=rank.map({1:1.30,2:1.10,3:.94}).fillna(.80)
        depth=(depth_base*(.82+.18*conf)*np.where(starter,1.08,1.0))
        evidence=hist*depth

        # Blend the existing projection with the evidence-implied distribution.
        current_share=cur/total
        desired=evidence/evidence.sum()
        blended=.72*current_share+.28*desired

        # Pairwise guardrail: a confirmed WR1 should not sit materially below his
        # WR2 unless the WR2's historical target earning is clearly stronger.
        wr1=[i for i in idx if rank.loc[i]==1]
        wr2=[i for i in idx if rank.loc[i]==2]
        if wr1 and wr2:
            i1,i2=wr1[0],wr2[0]
            h1,h2=float(hist.loc[i1]),float(hist.loc[i2])
            # If WR2 does NOT have >=20% stronger earning evidence, keep WR1 at
            # least within 3% of WR2's target share. This is a soft hierarchy,
            # not a forced ordering.
            if h2 < 1.20*max(h1,.01) and blended.loc[i1] < .97*blended.loc[i2]:
                pair=blended.loc[i1]+blended.loc[i2]
                wr2share=pair/1.97
                blended.loc[i2]=wr2share
                blended.loc[i1]=pair-wr2share

        new=blended/blended.sum()*total
        for i in idx:
            old=float(cur.loc[i]); nt=float(new.loc[i])
            if old>0:
                ratio=nt/old
                # Keep this layer modest; it should reconcile hierarchy, not
                # rewrite the full projection model.
                ratio=float(np.clip(ratio,.88,1.14))
                scale_receiving(m,i,ratio)
                m.at[i,'wr_depth_hierarchy_multiplier']=ratio
                m.at[i,'wr_depth_hierarchy_applied']=abs(ratio-1)>0.005
                m.at[i,'wr_depth_evidence_score']=float(evidence.loc[i])
        # Re-normalize WR targets after clipping so team WR target total is exact.
        after=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0)
        if after.sum()>0:
            fix=total/after.sum()
            for i in idx:
                scale_receiving(m,i,fix)
                m.at[i,'wr_depth_hierarchy_multiplier']*=fix

    # Recompute fantasy points and ranks after receiving-volume changes.
    for i in m[eligible].index:
        d=m.loc[i].to_dict()
        m.at[i,'ppr_points']=points(d,1);m.at[i,'half_ppr_points']=points(d,.5);m.at[i,'standard_points']=points(d,0)
        m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/17.0;m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/17.0;m.at[i,'standard_per_game']=m.at[i,'standard_points']/17.0
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        m[fmt.replace('_points','_overall_rank')]=m[fmt].rank(method='min',ascending=False)
        pc=fmt.replace('_points','_pos_rank');m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fmt].notna();m.loc[mask,pc]=m.loc[mask,fmt].rank(method='min',ascending=False)

    drop=['team_2026','depth_rank','depth_starter','role_confidence','target_share','targets_per_game']
    m=m.drop(columns=[c for c in drop if c in m.columns],errors='ignore')
    nums=m.select_dtypes(include=[np.number]).columns;m[nums]=m[nums].round(3)
    m.to_csv(a.out,index=False)
    watch=m[m.name.isin(['DJ Moore','Khalil Shakir'])]
    print(watch[['name','projected_targets','wr_depth_hierarchy_multiplier','wr_depth_evidence_score','ppr_points','ppr_pos_rank']].to_dict('records'))
    print('WR depth hierarchy adjusted:',int(m.wr_depth_hierarchy_applied.sum()))
    print(f'Wrote depth-reconciled projections to {a.out}')

if __name__=='__main__': main()
