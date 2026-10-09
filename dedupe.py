"""Collapse duplicate tranches: same issuer, coupon, maturity and spread."""
import re
import db

conn = db.connect()
rows = conn.execute("""
    SELECT t.bond_key, t.cusip, d.issuer, t.coupon_pct, t.maturity_date, t.spread_bps, t.title
    FROM tranches t JOIN deals d ON d.accession = t.accession""").fetchall()

def identity(cusip, issuer, coupon, maturity, spread, title):
    if cusip and len(cusip.strip()) >= 8:
        return cusip.strip().upper()
    stem = re.sub(r"[^a-z]", "", (issuer or "").lower())[:14]
    return f"{stem}|{coupon}|{maturity}|{spread}|{(title or '')[:18].lower()}"

seen, drop = {}, []
for key, cusip, issuer, coupon, maturity, spread, title in rows:
    ident = identity(cusip, issuer, coupon, maturity, spread, title)
    if ident in seen:
        drop.append(key)
    else:
        seen[ident] = key

for key in drop:
    conn.execute("DELETE FROM tranches WHERE bond_key = ?", (key,))
conn.commit()
print(f"{len(rows)} rows -> {len(seen)} unique bonds ({len(drop)} duplicates removed)")
