"""
One-time fix: a rating trigger inside a change of control clause is not a coupon step.
Unflags those deals. Safe to rerun.
"""
import sqlite3
from pathlib import Path

conn = sqlite3.connect(Path(__file__).resolve().parent / "data" / "bonds.db")
n = conn.execute("""
    UPDATE deals SET coupon_step = 0,
           coupon_step_note = '(not a coupon step: rating trigger on the change of control put) ' || coupon_step_note
    WHERE coupon_step = 1
      AND (LOWER(coupon_step_note) LIKE '%change of control%' OR LOWER(coupon_step_note) LIKE '%repurchase%')
""").rowcount
conn.commit()
print(f"Unflagged {n} deals.")
print("Still flagged as coupon steps:")
for (issuer,) in conn.execute("""
        SELECT DISTINCT issuer FROM deals d WHERE coupon_step = 1
        AND EXISTS (SELECT 1 FROM tranches t WHERE t.accession = d.accession)"""):
    print("  ", issuer)
