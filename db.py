"""
The bond tracker's database: SQLite at data/bonds.db.

  deals     - one row per filing
  tranches  - one row per BOND, keyed by CUSIP so the same bond filed twice
              collapses into one row

Run `python db.py` to see what's stored.
"""
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "bonds.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    accession       TEXT PRIMARY KEY,
    issuer          TEXT,
    security_type   TEXT,
    is_final        INTEGER,
    form            TEXT,
    filing_date     TEXT,
    trade_date      TEXT,
    settlement_date TEXT,
    bookrunners     TEXT,
    use_of_proceeds TEXT,
    proceeds_quote  TEXT,
    proceeds_source TEXT,
    url             TEXT,
    extracted_at    TEXT
);

CREATE TABLE IF NOT EXISTS tranches (
    bond_key           TEXT PRIMARY KEY,
    accession          TEXT,
    cusip              TEXT,
    title              TEXT,
    is_floating        INTEGER,
    principal_usd      REAL,
    coupon_pct         REAL,
    maturity_date      TEXT,
    benchmark_treasury TEXT,
    benchmark_yield_pct REAL,
    spread_bps         REAL,
    yield_pct          REAL,
    price_pct_of_par   REAL,
    make_whole_bps     REAL,
    par_call_date      TEXT,
    rating_moodys      TEXT,
    rating_sp          TEXT,
    rating_fitch       TEXT,
    math_check         TEXT,
    grade              TEXT,
    maturity_bucket    TEXT,
    spread_vs_index_bps REAL,
    FOREIGN KEY (accession) REFERENCES deals(accession)
);
"""

TRANCHE_FIELDS = [
    "cusip", "title", "is_floating_rate", "principal_usd", "coupon_pct", "maturity_date",
    "benchmark_treasury", "benchmark_yield_pct", "spread_bps", "yield_pct",
    "price_pct_of_par", "make_whole_bps", "par_call_date",
    "rating_moodys", "rating_sp", "rating_fitch",
]

IG_MOODYS = {"aaa", "aa1", "aa2", "aa3", "a1", "a2", "a3", "baa1", "baa2", "baa3"}
IG_SP = {"aaa", "aa+", "aa", "aa-", "a+", "a", "a-", "bbb+", "bbb", "bbb-"}


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def already_saved(accession):
    with connect() as conn:
        row = conn.execute("SELECT 1 FROM deals WHERE accession = ?", (accession,)).fetchone()
    return row is not None


def math_check(t):
    b, s, y = t.get("benchmark_yield_pct"), t.get("spread_bps"), t.get("yield_pct")
    if None in (b, s, y):
        return "n/a"
    return "OK" if abs(b + s / 100 - y) < 0.002 else "MISMATCH"


def grade(t):
    """IG, HY, split when the agencies disagree, or None when unrated here."""
    m, s = (t.get("rating_moodys") or "").strip().lower(), (t.get("rating_sp") or "").strip().lower()
    calls = [r in ig for r, ig in ((m, IG_MOODYS), (s, IG_SP)) if r]
    if not calls:
        return None
    if all(calls):
        return "IG"
    return "HY" if not any(calls) else "split"


def maturity_bucket(t):
    """Years to maturity, bucketed the way index families are."""
    md = t.get("maturity_date")
    if not md:
        return None
    try:
        years = (date.fromisoformat(md) - date.today()).days / 365.25
    except ValueError:
        return None
    for limit, name in ((3, "1-3y"), (5, "3-5y"), (7, "5-7y"), (10, "7-10y"), (15, "10-15y")):
        if years <= limit:
            return name
    return "15y+"


def bond_key(t, accession):
    """A bond's identity: its CUSIP when the filing gives one, else the filing plus title."""
    cusip = (t.get("cusip") or "").strip().upper()
    return cusip if len(cusip) >= 8 else f"{accession}:{t.get('title')}"


def save(terms, accession, form=None, filing_date=None, url=None):
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO deals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                accession,
                terms.get("issuer"),
                terms.get("security_type"),
                1 if terms.get("is_final_pricing") else 0,
                form,
                filing_date,
                terms.get("trade_date"),
                terms.get("settlement_date"),
                ", ".join(terms.get("bookrunners") or []),
                terms.get("use_of_proceeds_category"),
                terms.get("use_of_proceeds_quote"),
                "fwp" if terms.get("use_of_proceeds_category") else None,
                url,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        for t in terms.get("tranches", []):
            values = ([bond_key(t, accession), accession] + [t.get(f) for f in TRANCHE_FIELDS]
                      + [math_check(t), grade(t), maturity_bucket(t), None])
            conn.execute(
                f"INSERT OR REPLACE INTO tranches VALUES ({','.join('?' * len(values))})",
                values,
            )
    return len(terms.get("tranches", []))


def summary():
    with connect() as conn:
        deals = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        tranches = conn.execute("SELECT COUNT(*) FROM tranches").fetchone()[0]
        total = conn.execute("SELECT SUM(principal_usd) FROM tranches").fetchone()[0] or 0
        ig = conn.execute("SELECT COUNT(*) FROM tranches WHERE grade = 'IG'").fetchone()[0]
        hy = conn.execute("SELECT COUNT(*) FROM tranches WHERE grade = 'HY'").fetchone()[0]
        print(f"{deals} filings, {tranches} unique bonds ({ig} IG, {hy} HY), ${total / 1e9:,.2f}B total\n")
        rows = conn.execute("""
            SELECT d.issuer, t.title, t.grade, t.maturity_bucket, t.spread_bps, t.math_check, d.use_of_proceeds
            FROM tranches t JOIN deals d ON d.accession = t.accession
            ORDER BY d.trade_date DESC, t.maturity_date
        """).fetchall()
        for issuer, title, grade_, bucket, spread, check, proceeds in rows:
            spread = f"+{spread:g}" if spread is not None else "n/a"
            print(f"  {(issuer or '')[:26]:26} {(title or '')[:30]:30} {str(grade_ or ''):5} "
                  f"{str(bucket or ''):7} {spread:>6}  {check:8} {proceeds or ''}")


if __name__ == "__main__":
    summary()
