#!/usr/bin/env python3
import json, os, urllib.request, urllib.error
from pathlib import Path

API="https://datawrapper.dwcdn.net"
EDIT="https://api.datawrapper.de/v3"
token=os.environ["DATAWRAPPER_API_TOKEN"]
headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"}

def req(method,path,data=None,raw=False):
    body=data if raw else (json.dumps(data).encode() if data is not None else None)
    h=dict(headers)
    if raw: h["Content-Type"]="text/csv"
    r=urllib.request.Request(EDIT+path,data=body,headers=h,method=method)
    with urllib.request.urlopen(r,timeout=60) as x:
        b=x.read()
        return json.loads(b) if b else {}

players=json.loads(Path("players.json").read_text())
formats=[("half","Half PPR"),("ppr","Full PPR"),("standard","Standard")]
rows=[]
for key,label in formats:
    for p in sorted(players[key],key=lambda x:x.get("rank",999999))[:250]:
        rows.append([p["rank"],p["name"],p["team"],p["pos"],p.get("posRank",""),label,f'{float(p["value"]):.2f}'])

def q(v): return '"'+str(v).replace('"','""')+'"'
csv="Rank,Player,Team,Pos,Pos Rank,Scoring,Trade Value\n"+"\n".join(",".join(q(v) for v in r) for r in rows)

cfg=Path("data/datawrapper-charts.json")
conf=json.loads(cfg.read_text()) if cfg.exists() else {}
cid=conf.get("top250")
if cid:
    try: req("GET",f"/charts/{cid}")
    except Exception: cid=None
if not cid:
    cid=req("POST","/charts",{"title":"2026 Fantasy Football Top 250 Rankings","type":"tables"})["id"]
    conf["top250"]=cid
    cfg.write_text(json.dumps(conf,indent=2)+"\n")

req("PUT",f"/charts/{cid}/data",csv.encode(),raw=True)
meta={
 "title":"The Roster Report's 2026 Fantasy Football Rankings",
 "type":"tables",
 "metadata":{
  "describe":{
   "intro":"Completely sortable by scoring type. Search by player to quickly find anyone in the Top 250.",
   "source-name":"The Roster Report Trade Analyzer",
   "byline":"The Roster Report"
  },
  "visualize":{
   "perPage":25,
   "pagination":True,
   "searchable":True,
   "striped":True,
   "compact":True,
   "sortTable":True,
   "sortBy":"Rank",
   "sortDirection":"asc",
   "columns":{
    "Rank":{"sortable":True,"align":"right","width":0.08},
    "Player":{"sortable":True,"bold":True,"width":0.32},
    "Team":{"sortable":True,"width":0.09},
    "Pos":{"sortable":True,"bold":True,"width":0.08},
    "Pos Rank":{"sortable":True,"align":"right","width":0.10},
    "Scoring":{"sortable":True,"width":0.15},
    "Trade Value":{"sortable":True,"align":"right","bold":True,"number-format":"0.00","width":0.14}
   }
  },
  "publish":{"embed-width":700,"embed-height":900}
 }
}
req("PATCH",f"/charts/{cid}",meta)
pub=req("POST",f"/charts/{cid}/publish")
print(json.dumps({"chartId":cid,"publicUrl":pub.get("url") or f"https://datawrapper.dwcdn.net/{cid}/"}))

# publish refresh
