#!/usr/bin/env python3
"""Normalize nflverse draft-pick columns for projection consumers."""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd

DEFAULT_SOURCE="https://github.com/nflverse/nflverse-data/releases/download/draft_picks/draft_picks.csv"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default=DEFAULT_SOURCE)
    ap.add_argument("--out",type=Path,default=Path("data/projections/draft_picks_normalized.csv"))
    a=ap.parse_args()
    df=pd.read_csv(a.source,low_memory=False)
    rename={}
    if "pfr_name" in df.columns and "full_name" not in df.columns: rename["pfr_name"]="full_name"
    if "year" in df.columns and "season" not in df.columns: rename["year"]="season"
    if "overall" in df.columns and "pick" not in df.columns: rename["overall"]="pick"
    df=df.rename(columns=rename)
    required=["season","team","round","pick","full_name","position"]
    missing=[c for c in required if c not in df.columns]
    if missing: raise RuntimeError(f"Draft source missing required columns: {missing}; got {list(df.columns)}")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(a.out,index=False)
    print("Draft columns:",list(df.columns))
    print("2026 draft rows:",int(pd.to_numeric(df["season"],errors="coerce").eq(2026).sum()))
    print(f"Wrote {a.out}")

if __name__=="__main__": main()
