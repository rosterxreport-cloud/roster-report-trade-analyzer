#!/usr/bin/env python3
import json, os, urllib.request
from pathlib import Path
EDIT="https://api.datawrapper.de/v3"
headers={"Authorization":f'Bearer {os.environ["DATAWRAPPER_API_TOKEN"]}',"Content-Type":"application/json"}
def req(method,path,data=None,raw=False):
 body=data if raw else (json.dumps(data).encode() if data is not None else None)
 h=dict(headers)
 if raw:h["Content-Type"]="text/csv"
 with urllib.request.urlopen(urllib.request.Request(EDIT+path,data=body,headers=h,method=method),timeout=60) as x:
  b=x.read(); return json.loads(b) if b else {}
players=json.loads(Path("players.json").read_text())
fmts=[("half","Half-PPR"),("ppr","Full-PPR"),("standard","Standard")]
by={}
def live_default_rankings(lst):
 backs=sorted((p for p in lst if p["pos"]=="RB"),key=lambda p:(-p["value"],p["rank"]))
 rb_rank={p["name"]:i+1 for i,p in enumerate(backs)}
 adjusted=[]
 for p in lst:
  r=rb_rank.get(p["name"],999)
  premium=.03 if p["pos"]=="RB" and r<=12 else (.015 if p["pos"]=="RB" and r<=24 else 0)
  q=dict(p); q["_value"]=round(p["value"]*(1+premium),2); q["_baseRank"]=p["rank"]
  adjusted.append(q)
 adjusted.sort(key=lambda p:(-p["_value"],p["_baseRank"]))
 return [(i,p) for i,p in enumerate(adjusted,1)]

for key,label in fmts:
 for live_rank,p in live_default_rankings(players[key]):
  n=p["name"]; d=by.setdefault(n,{"Player":n,"Team":p["team"],"Pos":p["pos"]})
  d[label]=live_rank
# one player per row; include union of ranked players, ordered by Half-PPR
rows=sorted(by.values(),key=lambda x:(x.get("Half-PPR",9999),x["Player"]))[:250]
def q(v):return '"'+str(v if v is not None else "").replace('"','""')+'"'
cols=["Player","Team","Pos","Half-PPR","Full-PPR","Standard"]
csv=",".join(cols)+"\n"+"\n".join(",".join(q(r.get(k,"")) for k in cols) for r in rows)
cfg=Path("data/datawrapper-charts.json"); conf=json.loads(cfg.read_text()) if cfg.exists() else {}
# lock this redesigned Top 250 to the current chart
cid=conf.get("top250") or "cSE5i"; conf["top250"]=cid; cfg.write_text(json.dumps(conf,indent=2)+"\n")
req("PUT",f"/charts/{cid}/data",csv.encode(),raw=True)
meta={"title":"The Roster Report's 2026 Fantasy Football Rankings","type":"tables","metadata":{
"describe":{"intro":"Search any player. Click Half-PPR, Full-PPR, or Standard to sort the Top 250 for that scoring format.","source-name":"The Roster Report Trade Analyzer","byline":"The Roster Report"},
"visualize":{"perPage":25,"pagination":True,"searchable":True,"striped":False,"compact":True,"sortTable":True,"sortBy":"Half-PPR","sortDirection":"asc","columns":{
"Player":{"sortable":True,"bold":True,"width":0.36},"Team":{"sortable":True,"width":0.10},"Pos":{"sortable":True,"bold":True,"width":0.09},
"Half-PPR":{"sortable":True,"align":"center","width":0.15},"Full-PPR":{"sortable":True,"align":"center","width":0.15},"Standard":{"sortable":True,"align":"center","width":0.15}}},"publish":{"embed-width":700,"embed-height":900}}}
req("PATCH",f"/charts/{cid}",meta); pub=req("POST",f"/charts/{cid}/publish")
print(json.dumps({"chartId":cid,"publicUrl":pub.get("url") or f"https://datawrapper.dwcdn.net/{cid}/"}))

# rerun live-rank sync
