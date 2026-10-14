#!/usr/bin/env python3
"""Refresh injury adjustments from nflverse official reports and current rosters.

Fail closed: never mark a feed as fresh if the source cannot be retrieved,
the roster snapshot is old, or matching is ambiguous.
"""
import json
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
import pandas as pd

YEAR = 2026
BASE = "https://github.com/nflverse/nflverse-data/releases/download"
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "injury-adjustments.json"
POSITIONS = {"QB", "RB", "WR", "TE"}
RESERVE = {"RES", "RSV", "IR", "PUP", "NFI"}
def key(name):
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)

def download(path):
    url = BASE + "/" + path
    with urlopen(Request(url, headers={"User-Agent": "RosterReportInjuryRefresh/1.0"}), timeout=90) as response:
        modified = response.headers.get("Last-Modified")
        if not modified:
            raise RuntimeError("Source has no Last-Modified header: " + url)
        from email.utils import parsedate_to_datetime
        age = datetime.now(timezone.utc) - parsedate_to_datetime(modified)
        if age > timedelta(days=7) or age < -timedelta(hours=2):
            raise RuntimeError(f"Source too old or invalid ({age}): {url}")
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".parquet") as tmp:
            tmp.write(response.read())
            tmp.flush()
            return pd.read_parquet(tmp.name)

def main():
    roster = download(f"rosters/roster_{YEAR}.parquet")
    reports = download(f"injuries/injuries_{YEAR}.parquet")
    for df, cols in ((roster, {"full_name", "position", "status", "team"}), (reports, {"full_name", "position", "report_status", "week", "team"})):
        missing = cols - set(df.columns)
        if missing:
            raise RuntimeError(f"Unexpected injury feed schema: {sorted(missing)}")
    roster = roster[roster.position.isin(POSITIONS)].copy()
    roster["match"] = roster.full_name.map(key)
    roster = roster.dropna(subset=["match"])
    roster = roster.sort_values("full_name").drop_duplicates(["match"], keep=False)
    if len(roster) < 250:
        raise RuntimeError(f"Insufficient active roster coverage: {len(roster)}")
    reports = reports[reports.position.isin(POSITIONS)].copy()
    reports["week"] = pd.to_numeric(reports.week, errors="coerce")
    reports = reports.dropna(subset=["week"])
    if reports.empty:
        raise RuntimeError("No 2026 injury reports")
    week = int(reports.week.max())
    reports = reports[reports.week.eq(week)].copy()
    reports["match"] = reports.full_name.map(key)
    reports = reports.drop_duplicates(["match"], keep=False)
    if len(reports) < 10:
        raise RuntimeError(f"Too few injury reports for week {week}: {len(reports)}")
    prior = json.loads(TARGET.read_text())
    prior_players = prior.get("players", {})
    previous = {key(n): (n, adj) for n, adj in prior_players.items()}
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    players = {}
    report_by_key = {r["match"]: r for _, r in reports.iterrows()}
    for _, player in roster.iterrows():
        match = player["match"]
        name = previous.get(match, (str(player.full_name), {}))[0]
        status = str(player.status or "").upper()
        report = report_by_key.get(match)
        designation = str(report.report_status).strip().lower() if report is not None and pd.notna(report.report_status) else ""
        injury = str(report.report_primary_injury) if report is not None and "report_primary_injury" in reports and pd.notna(report.report_primary_injury) else "undisclosed"
        if status in RESERVE or "reserve/injured" in status.lower():
            a, w, risk = 0.15, 0.2, 0.55
            label = f"Roster reserve status: {status}"
        elif designation in {"out", "doubtful", "questionable"}:
            a, w, risk = {"out": (0.35, 0.6, 0.85), "doubtful": (0.55, 0.7, 0.9), "questionable": (0.85, 0.9, 0.97)}[designation]
            label = f"Week {week}: {designation} ({injury})"
        else:
            continue
        players[name] = {"availability": a, "workload": w, "longTermRisk": risk,
                         "status": label, "note": f"Automated nflverse roster and official weekly injury report; latest report week {week}. This is not a season-ending prognosis.",
                         "expectedReturn": "Unconfirmed", "updatedAt": now}
    if not players:
        raise RuntimeError("No injury adjustments generated; refusing to overwrite")
    # Do not silently discard manually curated confirmed long-term/season-ending cases.
    for old_name, adj in prior_players.items():
        if float(adj.get("longTermRisk", 1)) <= 0.35 and key(old_name) not in {key(n) for n in players}:
            raise RuntimeError(f"Manual severe injury requires review before overwrite: {old_name}")
    result = {"updatedAt": now, "players": players, "source": "nflverse 2026 rosters + weekly official injury reports", "sourceWeek": week}
    TARGET.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"Validated injury refresh: {len(players)} players, report week {week}")

if __name__ == "__main__":
    main()
