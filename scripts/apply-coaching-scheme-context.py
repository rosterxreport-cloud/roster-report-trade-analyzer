#!/usr/bin/env python3
"""Apply bounded 2026 offensive coaching/play-caller context to projections.

The existing projection is treated as the personnel/team baseline. This layer adds
only a bounded coaching tendency adjustment using the actual 2026 play-caller and
his recent scheme history. It affects team pass volume and RB/WR/TE target mix,
then lets all downstream player-level hierarchy, availability, efficiency and TD
layers operate normally.

Historical tendencies are calculated from 2023-25 nflverse team/player data.
Low-confidence first-time callers are intentionally shrunk heavily toward neutral.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

GAMES = 17.0
MAX_TEAM_VOL = 0.06
MAX_POS_SHARE = 0.07
MAX_WR_CONC_TOP = 0.04
MAX_WR_CONC_OTHER = 0.02


def num(v, d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except (TypeError, ValueError): return d


def parse_specs(text):
    out=[]
    for part in str(text or '').split(';'):
        if not part.strip(): continue
        bits=part.split(':')
        if len(bits)!=3: continue
        try: out.append((bits[0], int(bits[1]), float(bits[2])))
        except: pass
    total=sum(x[2] for x in out)
    return [(t,s,w/total) for t,s,w in out] if total>0 else []


def points(r, rec):
    x=lambda k:num(r.get(k),0.0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+\
           .1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+\
           .1*x('projected_receiving_yards')+6*x('projected_receiving_tds')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'))
    ap.add_argument('--team-features',type=Path,default=Path('data/projections/team_features_2023_2025.csv'))
    ap.add_argument('--player-features',type=Path,default=Path('data/projections/player_features_2023_2025.csv'))
    ap.add_argument('--config',type=Path,default=Path('data/coaching_scheme_2026.csv'))
    ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    a=ap.parse_args()

    s=pd.read_csv(a.stats); roles=pd.read_csv(a.roles); tf=pd.read_csv(a.team_features); pf=pd.read_csv(a.player_features); cfg=pd.read_csv(a.config)
    cfg['team']=cfg['team'].replace({'JAX':'JAC','LA':'LAR'})
    tf['team']=tf['team'].replace({'JAX':'JAC','LA':'LAR'})
    if 'recent_team' in pf: pf['team_hist']=pf['recent_team'].replace({'JAX':'JAC','LA':'LAR'})
    else: pf['team_hist']=pf['team'].replace({'JAX':'JAC','LA':'LAR'})

    # Build season-relative team tendency metrics so era/season environment is removed.
    tf['attempts']=pd.to_numeric(tf.get('attempts'),errors='coerce')
    tf['pass_rate_proxy']=pd.to_numeric(tf.get('pass_rate_proxy'),errors='coerce')
    tf['attempt_index']=tf['attempts']/tf.groupby('season')['attempts'].transform('mean')
    tf['pass_rate_index']=tf['pass_rate_proxy']/tf.groupby('season')['pass_rate_proxy'].transform('mean')

    skill=pf[pf.position.isin(['RB','WR','TE'])].copy()
    skill['targets']=pd.to_numeric(skill.get('targets'),errors='coerce').fillna(0)
    pos=skill.groupby(['season','team_hist','position'])['targets'].sum().unstack(fill_value=0).reset_index()
    for p in ['RB','WR','TE']:
        if p not in pos: pos[p]=0.0
    pos['skill_targets']=pos[['RB','WR','TE']].sum(axis=1).replace(0,np.nan)
    for p in ['RB','WR','TE']:
        pos[f'{p.lower()}_share']=pos[p]/pos['skill_targets']
        season_mean=pos.groupby('season')[f'{p.lower()}_share'].transform('mean')
        pos[f'{p.lower()}_share_index']=pos[f'{p.lower()}_share']/season_mean

    wr=skill[skill.position.eq('WR')].copy()
    wr_team=wr.groupby(['season','team_hist'])['targets'].sum().rename('wr_targets')
    wr_max=wr.groupby(['season','team_hist'])['targets'].max().rename('wr1_targets')
    wc=pd.concat([wr_team,wr_max],axis=1).reset_index()
    wc['wr1_concentration']=wc['wr1_targets']/wc['wr_targets'].replace(0,np.nan)
    wc['wr_concentration_index']=wc['wr1_concentration']/wc.groupby('season')['wr1_concentration'].transform('mean')

    hist=tf.merge(pos,left_on=['season','team'],right_on=['season','team_hist'],how='left').merge(wc,left_on=['season','team'],right_on=['season','team_hist'],how='left',suffixes=('','_wr'))

    records=[]
    for _,c in cfg.iterrows():
        specs=parse_specs(c.history_specs); conf=float(np.clip(num(c.confidence,0),0,1)); new=bool(int(num(c.new_play_caller,0)))
        vals=[]
        for team,season,w in specs:
            team={'JAX':'JAC','LA':'LAR'}.get(team,team)
            h=hist[(hist.team.eq(team)) & (hist.season.eq(season))]
            if h.empty: continue
            row=h.iloc[0]
            vals.append((w,row))
        if not vals:
            rec={'team':c.team,'play_caller':c.play_caller,'new_play_caller':new,'coaching_confidence':conf,
                 'coach_pass_volume_index':1.0,'coach_pass_rate_index':1.0,'coach_rb_target_index':1.0,
                 'coach_wr_target_index':1.0,'coach_te_target_index':1.0,'coach_wr_concentration_index':1.0}
        else:
            sw=sum(w for w,_ in vals); avg=lambda col: sum(w*num(r.get(col),1.0) for w,r in vals)/sw
            rec={'team':c.team,'play_caller':c.play_caller,'new_play_caller':new,'coaching_confidence':conf,
                 'coach_pass_volume_index':avg('attempt_index'),'coach_pass_rate_index':avg('pass_rate_index'),
                 'coach_rb_target_index':avg('rb_share_index'),'coach_wr_target_index':avg('wr_share_index'),
                 'coach_te_target_index':avg('te_share_index'),'coach_wr_concentration_index':avg('wr_concentration_index')}
        records.append(rec)
    coach=pd.DataFrame(records)

    # Baseline is already personnel-aware; coaching is an incremental 25-35% signal.
    coach['coach_weight']=np.where(coach.new_play_caller,.35,.25)*coach.coaching_confidence
    raw=.55*(coach.coach_pass_volume_index-1)+.45*(coach.coach_pass_rate_index-1)
    coach['coaching_team_volume_multiplier']=(1+coach.coach_weight*raw).clip(1-MAX_TEAM_VOL,1+MAX_TEAM_VOL)
    for p in ['rb','wr','te']:
        coach[f'coaching_{p}_share_multiplier']=(1+coach.coach_weight*.75*(coach[f'coach_{p}_target_index']-1)).clip(1-MAX_POS_SHARE,1+MAX_POS_SHARE)
    coach.to_csv('data/projections/coaching_scheme_context_2026.csv',index=False)

    eligible=s.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for col in ['coaching_play_caller','coaching_confidence','coaching_team_volume_multiplier','coaching_position_share_multiplier','coaching_wr_concentration_multiplier','coaching_scheme_multiplier']:
        s[col]=np.nan if col!='coaching_play_caller' else ''

    for _,cr in coach.iterrows():
        team=cr.team; idx=s.index[eligible & s.team.eq(team) & s.position.isin(['RB','WR','TE'])]
        if len(idx)==0: continue
        before=pd.to_numeric(s.loc[idx,'projected_targets'],errors='coerce').fillna(0).copy()
        vol=float(cr.coaching_team_volume_multiplier)
        posmult=pd.Series(1.0,index=idx)
        for p in ['RB','WR','TE']:
            pidx=s.index.intersection(idx)[s.loc[idx,'position'].eq(p).values]
            if len(pidx): posmult.loc[pidx]=float(cr[f'coaching_{p.lower()}_share_multiplier'])
        conc=pd.Series(1.0,index=idx)
        wridx=s.index.intersection(idx)[s.loc[idx,'position'].eq('WR').values]
        if len(wridx):
            wr_targets=before.loc[wridx]
            top=wr_targets.idxmax()
            d=float(cr.coach_wr_concentration_index)-1
            w=float(cr.coach_weight)
            conc.loc[top]=float(np.clip(1+w*.35*d,1-MAX_WR_CONC_TOP,1+MAX_WR_CONC_TOP))
            others=[x for x in wridx if x!=top]
            if others:
                other=float(np.clip(1-w*.12*d,1-MAX_WR_CONC_OTHER,1+MAX_WR_CONC_OTHER))
                conc.loc[others]=other
        raw_mult=vol*posmult*conc
        proposed=before*raw_mult
        # Keep total receiving opportunity under the current team pass-attempt budget.
        rteam=roles[roles.team_2026.eq(team)]
        if len(rteam) and pd.to_numeric(rteam.get('projected_pass_attempts'),errors='coerce').notna().any():
            budget=float(pd.to_numeric(rteam.projected_pass_attempts,errors='coerce').dropna().iloc[0])*.961
            other_idx=s.index[eligible & s.team.eq(team) & s.position.isin(['RB','WR','TE']) & ~s.index.isin(idx)]
            other_total=pd.to_numeric(s.loc[other_idx,'projected_targets'],errors='coerce').fillna(0).sum() if len(other_idx) else 0
            room=max(0,budget-other_total)
            if proposed.sum()>room and proposed.sum()>0: proposed*=room/proposed.sum()
        ratio=(proposed/before.replace(0,np.nan)).replace([np.inf,-np.inf],np.nan).fillna(1.0)
        s.loc[idx,'projected_targets']=proposed
        for stat in ['projected_receptions','projected_receiving_yards','projected_receiving_tds']:
            s.loc[idx,stat]=pd.to_numeric(s.loc[idx,stat],errors='coerce').fillna(0)*ratio
        s.loc[idx,'coaching_play_caller']=cr.play_caller
        s.loc[idx,'coaching_confidence']=cr.coaching_confidence
        s.loc[idx,'coaching_team_volume_multiplier']=vol
        s.loc[idx,'coaching_position_share_multiplier']=posmult
        s.loc[idx,'coaching_wr_concentration_multiplier']=conc
        s.loc[idx,'coaching_scheme_multiplier']=ratio

    # Re-score/rank after scheme adjustment; downstream layers will re-score again.
    for idx,r in s[eligible].iterrows():
        d=s.loc[idx].to_dict(); s.at[idx,'ppr_points']=points(d,1); s.at[idx,'half_ppr_points']=points(d,.5); s.at[idx,'standard_points']=points(d,0)
        s.at[idx,'ppr_per_game']=s.at[idx,'ppr_points']/GAMES; s.at[idx,'half_ppr_per_game']=s.at[idx,'half_ppr_points']/GAMES; s.at[idx,'standard_per_game']=s.at[idx,'standard_points']/GAMES
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        s[fmt.replace('_points','_overall_rank')]=s[fmt].rank(method='min',ascending=False); pc=fmt.replace('_points','_pos_rank'); s[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=s.position.eq(p)&s[fmt].notna(); s.loc[mask,pc]=s.loc[mask,fmt].rank(method='min',ascending=False)
    nums=s.select_dtypes(include=[np.number]).columns; s[nums]=s[nums].round(4); s.to_csv(a.out,index=False)
    watch=s[s.name.isin(['Chris Olave','Garrett Wilson','Jaylen Waddle','A.J. Brown','DK Metcalf','Jameson Williams'])]
    print(watch[['name','team','coaching_play_caller','coaching_team_volume_multiplier','coaching_position_share_multiplier','coaching_scheme_multiplier','projected_targets']].to_dict('records'))
    print(f'Coaching contexts: {len(coach)} teams; new play-callers: {int(coach.new_play_caller.sum())}')
    print(f'Wrote coaching-adjusted projections to {a.out}')

if __name__=='__main__': main()
