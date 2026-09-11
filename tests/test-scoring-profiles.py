#!/usr/bin/env python3
import json, math
from pathlib import Path
profiles=json.loads(Path("scoring-profiles.json").read_text());expected={"passingYards","passingTds","rushingTds","receivingTds","rushingFirstDowns","receivingFirstDowns","receptions","baselinePoints","longTds40","longTds50"}
assert profiles,"scoring profile dataset is empty"
for name,profile in profiles.items():
    assert set(profile)==expected,f"unexpected scoring profile schema for {name}"
    assert all(value is None or isinstance(value,(int,float)) and math.isfinite(value) and value>=0 for value in profile.values()),f"invalid scoring profile value for {name}"
print(f"Validated {len(profiles)} scoring profiles")
