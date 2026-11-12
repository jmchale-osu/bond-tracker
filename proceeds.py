"""
Fill in use of proceeds for each deal: from the term sheet when it says, otherwise from the
prospectus supplement (424B5) filed within a week. Rule-based (rules.py), so it costs nothing.

Run:  python proceeds.py            (all deals missing it)
      python proceeds.py --limit 5  (try a few first)
      python proceeds.py --check    (compare with what is stored, change nothing)
"""
import re
import sys
from datetime import date

from edgar import set_identity, Company

import db
import rules
from parse_fwp import get_html, parse

set_identity(db.SEC_IDENTITY)

def find_prospectus(cik, filing_date):
    """A 424B5 from the same issuer within a week of the term sheet."""
    filings = Company(int(cik)).get_filings(form="424B5")
    best = None
    for f in filings:
        gap = abs((f.filing_date - filing_date).days) if hasattr(f.filing_date, "days") or True else 99
        try:
            gap = abs((f.filing_date - filing_date).days)
        except TypeError:
            continue
        if gap <= 7 and (best is None or gap < best[0]):
            best = (gap, f)
    return best[1] if best else None


def read(accession, filing_date, url):
    """(category, quote, source) for one deal."""
    html = get_html(accession)
    if re.search(r"special\s+mandatory\s+redemption", html, re.I):
        return "acquisition", "Special mandatory redemption if the acquisition does not close", "fwp"
    sheet = parse(html).get("use_of_proceeds_quote")
    if sheet:
        category, quote = rules.proceeds(sheet)
        if category != "not_stated":
            return category, quote, "fwp"
    cik = url.split("/data/")[1].split("/")[0] if url and "/data/" in url else None
    prospectus = find_prospectus(cik, date.fromisoformat(filing_date)) if cik else None
    section = rules.proceeds_section(prospectus.text() or "") if prospectus else None
    if not section:
        return "not_stated", None, None
    category, quote = rules.proceeds(section)
    return category, quote, "424b5"


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    check = "--check" in sys.argv
    conn = db.connect()
    rows = conn.execute(f"""
        SELECT accession, issuer, filing_date, url, use_of_proceeds FROM deals
        WHERE {"use_of_proceeds IS NOT NULL" if check else "use_of_proceeds IS NULL"}
          AND accession IN (SELECT accession FROM tranches)
        ORDER BY filing_date DESC
    """).fetchall()
    if limit:
        rows = rows[:limit]
    print(f"{len(rows)} deals to read\n")
    same = filled = 0
    for i, (accession, issuer, filing_date, url, stored) in enumerate(rows, 1):
        try:
            category, quote, source = read(accession, filing_date, url)
        except Exception as e:
            print(f"[{i}/{len(rows)}] {(issuer or '')[:40]}  FAILED: {e}")
            continue
        if check:
            same += category == stored
            if category != stored:
                print(f"  {(issuer or '')[:36]:36} stored {stored:17} rules {category:17} {(quote or '')[:60]}")
            continue
        conn.execute("UPDATE deals SET use_of_proceeds = ?, proceeds_quote = ?, proceeds_source = ? WHERE accession = ?",
                     (category, quote, source, accession))
        conn.commit()
        filled += category != "not_stated"
        print(f"[{i}/{len(rows)}] {(issuer or '')[:40]:40} {category}: {(quote or '')[:60]}")
    print(f"\nDone. {same if check else filled} of {len(rows)} {'agree' if check else 'filled in'}.")


if __name__ == "__main__":
    main()
