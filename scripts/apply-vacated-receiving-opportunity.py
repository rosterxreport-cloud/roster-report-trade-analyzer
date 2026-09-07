#!/usr/bin/env python3
"""Redistribute a conservative portion of vacated 2025 targets to the 2026 depth chart.

Players must now demonstrate target-earning ability to capture a large portion of
vacated opportunity. Established incumbents do not automatically inherit departed
volume simply because they sit atop the depth chart.
"""
from pathlib import Path
import argparse, re, unicodedata
import numpy as np
import pandas as pd

TEAM_ALIAS={"JAX":"JAC","LA":"LAR"}
REDISTRIBUTE=.64
MAX_PLAYER_BONUS=.050
SATURATION_START=.285
SATURATION_HARD=.33


def norm(v):
    t=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
    t=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",t)
    return re.sub(r"[^a-z0-9]","",t)


def saturation(share):
    s=np.asarray(share,dtype=float)
    frac=np.clip((s-SATURATION_START)/(SATURATION_HARD-SATURATION_START),0,1)
    return 1.0-.82*frac


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'))
    ap.add_argument('--features',type=Path,default=Path('data/projections/player_features_2023_2025.csv'))
    ap.add_argument('--out',type=Path,default=Path('data/projections/player_role_context_2026.csv'))
    a=ap.parse_args()
    roles=pd.read_csv(a.roles); f=pd.read_csv(a.features)
    skill=f[(f.season.eq(2025)) & f.position.isin(['RB','WR','TE'])].copy()
    skill['team_norm']=skill['recent_team'].fillna(skill.get('team')).replace(TEAM_ALIAS)
    skill['name_key']=skill['player_display_name'].fillna(skill.get('player_name','')).map(norm)
    skill['targets']=pd.to_numeric(skill.targets,errors='coerce').fillna(0)
    skill['target_share_evidence']=pd.to_numeric(skill.get('target_share'),errors='coerce').fillna(0).clip(0,.40)
    skill['targets_per_game_evidence']=pd.to_numeric(skill.get('targets_per_game'),errors='coerce').fillna(0)
    roles['name_key_vacated']=roles.name.map(norm)
    roles['vacated_target_share_2026']=0.0
    roles['vacated_target_share_team_2026']=0.0
    roles['target_share_saturation_2026']=1.0
    roles['vacated_capture_evidence_2026']=0.0

    evidence=skill[['name_key','target_share_evidence','targets_per_game_evidence']].drop_duplicates('name_key')
    roles=roles.merge(evidence,left_on='name_key_vacated',right_on='name_key',how='left')
    roles['target_share_evidence']=roles['target_share_evidence'].fillna(0)
    roles['targets_per_game_evidence']=roles['targets_per_game_evidence'].fillna(0)

    for team,g in skill.groupby('team_norm'):
        total=g.targets.sum()
        if total<=0: continue
        current=roles[(roles.team_2026.eq(team)) & roles.position.isin(['RB','WR','TE'])]
        if current.empty: continue
        current_keys=set(current.name_key_vacated)
        retained=g[g.name_key.isin(current_keys)].targets.sum()/total
        vacated=max(0.0,1.0-retained)
        pool=vacated*REDISTRIBUTE
        if pool<.01: continue
        idx=current.index
        base=pd.to_numeric(roles.loc[idx,'role_target_share_2026'],errors='coerce').fillna(0).clip(lower=.01)
        starter=roles.loc[idx,'depth_starter'].fillna(False).astype(bool) if 'depth_starter' in roles else pd.Series(False,index=idx)
        rank=pd.to_numeric(roles.loc[idx,'depth_rank'],errors='coerce').fillna(9) if 'depth_rank' in roles else pd.Series(9,index=idx)
        hist_share=pd.to_numeric(roles.loc[idx,'target_share_evidence'],errors='coerce').fillna(0)
        tpg=pd.to_numeric(roles.loc[idx,'targets_per_game_evidence'],errors='coerce').fillna(0)
        sat=pd.Series(saturation(base),index=idx)
        roles.loc[idx,'target_share_saturation_2026']=sat

        # Target-earning evidence: roughly neutral at ~20% share / 6 targets per game,
        # reduced below that range, modestly enhanced for proven high-volume earners.
        share_score=np.clip(hist_share/.20,.35,1.30)
        tpg_score=np.clip(tpg/6.0,.40,1.25)
        earn=.60*share_score+.40*tpg_score
        earn=pd.Series(earn,index=idx).clip(.40,1.25)
        roles.loc[idx,'vacated_capture_evidence_2026']=earn

        role_mult=np.where(starter,1.30,np.where(rank.le(2),1.00,.58))
        weight=base.pow(.72) * role_mult * sat * earn
        weight=pd.Series(weight,index=idx)
        if weight.sum()<=0: continue
        cap=MAX_PLAYER_BONUS*sat*np.clip(earn,.55,1.10)
        bonus=(pool*weight/weight.sum()).clip(upper=cap)
        roles.loc[idx,'role_target_share_2026']=base+bonus
        roles.loc[idx,'vacated_target_share_2026']=bonus
        roles.loc[idx,'vacated_target_share_team_2026']=vacated

    roles=roles.drop(columns=['name_key_vacated','name_key','target_share_evidence','targets_per_game_evidence'],errors='ignore')
    roles.to_csv(a.out,index=False)
    watch=roles[roles.name.isin(['DK Metcalf','Emeka Egbuka',"Ja'Marr Chase",'Parker Washington'])]
    print(watch[['name','team_2026','role_target_share_2026','vacated_target_share_2026','vacated_capture_evidence_2026']].to_dict('records'))
    print(f'Wrote vacated-opportunity roles to {a.out}')

if __name__=='__main__': main()
