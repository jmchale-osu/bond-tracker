"""
One-time fix: a deal whose note titles all say "Junior Subordinated" (or similar) cannot be
senior. Happens when the coupon fallback matched a concurrent offering's prospectus.
Corrects those deals. Safe to rerun.
"""
import db
from structure import check_ranking

conn = db.connect()
fixed = 0
for accession, issuer, ranking, quote in conn.execute(
        "SELECT accession, issuer, ranking, structure_quote FROM deals WHERE ranking IS NOT NULL").fetchall():
    new = check_ranking(conn, accession, ranking)
    if new != ranking:
        conn.execute("UPDATE deals SET ranking = ?, structure_quote = ? WHERE accession = ?",
                     (new, f"(from note titles; matched prospectus disagreed) {quote or ''}", accession))
        print(f"  {issuer[:50]}: {ranking} -> {new}")
        fixed += 1
conn.commit()
print(f"Fixed {fixed} deals.")
