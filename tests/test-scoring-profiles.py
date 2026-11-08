#!/usr/bin/env python3
import json, math
from pathlib import Path
profiles=json.loads(Path("scoring-profiles.json").read_text());expected={"passingYards","passingTds","rushingTds","receivingTds","rushingFirstDowns","receivingFirstDowns","receptions","baselinePoints","longTds40","longTds50"}
signed_fields={"passingYards","baselinePoints"}
assert profiles,"scoring profile dataset is empty"
for name,profile in profiles.items():
    assert set(profile)==expected,f"unexpected scoring profile schema for {name}"
    for field,value in profile.items():
        assert value is None or (
            isinstance(value,(int,float)) and math.isfinite(value)
            and (field in signed_fields or value>=0)
        ),f"invalid {field} for {name}: {value!r}"
print(f"Validated {len(profiles)} scoring profiles")
