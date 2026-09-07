#!/usr/bin/env python3
"""Final WR target-growth guardrail.

Audits projected targets against the player's 2025 17-game target pace. Growth above
20% must be supported by target-earning strength, sustainable breakout evidence and
an uncrowded 2026 room. Poor prior-year efficiency and premium rookie competition
reduce the allowable growth. Team WR target totals are preserved exactly.
"""
from pathlib import Path
import argparse, re, unicodedata
import numpy as np
import pandas as pd

GAMES=17.0
TEAM_ALIAS={'JAX':'JAC','LA':'LAR'}


def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t)
    return re.sub(r'[^a-z0-9]','',t)


def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d


def scale_receiving(m,i,ratio):
    for c in ['projected_targets','projected_receptions','projected_receiving_yards','projected_receiving_tds']:
        if c in m.columns and np.isfinite(num(m.at[i,c])):
            m.at[i,c]=num(m.at[i,c],0)*ratio


def points(r,rec):
    x=lambda k:num(r.get(k),0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'))
    ap.add_argument('--features',type=Path,default=Path('data/projections/player_features_2023_2025.csv'))
    ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    a=ap.parse_args()
    s=pd.read_csv(a.stats); r=pd.read_csv(a.roles); f=pd.read_csv(a.features)

    # 2025 veteran evidence, including efficiency that should affect whether volume expands.
    fw=f[(pd.to_numeric(f.season,errors='coerce').eq(2025)) & f.position.eq('WR')].copy()
    fw['name_key']=fw.player_display_name.fillna(fw.get('player_name','')).map(norm)
    fw['team_key']=fw.recent_team.fillna(fw.get('team')).replace(TEAM_ALIAS)
    for c in ['games','targets_per_game','target_share','yards_per_target','catch_rate','receiving_epa_per_target']:
        fw[c]=pd.to_numeric(fw.get(c),errors='coerce')
    hist=fw[['name_key','team_key','games','targets_per_game','target_share','yards_per_target','catch_rate','receiving_epa_per_target']].drop_duplicates('name_key')

    rolecols=[c for c in ['name','position','team_2026','depth_rank','depth_starter','changed_team'] if c in r.columns]
    rr=r[rolecols].copy(); rr['name_key']=rr.name.map(norm); rr['team_key']=rr.team_2026.replace(TEAM_ALIAS)
    rr=rr.merge(hist,on='name_key',how='left',suffixes=('','_hist'))
    m=s.merge(rr.drop(columns=['name_key']),on=['name','position'],how='left',suffixes=('','_guard'))

    eligible=m.position.eq('WR') & m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    m['target_growth_guardrail_applied']=False
    m['target_growth_prev_17']=np.nan
    m['target_growth_rate_2026']=np.nan
    m['target_growth_allowed_2026']=np.nan
    m['target_growth_evidence']=np.nan
    m['prior_efficiency_score']=np.nan
    m['premium_rookie_competitors']=0
    m['competition_adjusted_target_cap']=np.nan

    team_key='team' if 'team' in m.columns else 'team_2026'
    for team,g in m[eligible].groupby(team_key):
        idx=g.index
        cur=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0)
        total=float(cur.sum())
        if total<=0: continue
        rank=pd.to_numeric(m.loc[idx,'depth_rank'],errors='coerce').fillna(9)
        status=m.loc[idx,'projection_status'].astype(str)
        rookie_top3=[j for j in idx if status.loc[j]=='rookie_model' and rank.loc[j]<=3]
        room_comp=pd.to_numeric(m.loc[idx,'wr_room_competition'],errors='coerce').fillna(0) if 'wr_room_competition' in m.columns else pd.Series(0.0,index=idx)
        changed=m.loc[idx,'changed_team'].fillna(False).astype(bool) if 'changed_team' in m.columns else pd.Series(False,index=idx)

        caps={}
        for i in idx:
            games=num(m.at[i,'games'],0); tpg=num(m.at[i,'targets_per_game'],0); share=num(m.at[i,'target_share'],0)
            if status.loc[i]=='rookie_model' or games<8 or tpg<=0:
                continue
            prev17=tpg*GAMES
            growth=cur.loc[i]/prev17-1 if prev17>0 else np.nan
            ypt=num(m.at[i,'yards_per_target'],6.8); catch=num(m.at[i,'catch_rate'],.58); epa=num(m.at[i,'receiving_epa_per_target'],.08)
            ypt_s=float(np.clip((ypt-5.5)/3.5,0,1)); catch_s=float(np.clip((catch-.48)/.22,0,1)); epa_s=float(np.clip((epa+.10)/.45,0,1))
            efficiency=.50*ypt_s+.25*catch_s+.25*epa_s
            share_s=float(np.clip(share/.24,.35,1.25)); tpg_s=float(np.clip(tpg/7.0,.35,1.25)); earned=.58*share_s+.42*tpg_s
            confirmed=bool(m.at[i,'confirmed_role_breakout']) if 'confirmed_role_breakout' in m.columns and pd.notna(m.at[i,'confirmed_role_breakout']) else False
            breakout=bool(m.at[i,'recent_role_breakout']) if 'recent_role_breakout' in m.columns and pd.notna(m.at[i,'recent_role_breakout']) else False
            sustain=num(m.at[i,'breakout_sustainability'],1.0) if breakout else 1.0
            rookie_comp=sum(1 for j in rookie_top3 if j!=i)
            allowed=.20
            allowed+=.10*float(np.clip((earned-.85)/.35,0,1))
            allowed+=.10*(1 if confirmed else 0)*float(np.clip(sustain,.55,1.10))
            allowed+=.04*(1 if (breakout and not confirmed) else 0)*float(np.clip(sustain,.55,1.10))
            allowed+=.06*(1 if (changed.loc[i] and rank.loc[i]==1 and room_comp.loc[i]<.35) else 0)
            allowed-=.10*float(np.clip(room_comp.loc[i],0,1))
            allowed-=min(.10,.05*rookie_comp)
            allowed-=.07*float(np.clip((.45-efficiency)/.45,0,1))
            allowed=float(np.clip(allowed,.10,.45))
            cap=prev17*(1+allowed)
            m.at[i,'target_growth_prev_17']=prev17; m.at[i,'target_growth_rate_2026']=growth; m.at[i,'target_growth_allowed_2026']=allowed
            m.at[i,'target_growth_evidence']=earned; m.at[i,'prior_efficiency_score']=efficiency; m.at[i,'premium_rookie_competitors']=rookie_comp; m.at[i,'competition_adjusted_target_cap']=cap
            if np.isfinite(growth) and growth>.20 and cur.loc[i]>cap:
                caps[i]=cap

        # Cap unsupported growth, then redistribute only to teammates without violating
        # their own known veteran cap; rookies/no-history players may absorb based on role.
        excess=0.0
        for i,cap in caps.items():
            old=float(cur.loc[i]); new=float(cap)
            if old<=0 or new>=old: continue
            scale_receiving(m,i,new/old); excess+=old-new; m.at[i,'target_growth_guardrail_applied']=True

        if excess>1e-6:
            after=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0)
            receivers=[j for j in idx if j not in caps]
            capacity={}
            for j in receivers:
                old=float(after.loc[j])
                if old<=0: continue
                own_cap=num(m.at[j,'competition_adjusted_target_cap'],np.nan)
                if np.isfinite(own_cap): room=max(0.0,own_cap-old)
                else: room=max(8.0,.35*old)
                if room>0: capacity[j]=room
            if capacity:
                weights=pd.Series({j:max(1.0,float(after.loc[j]))*(1.15 if rank.loc[j]<=2 else .85) for j in capacity})
                for _ in range(3):
                    if excess<=1e-6 or not capacity: break
                    w=weights.loc[list(capacity)].copy(); w=w/w.sum(); moved=0.0
                    for j,share_w in w.items():
                        add=min(capacity[j],excess*float(share_w))
                        old=num(m.at[j,'projected_targets'],0)
                        if add>0 and old>0:
                            scale_receiving(m,j,(old+add)/old); capacity[j]-=add; moved+=add
                    excess-=moved; capacity={j:v for j,v in capacity.items() if v>1e-6}
                    if moved<=1e-6: break
        # If a tiny remainder cannot be reassigned within guardrails, leave it unallocated;
        # the broader team target budget is a ceiling, not a requirement to force volume.

    for i in m[eligible].index:
        d=m.loc[i].to_dict();m.at[i,'ppr_points']=points(d,1);m.at[i,'half_ppr_points']=points(d,.5);m.at[i,'standard_points']=points(d,0);m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES;m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES;m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        m[fmt.replace('_points','_overall_rank')]=m[fmt].rank(method='min',ascending=False);pc=fmt.replace('_points','_pos_rank');m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fmt].notna();m.loc[mask,pc]=m.loc[mask,fmt].rank(method='min',ascending=False)

    drop=['team_2026','depth_rank','depth_starter','changed_team','team_key','team_key_hist','games','targets_per_game','target_share','yards_per_target','catch_rate','receiving_epa_per_target']
    m=m.drop(columns=[c for c in drop if c in m.columns],errors='ignore')
    nums=m.select_dtypes(include=[np.number]).columns;m[nums]=m[nums].round(3);m.to_csv(a.out,index=False)
    audit=m[eligible & (pd.to_numeric(m.target_growth_rate_2026,errors='coerce')>.20)][['name','team','projected_targets','target_growth_prev_17','target_growth_rate_2026','target_growth_allowed_2026','target_growth_evidence','prior_efficiency_score','premium_rookie_competitors','target_growth_guardrail_applied','ppr_points','ppr_pos_rank']].sort_values('target_growth_rate_2026',ascending=False)
    print('WR target growth >20% audit:',audit.to_dict('records'))
    print('Guardrail adjustments:',int(m.target_growth_guardrail_applied.sum()))
    print(f'Wrote competition-adjusted projections to {a.out}')

if __name__=='__main__':main()
