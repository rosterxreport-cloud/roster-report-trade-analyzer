#!/usr/bin/env python3
"""Adjust 2026 WR/TE opportunity using late-2025 target earning windows.

Projection-only layer. Ordinary recent improvement still uses bounded multipliers.
Confirmed structural breakouts instead establish a new 2026 target-share baseline by
regressing late-season share toward full-season share, then rebuilding the team target
allocation around that baseline while preserving the team's target budget.
"""
from pathlib import Path
import argparse, re, unicodedata
import numpy as np
import pandas as pd

WEEKLY_URL='https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2025.csv'
GAMES=17.0
TEAM_ALIAS={'JAX':'JAC','LA':'LAR'}


def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t)
    return re.sub(r'[^a-z0-9]','',t)


def num(v,d=np.nan):
    try:
        x=float(v);return x if np.isfinite(x) else d
    except:return d


def scale(m,idx,ratio):
    for c in ['projected_targets','projected_receptions','projected_receiving_yards','projected_receiving_tds']:
        if c in m.columns and np.isfinite(num(m.at[idx,c])):
            m.at[idx,c]=num(m.at[idx,c],0)*ratio


def pts(r,rec):
    x=lambda k:num(r.get(k),0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')


def window_features(w,weeks,suffix):
    z=w[w.week.isin(weeks)].copy()
    if z.empty:return pd.DataFrame(columns=['name_key','team_key'])
    agg=z.groupby(['name_key','team_key'],dropna=False).agg(
        targets=('targets','sum'),games=('week','nunique'),target_share=('target_share','mean')
    ).reset_index()
    agg[f'tpg_{suffix}']=agg.targets/agg.games.where(agg.games>0)
    agg=agg.rename(columns={'target_share':f'share_{suffix}'})
    return agg[['name_key','team_key',f'tpg_{suffix}',f'share_{suffix}']]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'))
    ap.add_argument('--weekly-source',default=WEEKLY_URL)
    ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    a=ap.parse_args()

    s=pd.read_csv(a.stats);r=pd.read_csv(a.roles);w=pd.read_csv(a.weekly_source,low_memory=False)
    if 'season_type' in w.columns:w=w[w.season_type.eq('REG')]
    w=w[w.position.isin(['WR','TE'])].copy()
    w['targets']=pd.to_numeric(w.targets,errors='coerce').fillna(0)
    w['target_share']=pd.to_numeric(w.get('target_share'),errors='coerce')
    w['name_key']=w['player_display_name'].fillna(w.get('player_name','')).map(norm)
    teamcol='recent_team' if 'recent_team' in w.columns else 'team'
    w['team_key']=w[teamcol].replace(TEAM_ALIAS)

    maxw=int(pd.to_numeric(w.week,errors='coerce').max())
    windows={'l8':range(max(1,maxw-7),maxw+1),'l6':range(max(1,maxw-5),maxw+1),'l4':range(max(1,maxw-3),maxw+1)}
    feat=None
    for suf,weeks in windows.items():
        f=window_features(w,weeks,suf)
        feat=f if feat is None else feat.merge(f,on=['name_key','team_key'],how='outer')

    cols=[c for c in ['name','position','team_2026','targets_per_game','target_share','depth_starter','depth_rank'] if c in r.columns]
    rr=r[cols].copy();rr['name_key']=rr.name.map(norm);rr['team_key']=rr.team_2026.replace(TEAM_ALIAS);rr=rr.merge(feat,on=['name_key','team_key'],how='left')
    m=s.merge(rr.drop(columns=['name_key','team_key']),on=['name','position'],how='left',suffixes=('','_recent'))
    eligible=m.projection_status.isin(['modeled_veteran','returning_fallback']) & m.position.isin(['WR','TE'])
    m['recent_role_breakout']=False;m['confirmed_role_breakout']=False;m['recent_role_multiplier']=1.0;m['recent_role_score']=np.nan;m['breakout_target_share_baseline']=np.nan

    for team,g in m[eligible].groupby('team'):
        idx=g.index;cur=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0)
        if cur.sum()<=0:continue
        season_tpg=pd.to_numeric(m.loc[idx,'targets_per_game'],errors='coerce').fillna(0)
        season_share=pd.to_numeric(m.loc[idx,'target_share'],errors='coerce').fillna(0)
        l8t=pd.to_numeric(m.loc[idx,'tpg_l8'],errors='coerce').fillna(season_tpg)
        l6t=pd.to_numeric(m.loc[idx,'tpg_l6'],errors='coerce').fillna(l8t)
        l4t=pd.to_numeric(m.loc[idx,'tpg_l4'],errors='coerce').fillna(l6t)
        l8s=pd.to_numeric(m.loc[idx,'share_l8'],errors='coerce').fillna(season_share)
        l6s=pd.to_numeric(m.loc[idx,'share_l6'],errors='coerce').fillna(l8s)
        l4s=pd.to_numeric(m.loc[idx,'share_l4'],errors='coerce').fillna(l6s)
        starter=m.loc[idx,'depth_starter'].fillna(False).astype(bool)
        rank=pd.to_numeric(m.loc[idx,'depth_rank'],errors='coerce').fillna(9)

        tpg_recent=.30*l8t+.40*l6t+.30*l4t
        share_recent=.30*l8s+.40*l6s+.30*l4s
        tpg_growth=(tpg_recent/season_tpg.replace(0,np.nan)).replace([np.inf,-np.inf],np.nan).fillna(1)
        share_growth=(share_recent/season_share.replace(0,np.nan)).replace([np.inf,-np.inf],np.nan).fillna(1)
        sustained=.45*tpg_growth+.55*share_growth
        role_ok=starter|rank.le(2)
        breakout=role_ok & ((share_growth.ge(1.22)&tpg_growth.ge(1.12)) | (share_growth.ge(1.12)&tpg_growth.ge(1.28))) & l6t.ge(4.0)
        confirmed=role_ok & breakout & l6t.ge(5.5) & l8t.ge(4.75) & l6s.ge(.22) & l4s.ge(.20) & l4t.ge(.80*l6t)

        current_share=cur/cur.sum()
        new_share=current_share.copy()

        # Confirmed breakouts create a new baseline instead of receiving only a multiplier.
        # Blend 70% recent role with 30% full-season role, then regress 18% toward a
        # positionally neutral 20% share so a four-to-eight game heater is not treated as
        # a permanent 30% alpha role. Cap at 30% before team reconciliation.
        baseline=(.70*share_recent+.30*season_share)
        baseline=.82*baseline+.18*.20
        baseline=baseline.clip(lower=.10,upper=.30)
        baseline=pd.Series(baseline,index=idx)

        confirmed_idx=idx[confirmed.to_numpy()]
        if len(confirmed_idx):
            for i in confirmed_idx:
                new_share.loc[i]=baseline.loc[i]
                m.at[i,'breakout_target_share_baseline']=float(baseline.loc[i])

            # Reallocate the remainder proportionally across non-breakout teammates.
            confirmed_total=float(new_share.loc[confirmed_idx].sum())
            other_idx=idx.difference(confirmed_idx)
            remaining=max(.01,1.0-confirmed_total)
            if len(other_idx):
                other_cur=current_share.loc[other_idx]
                if other_cur.sum()>0:new_share.loc[other_idx]=remaining*other_cur/other_cur.sum()

        # Ordinary breakouts/improvement still get a bounded recent-role nudge.
        nonconfirmed=~confirmed
        season_score=.55*season_tpg+.45*(season_share*30.0)
        recent_score=.55*tpg_recent+.45*(share_recent*30.0)
        score=pd.Series(.72*season_score+.28*recent_score,index=idx).clip(lower=.25)
        desired=score/score.sum()
        blended=.82*new_share+.18*desired
        for j,i in enumerate(idx):
            if confirmed.iloc[j]:continue
            max_mult=1.32 if breakout.iloc[j] else 1.16
            min_mult=.88 if breakout.iloc[j] else .86
            base=current_share.loc[i]
            candidate=blended.loc[i]
            if base>0:new_share.loc[i]=base*np.clip(candidate/base,min_mult,max_mult)

        # Convert target shares back to the existing team target budget.
        new_share=new_share.clip(lower=.001)
        new_share/=new_share.sum()
        new=cur.sum()*new_share

        for j,i in enumerate(idx):
            old=num(m.at[i,'projected_targets'],0);nt=float(new.loc[i])
            if old>0:
                ratio=nt/old;scale(m,i,ratio)
                m.at[i,'recent_role_multiplier']=ratio
                m.at[i,'recent_role_breakout']=bool(breakout.iloc[j])
                m.at[i,'confirmed_role_breakout']=bool(confirmed.iloc[j])
                m.at[i,'recent_role_score']=float(sustained.iloc[j])

    for i in m[eligible].index:
        d=m.loc[i].to_dict();m.at[i,'ppr_points']=pts(d,1);m.at[i,'half_ppr_points']=pts(d,.5);m.at[i,'standard_points']=pts(d,0);m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES;m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES;m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        m[fmt.replace('_points','_overall_rank')]=m[fmt].rank(method='min',ascending=False);pc=fmt.replace('_points','_pos_rank');m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fmt].notna();m.loc[mask,pc]=m.loc[mask,fmt].rank(method='min',ascending=False)

    drop=['team_2026','targets_per_game','target_share','depth_starter','depth_rank','tpg_l8','share_l8','tpg_l6','share_l6','tpg_l4','share_l4']
    m=m.drop(columns=[c for c in drop if c in m.columns],errors='ignore')
    nums=m.select_dtypes(include=[np.number]).columns;m[nums]=m[nums].round(3);m.to_csv(a.out,index=False)
    watch=m[m.name.isin(['Parker Washington','Jakobi Meyers','Brian Thomas Jr.'])]
    print(watch[['name','projected_targets','confirmed_role_breakout','breakout_target_share_baseline','recent_role_multiplier','ppr_points','ppr_pos_rank']].sort_values('ppr_pos_rank').to_dict('records'))
    print('Recent-role breakouts:',int(m.recent_role_breakout.sum()),'confirmed:',int(m.confirmed_role_breakout.sum()))
    print(f'Wrote recent-role projections to {a.out}')

if __name__=='__main__':main()
