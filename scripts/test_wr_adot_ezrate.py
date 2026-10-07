#!/usr/bin/env python3
import pandas as pd, numpy as np, re
def norm(x): return re.sub(r'[^a-z0-9]','',str(x).lower())
base=pd.read_csv('data/backtests/wr_alpha010/player_results.csv')
base=base[(base.week==4)&(base.position=='WR')].copy()
adv=pd.read_csv('data/backtests/inputs/receiving-statswk3.csv',header=[0,1])
adv.columns=[b if str(b)!='nan' and not str(b).startswith('Unnamed') else a for a,b in adv.columns]
# Parsed Fantasy Points export: second header row contains canonical labels.
def col(name):
 for x in adv.columns:
  if str(x).strip()==name:return x
 raise KeyError((name,list(adv.columns)))
namec=col('Name'); adotc=col('aDOT'); tgtc=col('TGT'); ezc=col('EZTGT')
a=adv[[namec,adotc,tgtc,ezc]].copy();a.columns=['adv_name','adot','tgt','eztgt']
for x in ['adot','tgt','eztgt']:a[x]=pd.to_numeric(a[x],errors='coerce')
a['join']=a.adv_name.map(norm)
base['join']=(base.player_display_name if 'player_display_name' in base else base.player_name).map(norm)
m=base.merge(a,on='join',how='left')
print('matched',m.adot.notna().sum(),'of',len(m))
# exact baseline recalculated from stored predictions
baseline=(m.v4_ppr-m.actual_ppr).abs().mean();print('BASELINE',baseline)
# aDOT modifies only receiving YPT around 8.0; sweep conservative slopes.
for beta in [0.05,0.10,0.15,0.20,0.30,0.40]:
 ypt=np.clip(8.0+beta*(m.adot.fillna(10.0)-10.0),5.0,12.0)
 pred=m.v4_ppr + m.pred_targets*(ypt-8.0)*.1
 mae=(pred-m.actual_ppr).abs().mean()
 print('ADOT',beta,mae)
# End-zone target rate modifies only TD/target around fixed .045.
rate=(m.eztgt/m.tgt.replace(0,np.nan)).clip(0,.5)
center=rate.dropna().mean()
for beta in [0.025,0.05,0.075,0.10,0.15,0.20]:
 td_rate=np.clip(.045+beta*(rate.fillna(center)-center),.015,.10)
 pred=m.v4_ppr + m.pred_targets*(td_rate-.045)*6
 mae=(pred-m.actual_ppr).abs().mean()
 print('EZRATE',beta,mae)
print('EZ_CENTER',center)
