#!/usr/bin/env python3
"""One-time creator for the immutable v10 core baseline used by refreshes."""
import json
from pathlib import Path
source=json.loads(Path("players.json").read_text());core={}
for scoring,rows in source.items():
    core[scoring]={p["name"]:{"rank":p["rank"],"value":p["value"],"analyticsScore":p["analyticsScore"]} for p in rows if p["pos"] in {"QB","RB","WR","TE"}}
Path("data/live-refresh-baseline.json").write_text(json.dumps(core,indent=2,ensure_ascii=False)+"\n")
print("Wrote immutable v10 offensive-player refresh baseline")
