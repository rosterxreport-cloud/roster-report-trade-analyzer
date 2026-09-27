#!/usr/bin/env python3
import pandas as pd,numpy as np
from pathlib import Path
# Reproducible QB Week2 residual audit. User-provided inputs are committed separately only if licensed;
# this runner expects CSVs in data/model-inputs/.
base=pd.read_csv("data/model-inputs/qb-full-model-audit-2023-2025.csv")
w1=pd.read_csv("data/model-inputs/passing-statsweek1.csv")
w2=pd.read_csv("data/model-inputs/passing-statsweek_2.csv")
print("BASE",base.columns.tolist());print("W1",w1.columns.tolist());print("W2",w2.columns.tolist())
# Fail loudly rather than fabricate formula/columns.
need=["XTD","INT","HERO%","RPO%"]
missing=[x for x in need if x not in w1.columns]
if missing: raise SystemExit("Missing required Week1 fields: "+str(missing))
raise SystemExit("DEFENSE_INPUT_REQUIRED: add machine-readable 2025 + 2026 Week1 defense CSV before fitting. No proxy or fabricated values permitted.")
