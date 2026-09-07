#!/usr/bin/env python3
"""Reconcile same-team WR target hierarchy selectively.

Projection-only layer. Depth position matters most when it agrees with target-earning
evidence. Crowded rooms and weak recent profiles receive little or no WR1 boost.
Team WR target totals are preserved exactly.
"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d

def scale_receiving(m,i,ratio):
    for c in ['projected_targets','projected_receptions','projected_receiving_yards','projected_receiving_tds']:
        if c in m.columns and np.isfinite(num(m.at[i,c])):m.at[i,c]=num(m.at[i,c],0)*ratio

def points(r,rec):
    x=lambda k:num(r.get(k),0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'));ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'));ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv'));a=ap.parse_args()
    s=pd.read_csv(a.stats);r=pd.read_csv(a.roles)
    cols=[c for c in ['name','position','team_2026','depth_rank','depth_starter','role_confidence','target_share','targets_per_game'] if c in r.columns]
    rr=r[cols].copy();m=s.merge(rr,on=['name','position'],how='left',suffixes=('','_depth'))
    m['wr_depth_hierarchy_multiplier']=1.0;m['wr_depth_hierarchy_applied']=False;m['wr_depth_evidence_score']=np.nan;m['wr_room_competition']=np.nan;m['wr_depth_exposure']=np.nan
    eligible=m.position.eq('WR') & m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']);team_key='team' if 'team' in m.columns else 'team_2026'
    for team,g in m[eligible].groupby(team_key):
        idx=g.index
        if len(idx)<2:continue
        cur=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0);total=float(cur.sum())
        if total<=0:continue
        rank=pd.to_numeric(m.loc[idx,'depth_rank'],errors='coerce').fillna(9);starter=m.loc[idx,'depth_starter'].fillna(False).astype(bool);conf=pd.to_numeric(m.loc[idx,'role_confidence'],errors='coerce').fillna(.5).clip(0,1);share=pd.to_numeric(m.loc[idx,'target_share'],errors='coerce').fillna(0).clip(lower=0);tpg=pd.to_numeric(m.loc[idx,'targets_per_game'],errors='coerce').fillna(0).clip(lower=0)
        hist=(.60*(share*30.0)+.40*tpg).clip(lower=.25)
        competition=pd.Series(0.0,index=idx)
        for i in idx:
            peers=[j for j in idx if j!=i and rank.loc[j]<=3]
            if peers:
                peer_share=float(cur.loc[peers].sum()/max(total,1));rook=sum(1 for j in peers if str(m.at[j,'projection_status'])=='rookie_model')
                competition.loc[i]=min(1.0,.72*peer_share+.14*rook)
        # Depth values are modest. WR1 benefit is earned, not automatic.
        depth_base=rank.map({1:1.08,2:1.03,3:.99}).fillna(.95)
        earning_strength=np.clip((hist-3.8)/3.2,0,1)
        crowd_drag=1-.20*competition*(1-earning_strength)
        depth_support=1+(depth_base-1)*earning_strength*crowd_drag
        evidence=hist*depth_support*(.90+.10*conf)*np.where(starter,1.01,1.0)
        current_share=cur/total;desired=evidence/evidence.sum()
        # Dynamic exposure: strong evidence alignment gets a meaningful correction;
        # weak/crowded profiles get very little hierarchy influence.
        exposure=(.04+.14*earning_strength*(1-.55*competition)).clip(.035,.16)
        blended=current_share*(1-exposure)+desired*exposure
        wr1=[i for i in idx if rank.loc[i]==1];wr2=[i for i in idx if rank.loc[i]==2]
        if wr1 and wr2:
            i1,i2=wr1[0],wr2[0];h1,h2=float(hist.loc[i1]),float(hist.loc[i2])
            # Stronger correction only when WR1 also has equal/better earning evidence.
            if h1>=1.03*h2 and blended.loc[i1]<blended.loc[i2]:
                pair=blended.loc[i1]+blended.loc[i2];w2=pair/2.04;blended.loc[i2]=w2;blended.loc[i1]=pair-w2
        new=blended/blended.sum()*total
        for i in idx:
            old=float(cur.loc[i]);nt=float(new.loc[i])
            if old>0:
                # Narrower global cap; crowded weak WR1s can only move a few percent.
                cap=0.045 if (rank.loc[i]==1 and competition.loc[i]>.45 and hist.loc[i]<5.5) else 0.065
                ratio=float(np.clip(nt/old,1-cap,1+cap));scale_receiving(m,i,ratio);m.at[i,'wr_depth_hierarchy_multiplier']=ratio;m.at[i,'wr_depth_hierarchy_applied']=abs(ratio-1)>.005;m.at[i,'wr_depth_evidence_score']=float(evidence.loc[i]);m.at[i,'wr_room_competition']=float(competition.loc[i]);m.at[i,'wr_depth_exposure']=float(exposure.loc[i])
        after=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0)
        if after.sum()>0:
            fix=total/after.sum()
            for i in idx:scale_receiving(m,i,fix);m.at[i,'wr_depth_hierarchy_multiplier']*=fix
    for i in m[eligible].index:
        d=m.loc[i].to_dict();m.at[i,'ppr_points']=points(d,1);m.at[i,'half_ppr_points']=points(d,.5);m.at[i,'standard_points']=points(d,0);m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/17;m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/17;m.at[i,'standard_per_game']=m.at[i,'standard_points']/17
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        m[fmt.replace('_points','_overall_rank')]=m[fmt].rank(method='min',ascending=False);pc=fmt.replace('_points','_pos_rank');m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fmt].notna();m.loc[mask,pc]=m.loc[mask,fmt].rank(method='min',ascending=False)
    drop=['team_2026','depth_rank','depth_starter','role_confidence','target_share','targets_per_game'];m=m.drop(columns=[c for c in drop if c in m.columns],errors='ignore');nums=m.select_dtypes(include=[np.number]).columns;m[nums]=m[nums].round(3);m.to_csv(a.out,index=False)
    watch=m[m.name.isin(['Jerry Jeudy','DJ Moore','Khalil Shakir',"Ja'Marr Chase",'Amon-Ra St. Brown','Jaxon Smith-Njigba'])];print(watch[['name','projected_targets','wr_depth_hierarchy_multiplier','wr_depth_evidence_score','wr_room_competition','wr_depth_exposure','ppr_points','ppr_pos_rank']].sort_values('ppr_pos_rank').to_dict('records'));print('WR depth hierarchy adjusted:',int(m.wr_depth_hierarchy_applied.sum()));print(f'Wrote selectively depth-reconciled projections to {a.out}')
if __name__=='__main__':main()
