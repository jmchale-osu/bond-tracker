"""
The three tests, run against the database.

    python analysis.py            all three
    python analysis.py proceeds   just test 1
"""
import sys
from statistics import median

import db

MIN_GROUP = 3     # never report a median from fewer than this many bonds


def rows(conn, sql, args=()):
    return conn.execute(sql, args).fetchall()


def test_proceeds(conn):
    """Test 1: do acquisition-funded deals price wider than refinancings?"""
    print("=" * 78)
    print("TEST 1  Acquisition vs refinancing, spread versus index (bps)")
    print("=" * 78)
    data = rows(conn, """
        SELECT d.use_of_proceeds, t.grade, t.maturity_bucket, t.spread_vs_index_bps
        FROM tranches t JOIN deals d ON d.accession = t.accession
        WHERE t.spread_vs_index_bps IS NOT NULL
          AND d.use_of_proceeds IN ('acquisition', 'refinancing')
    """)
    if not data:
        print("  no data yet: run proceeds.py and enrich.py first\n")
        return

    groups = {}
    for proceeds, grade, bucket, gap in data:
        groups.setdefault((grade, bucket, proceeds), []).append(gap)

    print(f"\n  {'Grade':6} {'Tenor':8} {'Acquisition':>22} {'Refinancing':>22} {'Gap':>8}")
    for grade, bucket in sorted({(g, b) for g, b, _ in groups}, key=lambda x: (str(x[0]), str(x[1]))):
        acq = groups.get((grade, bucket, "acquisition"), [])
        ref = groups.get((grade, bucket, "refinancing"), [])
        if len(acq) < MIN_GROUP or len(ref) < MIN_GROUP:
            continue
        a, r = median(acq), median(ref)
        print(f"  {str(grade):6} {str(bucket):8} {a:+8.0f} (n={len(acq):3}) {r:+8.0f} (n={len(ref):3}) {a - r:+8.0f}")

    overall = {}
    for proceeds, _, _, gap in data:
        overall.setdefault(proceeds, []).append(gap)
    print("\n  All tranches pooled (not controlled for rating or tenor):")
    for name, values in sorted(overall.items()):
        print(f"    {name:14} median {median(values):+6.0f} bps vs index   n={len(values)}")
    if len(overall) == 2:
        a, r = (median(overall[k]) for k in ("acquisition", "refinancing"))
        print(f"\n  Acquisition deals priced {a - r:+.0f} bps versus refinancings, pooled.")
    print()


def test_tenor_mix(conn):
    """Test 2: what maturities are issuers selling, week by week?"""
    print("=" * 78)
    print("TEST 2  Issuance by maturity bucket, per week ($mm)")
    print("=" * 78)
    data = rows(conn, """
        SELECT strftime('%Y-%W', COALESCE(d.trade_date, d.filing_date)) AS wk,
               t.maturity_bucket, SUM(t.principal_usd) / 1e6, COUNT(*)
        FROM tranches t JOIN deals d ON d.accession = t.accession
        WHERE t.principal_usd IS NOT NULL AND t.maturity_bucket IS NOT NULL
        GROUP BY wk, t.maturity_bucket ORDER BY wk
    """)
    if not data:
        print("  no data yet\n")
        return
    buckets = ["1-3y", "3-5y", "5-7y", "7-10y", "10-15y", "15y+"]
    weeks = {}
    for wk, bucket, amount, count in data:
        weeks.setdefault(wk, {})[bucket] = amount
    print("  Week     " + "".join(f"{b:>9}" for b in buckets) + f"{'Total':>11}")
    for wk in sorted(weeks):
        row = weeks[wk]
        total = sum(row.values())
        print(f"  {wk:9}" + "".join(f"{row.get(b, 0):>9,.0f}" for b in buckets) + f"{total:>11,.0f}")
    print()


def test_rates(conn):
    """Test 3: does supply pick up when rate expectations move?"""
    print("=" * 78)
    print("TEST 3  Weekly supply versus the 2-year Treasury")
    print("=" * 78)
    supply = dict(rows(conn, """
        SELECT strftime('%Y-%W', COALESCE(d.trade_date, d.filing_date)) AS wk,
               SUM(t.principal_usd) / 1e9
        FROM tranches t JOIN deals d ON d.accession = t.accession
        WHERE t.principal_usd IS NOT NULL GROUP BY wk
    """))
    yields = rows(conn, """
        SELECT strftime('%Y-%W', date) AS wk, AVG(value)
        FROM market_data WHERE family = 'treasury' AND label = '2y'
        GROUP BY wk ORDER BY wk
    """)
    if not supply or not yields:
        print("  no data yet: run fred.py and the backfill first\n")
        return
    y = {wk: value for wk, value in yields}
    print(f"\n  {'Week':9} {'Supply ($B)':>12} {'2y yield':>10} {'Weekly change':>15}")
    previous = None
    for wk in sorted(supply):
        rate = y.get(wk)
        change = f"{(rate - previous) * 100:+.0f} bps" if (rate and previous) else ""
        shown = f"{rate:.2f}" if rate else "n/a"
        print(f"  {wk:9} {supply[wk]:>12,.1f} {shown:>10} {change:>15}")
        previous = rate if rate else previous
    print("\n  Rising 2-year yields mean the market expects tighter policy.")
    print("  Heavy supply alongside a rise suggests issuers moving ahead of it.\n")


TESTS = {"proceeds": test_proceeds, "tenor": test_tenor_mix, "rates": test_rates}

if __name__ == "__main__":
    conn = db.connect()
    chosen = [a for a in sys.argv[1:] if a in TESTS] or list(TESTS)
    for name in chosen:
        TESTS[name](conn)
