"""Collapse duplicate tranches: same issuer, coupon, maturity and spread.

A missing spread matches any spread: an issuer can file one term sheet for the whole deal that
leaves a floater's spread out, and a second one for the floater alone. The kept row takes any
field it is missing from the duplicate. Run enrich.py afterwards to recompute spread vs index.
"""
import re
import db

FILL = ["cusip", "benchmark_treasury", "benchmark_yield_pct", "spread_bps", "yield_pct",
        "price_pct_of_par", "make_whole_bps", "par_call_date",
        "rating_moodys", "rating_sp", "rating_fitch", "grade"]

conn = db.connect()
# Rows from deals with a stated structure come first, so they are the ones kept
rows = conn.execute("""
    SELECT t.bond_key, t.cusip, d.issuer, t.coupon_pct, t.maturity_date, t.spread_bps, t.title
    FROM tranches t JOIN deals d ON d.accession = t.accession
    ORDER BY (d.ranking IS NULL OR d.ranking = 'not_stated'), t.bond_key""").fetchall()

def identity(cusip, issuer, coupon, maturity, title):
    if cusip and len(cusip.strip()) >= 8:
        return cusip.strip().upper()
    stem = re.sub(r"[^a-z]", "", (issuer or "").lower())[:14]
    return f"{stem}|{coupon}|{maturity}|{(title or '')[:18].lower()}"

seen, drop = {}, []          # identity -> [(key, spread)] of the rows kept
for key, cusip, issuer, coupon, maturity, spread, title in rows:
    kept = seen.setdefault(identity(cusip, issuer, coupon, maturity, title), [])
    match = next((i for i, (_, s) in enumerate(kept) if s is None or spread is None or s == spread), None)
    if match is None:
        kept.append((key, spread))
        continue
    keep_key, keep_spread = kept[match]
    conn.execute(f"""
        UPDATE tranches SET {', '.join(f'{c} = COALESCE({c}, (SELECT {c} FROM tranches WHERE bond_key = :dup))'
                                       for c in FILL)}
        WHERE bond_key = :keep""", {"keep": keep_key, "dup": key})
    b, s, y = conn.execute("SELECT benchmark_yield_pct, spread_bps, yield_pct FROM tranches WHERE bond_key = ?",
                           (keep_key,)).fetchone()
    conn.execute("UPDATE tranches SET math_check = ? WHERE bond_key = ?",
                 (db.math_check({"benchmark_yield_pct": b, "spread_bps": s, "yield_pct": y}), keep_key))
    kept[match] = (keep_key, keep_spread if keep_spread is not None else spread)
    drop.append(key)

for key in drop:
    conn.execute("DELETE FROM tranches WHERE bond_key = ?", (key,))
conn.commit()
print(f"{len(rows)} rows -> {len(rows) - len(drop)} unique bonds ({len(drop)} duplicates removed)")
