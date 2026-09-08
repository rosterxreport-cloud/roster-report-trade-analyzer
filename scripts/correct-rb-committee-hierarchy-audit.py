#!/usr/bin/env python3
"""Normalize the RB committee hierarchy audit ratio.

The diagnostic is defined as challenger hierarchy strength relative to the designated
RB1, bounded to [0, 1]. A challenger that grades above the designated RB1 therefore
reports 1.0 (full parity) rather than an impossible >1 share-style ratio.
This is audit-only and does not change projected workload or fantasy points.
"""
from pathlib import Path
import numpy as np
import pandas as pd

P = Path('data/projections/stat_projections_2026.csv')


def main():
    df = pd.read_csv(P)
    col = 'rb_committee_hierarchy_ratio'
    if col not in df.columns:
        raise SystemExit(f'Missing {col}')
    raw = pd.to_numeric(df[col], errors='coerce')
    df['rb_committee_hierarchy_ratio_raw'] = raw
    df[col] = raw.clip(lower=0.0, upper=1.0)
    df['rb_committee_hierarchy_ratio_corrected'] = raw.notna() & ((raw < 0.0) | (raw > 1.0))
    df.to_csv(P, index=False)
    corrected = df[df['rb_committee_hierarchy_ratio_corrected']]
    print('RB_HIERARCHY_RATIO_CORRECTIONS', corrected[['name','team',col,'rb_committee_hierarchy_ratio_raw']].to_dict('records'))
    rbs = df[(df['position'] == 'RB') & df['projection_status'].isin(['modeled_veteran','returning_fallback','rookie_model'])].copy()
    rbs = rbs.sort_values('ppr_points', ascending=False).head(40)
    cols = [c for c in ['name','team','projected_rush_attempts','projected_targets','ppr_points','ppr_pos_rank','rb_committee_tier',col] if c in rbs.columns]
    print('RB_TOP_40', rbs[cols].to_dict('records'))


if __name__ == '__main__':
    main()
