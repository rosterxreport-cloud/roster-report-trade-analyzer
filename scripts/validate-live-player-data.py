#!/usr/bin/env python3
"""Fail-closed validation entry point for generated website data."""
import importlib.util, json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("refresh",root/"scripts/refresh-live-player-data.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.validate(json.loads((root/"players.json").read_text()))
print("players.json passed schema, duplicate, finite-value, Top 250, kicker and D/ST validation")
