"""
Extract one filing with extract.py and save the result to the database.

Run:  python save.py                                  (the Xylem FWP)
      python save.py 0001193125-26-390790             (any FWP)
      python save.py 0001193125-26-390790 --force     (redo one already saved)
"""
import sys
import json

from edgar import find

import db
from extract import extract, check_math, grade, XYLEM_FWP, XYLEM_GOLD

args = [a for a in sys.argv[1:] if a != "--force"]
force = "--force" in sys.argv
accession = args[0] if args else XYLEM_FWP

if db.already_saved(accession) and not force:
    print(f"{accession} is already in the database. Add --force to do it again.")
    sys.exit()

terms = extract(accession)
print(json.dumps(terms, indent=2))

print("\nMath check:")
check_math(terms)
if accession == XYLEM_FWP:
    grade(terms, XYLEM_GOLD)

filing = find(accession)
url = f"https://www.sec.gov/Archives/edgar/data/{filing.cik}/{accession.replace('-', '')}/"
count = db.save(terms, accession, form=filing.form, filing_date=str(filing.filing_date), url=url)
print(f"\nSaved {count} tranches to {db.DB_PATH.name}")
