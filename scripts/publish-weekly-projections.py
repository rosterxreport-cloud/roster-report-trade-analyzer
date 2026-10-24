#!/usr/bin/env python3
"""Validate the latest weekly master and publish its website snapshot (no model changes)."""
import argparse,csv,json,math,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FIELDS=['Pass_Att','Pass_Yds','Pass_TD','INT','Rush_Att','Rush_Yds','Rush_TD','Targets','Receptions','Rec_Yds','Rec_TD','Standard','Half_PPR','PPR']
def build(source,manifest):
 meta=json.loads(manifest.read_text());week=int(meta['forecast_week'])
 match=re.fullmatch(r'(\d{4})_week(\d+)_league_v4_full.csv',source.name)
 if not match or int(match[2])!=week:raise ValueError('Master and manifest week mismatch')
 players=[];seen=set()
 with source.open(newline='') as f:
  for row in csv.DictReader(f):
   if row['Player'] in seen:raise ValueError('Duplicate player: '+row['Player'])
   seen.add(row['Player'])
   if row['Position'] not in {'QB','RB','WR','TE'}:raise ValueError('Unsupported position')
   p={k:row[k] for k in ['Player','Team','Opponent','Position']}
   for k in FIELDS:
    p[k]=float(row[k])
    if not math.isfinite(p[k]) or p[k]<0:raise ValueError('Invalid '+k)
   if p['Receptions']>p['Targets']+.02:raise ValueError('Receptions exceed targets')
   if p['Position']=='QB':expected=.04*p['Pass_Yds']+4*p['Pass_TD']-2*p['INT']+.1*p['Rush_Yds']+6*p['Rush_TD']
   else:expected=.1*(p['Rush_Yds']+p['Rec_Yds'])+6*(p['Rush_TD']+p['Rec_TD'])+p['Receptions']
   if abs(expected-p['PPR'])>.15:raise ValueError('Scoring mismatch: '+p['Player'])
   p['note']=row.get('Availability_Note','')
   p['starterNote']=row.get('QB_Starter_Assumption','')
   p['snapStatus']=row.get('Snap_Data_Status','')
   players.append(p)
 if len(players)<100:raise ValueError('Incomplete projection pool')
 counts={pos:sum(p['Position']==pos for p in players) for pos in ['QB','RB','WR','TE']}
 if not all(counts.values()):raise ValueError('Missing position')
 if counts!=meta['counts']:raise ValueError('Manifest counts differ from master')
 return {'season':int(match[1]),'week':week,'updatedAt':meta['as_of'],'throughWeek':max(meta['input_weeks']),
 'status':'Preliminary','updateNote':meta.get('update_note',''),'source':str(source.relative_to(ROOT)),
 'conditionalStarters':meta.get('conditional_starters',{}),'counts':counts,'players':players}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source');ap.add_argument('--manifest');a=ap.parse_args()
 if bool(a.source)!=bool(a.manifest):ap.error('Provide source and manifest together')
 if a.source:source=ROOT/a.source;manifest=ROOT/a.manifest
 else:
  candidates=[]
  for m in (ROOT/'data/projections').glob('*_week*_run_manifest.json'):
   x=re.fullmatch(r'(\d{4})_week(\d+)_run_manifest.json',m.name)
   if x:candidates.append((int(x[1]),int(x[2]),m))
  if not candidates:raise ValueError('No weekly run manifest')
  year,week,manifest=max(candidates);source=ROOT/f'data/projections/{year}_week{week}_league_v4_full.csv'
 data=build(source,manifest)
 target=ROOT/'data/weekly-projections.json';target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 print(f'Published {len(data["players"])} players for Week {data["week"]}, {data["season"]}; source timestamp {data["updatedAt"]}')
if __name__=='__main__':main()
