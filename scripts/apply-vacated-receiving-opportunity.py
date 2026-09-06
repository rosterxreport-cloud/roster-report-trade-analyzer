#!/usr/bin/env python3
"""Redistribute a conservative portion of vacated 2025 targets to the 2026 depth chart.

This fixes a blind spot where returning players were anchored almost entirely to their
prior target share even after a high-volume teammate left. Only current RB/WR/TE
players with prior-team continuity participate; starters receive most of the vacated
share. The layer changes role_target_share_2026 only, so normal team-budget
reconciliation still controls final targets.
"""
from pathlib import Path
import argparse, re, unicodedata
import numpy as np
import pandas as pd

TEAM_ALIAS={"JAX":"JAC","LA":"LAR"}
REDISTRIBUTE=.72
MAX_PLAYER_BONUS=.055


def norm(v):
    t=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
    t=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",t)
    return re.sub(r"[^a-z0-9]","",t)


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
    roles['name_key_vacated']=roles.name.map(norm)
    roles['vacated_target_share_2026']=0.0
    roles['vacated_target_share_team_2026']=0.0

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
        # Existing involvement is the talent/role prior; confirmed starters get priority.
        weight=base.pow(.75) * np.where(starter,1.45,np.where(rank.le(2),1.05,.55))
        weight=pd.Series(weight,index=idx)
        if weight.sum()<=0: continue
        bonus=(pool*weight/weight.sum()).clip(upper=MAX_PLAYER_BONUS)
        roles.loc[idx,'role_target_share_2026']=base+bonus
        roles.loc[idx,'vacated_target_share_2026']=bonus
        roles.loc[idx,'vacated_target_share_team_2026']=vacated

    roles=roles.drop(columns=['name_key_vacated'])
    roles.to_csv(a.out,index=False)
    watch=roles[roles.name.isin(['Emeka Egbuka','Ladd McConkey','Justin Jefferson'])]
    print(watch[['name','team_2026','role_target_share_2026','vacated_target_share_2026','vacated_target_share_team_2026']].to_dict('records'))
    print(f'Wrote vacated-opportunity roles to {a.out}')

if __name__=='__main__': main()
