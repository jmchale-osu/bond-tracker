"""
For every bond, compare its spread to the matching index on its trade date.

    spread_vs_index_bps = deal spread - index OAS

Positive means the deal priced wider (cheaper) than comparable paper.
"""
import db

MOODYS = [("aaa", "AAA"), ("aa", "AA"), ("a", "A"), ("baa", "BBB"),
          ("ba", "BB"), ("b", "B"), ("caa", "CCC"), ("ca", "CCC"), ("c", "CCC")]
SP = [("aaa", "AAA"), ("aa", "AA"), ("a", "A"), ("bbb", "BBB"),
      ("bb", "BB"), ("b", "B"), ("ccc", "CCC"), ("cc", "CCC"), ("c", "CCC")]


def rating_bucket(moodys, sp):
    """Aa2 -> AA, BBB+ -> BBB. Moody's first, then S&P."""
    for value, table in ((moodys, MOODYS), (sp, SP)):
        v = (value or "").strip().lower()
        if not v:
            continue
        for prefix, bucket in table:
            if v.startswith(prefix):
                return bucket
    return None


def index_on(conn, family, label, as_of):
    row = conn.execute("""
        SELECT value FROM market_data
        WHERE family = ? AND label = ? AND date <= ?
        ORDER BY date DESC LIMIT 1
    """, (family, label, as_of)).fetchone()
    return row[0] if row else None


def main():
    conn = db.connect()
    rows = conn.execute("""
        SELECT t.bond_key, t.spread_bps, t.grade, t.rating_moodys, t.rating_sp,
               COALESCE(d.trade_date, d.filing_date)
        FROM tranches t JOIN deals d ON d.accession = t.accession
        WHERE t.spread_bps IS NOT NULL
    """).fetchall()

    done = skipped = 0
    for bond_key, spread, grade, moodys, sp, as_of in rows:
        bucket = rating_bucket(moodys, sp)
        if grade == "HY":
            family, label = "hy_rating", bucket if bucket in ("BB", "B", "CCC") else "HY_ALL"
        else:
            family, label = "ig_rating", bucket if bucket in ("AAA", "AA", "A", "BBB") else "BBB"
        index_pct = index_on(conn, family, label, as_of) if as_of else None
        if index_pct is None:
            skipped += 1
            continue
        conn.execute("UPDATE tranches SET spread_vs_index_bps = ? WHERE bond_key = ?",
                     (round(spread - index_pct * 100, 1), bond_key))
        done += 1
    conn.commit()

    print(f"{done} bonds compared to their index, {skipped} skipped\n")
    for label, sign in (("cheapest (widest vs index)", "DESC"), ("richest (tightest vs index)", "ASC")):
        print(label)
        for issuer, title, gap, grade in conn.execute(f"""
            SELECT d.issuer, t.title, t.spread_vs_index_bps, t.grade
            FROM tranches t JOIN deals d ON d.accession = t.accession
            WHERE t.spread_vs_index_bps IS NOT NULL
            ORDER BY t.spread_vs_index_bps {sign} LIMIT 5
        """):
            print(f"  {(issuer or '')[:28]:28} {(title or '')[:32]:32} {grade or '':5} {gap:+.0f} bps")
        print()


if __name__ == "__main__":
    main()
