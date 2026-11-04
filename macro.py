"""
The macro backdrop: inflation, jobs and the Fed's rate, plus the days that move markets.

    python macro.py

Saves to the database:
  market_data (family 'macro')  monthly CPI, core CPI, core PCE, payrolls and unemployment,
                                and the daily fed funds target range, from FRED
  events                        FOMC decision days (federalreserve.gov) and CPI and jobs
                                report release days (ALFRED, the St. Louis Fed's release archive)

No API key needed. Each source is fetched on its own, so one failing leaves the rest.
"""
import re
import sqlite3
import urllib.request
from datetime import date

import db
from fred import fetch

SERIES = {
    "CPIAUCSL": "cpi",           # index level, turned into a year-on-year rate on the site
    "CPILFESL": "core_cpi",      # CPI excluding food and energy
    "PCEPILFE": "core_pce",      # the Fed's preferred inflation gauge
    "UNRATE": "unemployment",    # percent
    "PAYEMS": "payrolls",        # thousands of jobs
    "DFEDTARU": "fed_upper",     # top of the fed funds target range, percent
    "DFEDTARL": "fed_lower",
}
SINCE = "2023-01-01"             # enough for year-on-year rates and a two-year chart

RELEASES = {10: ("cpi", "CPI report"), 50: ("jobs", "Jobs report")}   # ALFRED release ids
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July",
                                      "August", "September", "October", "November", "December"], 1)}

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    date   TEXT,
    kind   TEXT,   -- fomc, cpi, jobs
    label  TEXT,
    PRIMARY KEY (date, kind)
);
"""


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (bond-tracker; research)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def fomc_days(html):
    """Decision day (the last day) of each scheduled FOMC meeting. Skips notation votes and
    unscheduled calls, which have no range of days. A meeting that spans months is listed
    as 'April/May' with days like '30-1'."""
    out = []
    for block in re.split(r'(?=<h4><a id="\d+">\d{4} FOMC Meetings)', html)[1:]:
        year = int(re.search(r"(\d{4}) FOMC Meetings", block).group(1))
        pairs = re.findall(r'fomc-meeting__month[^>]*><strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<',
                           block, re.S)
        for month, days in pairs:
            m = re.match(r"\s*(\d+)-(\d+)", days)
            if not m:
                continue
            name = month.strip().split("/")[-1]
            if name in MONTHS:
                out.append(date(year, MONTHS[name], int(m.group(2))).isoformat())
    return sorted(set(out))


def release_days(rid):
    return re.findall(r"^(\d{4}-\d\d-\d\d)\s*$", get(f"https://alfred.stlouisfed.org/release/downloaddates?rid={rid}&ff=txt"), re.M)


def main():
    conn = db.connect()
    conn.executescript(SCHEMA)

    for series_id, label in SERIES.items():
        try:
            rows = fetch(series_id)
        except Exception as e:
            print(f"  {series_id:10} FAILED: {e}")
            continue
        saved = 0
        for row in rows[1:]:
            if len(row) < 2 or row[1] in (".", "") or row[0] < SINCE:
                continue
            try:
                conn.execute("INSERT OR REPLACE INTO market_data VALUES (?,?,?,?,?)",
                             (row[0], "macro", label, float(row[1]), series_id))
                saved += 1
            except (ValueError, sqlite3.Error):
                continue
        conn.commit()
        print(f"  {series_id:10} {label:13} {saved:,} values")

    try:
        days = fomc_days(get(FOMC_URL))
        conn.executemany("INSERT OR REPLACE INTO events VALUES (?,?,?)", [(d, "fomc", "Fed decision") for d in days])
        print(f"  FOMC       {len(days)} decision days, {days[0]} to {days[-1]}")
    except Exception as e:
        print(f"  FOMC       FAILED: {e}")
    for rid, (kind, label) in RELEASES.items():
        try:
            days = [d for d in release_days(rid) if d >= SINCE]
            conn.executemany("INSERT OR REPLACE INTO events VALUES (?,?,?)", [(d, kind, label) for d in days])
            print(f"  {label:10} {len(days)} release days through {days[-1]}")
        except Exception as e:
            print(f"  {label:10} FAILED: {e}")
    conn.commit()


if __name__ == "__main__":
    main()
