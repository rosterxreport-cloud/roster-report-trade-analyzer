#!/usr/bin/env python3
"""Reconcile same-team WR target hierarchy without letting depth labels overwhelm evidence.

Projection-only layer. Depth position matters, but boosts require target-earning support.
Veterans coming off weak seasons receive smaller depth boosts when meaningful young
competition is present. Team WR target totals are preserved exactly.
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
    cols=[c for c in ['name','position','team_2026','depth_rank','depth_starter','role_confidence','target_share','targets_per_game','age','draft_round','rookie_flag'] if c in r.columns]
    rr=r[cols].copy();m=s.merge(rr,on=['name','position'],how='left',suffixes=('','_depth'))
    m['wr_depth_hierarchy_multiplier']=1.0;m['wr_depth_hierarchy_applied']=False;m['wr_depth_evidence_score']=np.nan;m['wr_room_competition']=np.nan
    eligible=m.position.eq('WR') & m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']);team_key='team' if 'team' in m.columns else 'team_2026'
    for team,g in m[eligible].groupby(team_key):
        idx=g.index
        if len(idx)<2:continue
        cur=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0);total=float(cur.sum())
        if total<=0:continue
        rank=pd.to_numeric(m.loc[idx,'depth_rank'],errors='coerce').fillna(9);starter=m.loc[idx,'depth_starter'].fillna(False).astype(bool);conf=pd.to_numeric(m.loc[idx,'role_confidence'],errors='coerce').fillna(.5).clip(0,1);share=pd.to_numeric(m.loc[idx,'target_share'],errors='coerce').fillna(0).clip(lower=0);tpg=pd.to_numeric(m.loc[idx,'targets_per_game'],errors='coerce').fillna(0).clip(lower=0)
        # Recent production quality: target earning plus how efficiently the player converted
        # his projected baseline opportunity. This prevents depth rank alone from creating stars.
        hist=(.58*(share*30.0)+.42*tpg).clip(lower=.25)
        rec_yards=pd.to_numeric(m.loc[idx,'projected_receiving_yards'],errors='coerce').fillna(0);rec_tds=pd.to_numeric(m.loc[idx,'projected_receiving_tds'],errors='coerce').fillna(0);recs=pd.to_numeric(m.loc[idx,'projected_receptions'],errors='coerce').fillna(0)
        baseline_ppr=(recs+.1*rec_yards+6*rec_tds).clip(lower=1);quality=(baseline_ppr/(cur.clip(lower=1))).clip(.65,1.35)
        # Competition score from other top-three depth players. Rookie-model teammates count
        # as meaningful competition because the rookie model already incorporates draft capital.
        competition=pd.Series(0.0,index=idx)
        for i in idx:
            peers=[j for j in idx if j!=i and rank.loc[j]<=3]
            if peers:
                peer_cur=cur.loc[peers].sum()/max(total,1);peer_rook=sum(1 for j in peers if str(m.at[j,'projection_status'])=='rookie_model')
                competition.loc[i]=min(1.0,.70*peer_cur+.15*peer_rook)
        # Depth advantage is deliberately modest and conditional on evidence quality.
        depth_base=rank.map({1:1.12,2:1.05,3:.98}).fillna(.92)
        support=(.55+.45*np.clip(hist/6.5,.45,1.15))*(.88+.12*conf)*np.where(starter,1.025,1.0)
        # Weak target earners in crowded rooms lose most of the nominal WR1 boost.
        crowd_penalty=1-.16*competition*np.clip((6.0-hist)/3.0,0,1)
        evidence=hist*quality*depth_base*support*crowd_penalty
        current_share=cur/total;desired=evidence/evidence.sum()
        # Reduce global exposure from 28% to 15%; this layer is a guardrail, not a re-projection.
        blended=.85*current_share+.15*desired
        wr1=[i for i in idx if rank.loc[i]==1];wr2=[i for i in idx if rank.loc[i]==2]
        if wr1 and wr2:
            i1,i2=wr1[0],wr2[0];h1,h2=float(hist.loc[i1]),float(hist.loc[i2])
            # Only reconcile an inversion when WR1 has at least comparable earning evidence.
            # Do not force a weak WR1 ahead merely because of the label.
            if h1>=.90*h2 and blended.loc[i1]<.97*blended.loc[i2]:
                pair=blended.loc[i1]+blended.loc[i2];w2=pair/1.97;blended.loc[i2]=w2;blended.loc[i1]=pair-w2
        new=blended/blended.sum()*total
        for i in idx:
            old=float(cur.loc[i]);nt=float(new.loc[i])
            if old>0:
                # Tighter cap prevents elite incumbents from being inflated by a hierarchy pass.
                ratio=float(np.clip(nt/old,.93,1.07));scale_receiving(m,i,ratio);m.at[i,'wr_depth_hierarchy_multiplier']=ratio;m.at[i,'wr_depth_hierarchy_applied']=abs(ratio-1)>.005;m.at[i,'wr_depth_evidence_score']=float(evidence.loc[i]);m.at[i,'wr_room_competition']=float(competition.loc[i])
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
    drop=['team_2026','depth_rank','depth_starter','role_confidence','target_share','targets_per_game','age','draft_round','rookie_flag'];m=m.drop(columns=[c for c in drop if c in m.columns],errors='ignore');nums=m.select_dtypes(include=[np.number]).columns;m[nums]=m[nums].round(3);m.to_csv(a.out,index=False)
    watch=m[m.name.isin(['Jerry Jeudy','DJ Moore','Khalil Shakir',"Ja'Marr Chase",'Amon-Ra St. Brown','Jaxon Smith-Njigba'])];print(watch[['name','projected_targets','wr_depth_hierarchy_multiplier','wr_depth_evidence_score','wr_room_competition','ppr_points','ppr_pos_rank']].sort_values('ppr_pos_rank').to_dict('records'));print('WR depth hierarchy adjusted:',int(m.wr_depth_hierarchy_applied.sum()));print(f'Wrote tempered depth-reconciled projections to {a.out}')
if __name__=='__main__':main()
