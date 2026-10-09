"""
Download ICE BofA index spreads and Treasury yields from FRED into the database.

Run:  python fred.py
No API key needed: these are public CSV downloads.
"""
import csv
import io
import sqlite3
import urllib.request

import db

# ICE BofA option-adjusted spreads, in percent (1.25 means 125 bps)
SERIES = {
    # investment grade, by rating
    "BAMLC0A1CAAA": ("ig_rating", "AAA"),
    "BAMLC0A2CAA": ("ig_rating", "AA"),
    "BAMLC0A3CA": ("ig_rating", "A"),
    "BAMLC0A4CBBB": ("ig_rating", "BBB"),
    # high yield, by rating
    "BAMLH0A1HYBB": ("hy_rating", "BB"),
    "BAMLH0A2HYB": ("hy_rating", "B"),
    "BAMLH0A3HYC": ("hy_rating", "CCC"),
    "BAMLH0A0HYM2": ("hy_rating", "HY_ALL"),
    # investment grade, by maturity
    "BAMLC1A0C13Y": ("ig_maturity", "1-3y"),
    "BAMLC2A0C35Y": ("ig_maturity", "3-5y"),
    "BAMLC3A0C57Y": ("ig_maturity", "5-7y"),
    "BAMLC4A0C710Y": ("ig_maturity", "7-10y"),
    "BAMLC7A0C1015Y": ("ig_maturity", "10-15y"),
    "BAMLC8A0C15PY": ("ig_maturity", "15y+"),
    # Treasury yields, in percent
    "DGS2": ("treasury", "2y"),
    "DGS10": ("treasury", "10y"),
    "DGS30": ("treasury", "30y"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_data (
    date     TEXT,
    family   TEXT,   -- ig_rating, hy_rating, ig_maturity, treasury
    label    TEXT,   -- BBB, 7-10y, 10y, ...
    value    REAL,   -- percent
    series   TEXT,
    PRIMARY KEY (date, family, label)
);
"""


def fetch(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return list(csv.reader(io.StringIO(r.read().decode())))


def main():
    conn = db.connect()
    conn.executescript(SCHEMA)
    total = 0
    for series_id, (family, label) in SERIES.items():
        try:
            rows = fetch(series_id)
        except Exception as e:
            print(f"  {series_id:16} FAILED: {e}")
            continue
        saved = 0
        for row in rows[1:]:
            if len(row) < 2 or row[1] in (".", ""):
                continue
            try:
                conn.execute("INSERT OR REPLACE INTO market_data VALUES (?,?,?,?,?)",
                             (row[0], family, label, float(row[1]), series_id))
                saved += 1
            except (ValueError, sqlite3.Error):
                continue
        conn.commit()
        total += saved
        print(f"  {series_id:16} {family:12} {label:8} {saved:,} daily values")
    last = conn.execute("SELECT MAX(date) FROM market_data").fetchone()[0]
    print(f"\n{total:,} values saved, through {last}")


if __name__ == "__main__":
    main()
