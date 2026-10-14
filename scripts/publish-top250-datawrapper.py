#!/usr/bin/env python3
"""Create and publish a NEW Datawrapper Top 250 table from the committed rankings CSV."""
import csv
import io
import json
import os
import urllib.request
from pathlib import Path

TOKEN = os.environ.get("DATAWRAPPER_API_TOKEN") or os.environ.get("DATAWRAPPER_ACCESS_TOKEN")
if not TOKEN:
    raise SystemExit("Missing DATAWRAPPER_API_TOKEN / DATAWRAPPER_ACCESS_TOKEN GitHub Actions secret")
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "datawrapper/top-250-rankings-2026-week5.csv"
csv_text = SOURCE.read_text()
rows = list(csv.DictReader(io.StringIO(csv_text)))
if len(rows) != 250:
    raise SystemExit(f"Expected exactly 250 rows, found {len(rows)}")
columns = ["Half PPR Rank", "PPR Rank", "Standard Rank"]
for col in columns:
    ranks = [int(row[col]) for row in rows]
    if len(set(ranks)) != len(ranks) or any(rank < 1 for rank in ranks):
        raise SystemExit(f"Invalid rankings in {col}")
if len(set(row["Player"] for row in rows)) != 250:
    raise SystemExit("Duplicate player names in Top 250")
def api(method, path, data=None, content_type="application/json"):
    payload = None if data is None else (data.encode("utf-8") if isinstance(data,str) else json.dumps(data).encode("utf-8"))
    req = urllib.request.Request("https://api.datawrapper.de/v3" + path, data=payload, method=method, headers={
        "Authorization": "Bearer " + TOKEN, "Content-Type": content_type,
        "Accept": "application/json", "User-Agent": "RosterReportDatawrapperPublisher/1.0"})
    with urllib.request.urlopen(req, timeout=60) as res:
        body = res.read()
        return json.loads(body) if body else {}
chart = api("POST", "/charts", {"title": "The Roster Report | 2026 Fantasy Football Top 250 Rankings", "type": "table", "theme": "datawrapper", "language": "en-US"})
id = chart["id"]
api("PUT", f"/charts/{id}/data", csv_text, "text/csv")
# Sortable numeric ranking columns, with half-PPR as default ordering.
metadata = {"visualize": {
    "sort-by": "Half PPR Rank", "sort-asc": True,
    "pagination": {"enabled": True, "rowsPerPage": 15},
    "columns": {
        "Half PPR Rank": {"type": "number"},
        "PPR Rank": {"type": "number"},
        "Standard Rank": {"type": "number"},
        "Position": {"type": "text"}
    },
    "filterable": True, "sortable": True
}}
api("PATCH", f"/charts/{id}", {"metadata": metadata, "lastEditStep": 4,
    "description": "Top 250 overall (half-PPR baseline). Click a scoring rank column to sort; filter Position for QB, RB, WR or TE. Trade values are excluded.",
    "source-name": "The Roster Report"})
published = api("POST", f"/charts/{id}/publish", {"callWebhooks": True})
result = {"chartId": id, "url": published.get("url") or f"https://datawrapper.dwcdn.net/{id}/", "players": 250}
(ROOT / "datawrapper" / "published-top250.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
