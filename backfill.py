"""
Backfill: find bond pricing term sheets (FWPs) over a window of days,
extract each one with Claude, and save it to the database.

    python backfill.py 30 --dry-run     # list candidates, no API calls
    python backfill.py 30 --limit 10    # extract the 10 oldest candidates
    python backfill.py 30               # extract all candidates

Filings already in the database are skipped, so you can stop and restart.
"""
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from edgar import set_identity, get_filings

import db
from extract import extract

set_identity("James McHale jtmchale912@gmail.com")

BASE = Path(__file__).resolve().parent
RAW_DIR = BASE / "data" / "raw"

PRICING = re.compile(r"spread to (the )?benchmark|benchmark treasury|reoffer spread|treasury rate plus", re.I)
BOND = re.compile(r"(notes?|bonds?|debentures?)\b[^.$]{0,40}?\bdue\s+20\d{2}", re.I)
EXCLUDE = re.compile(
    r"convertible|exchangeable|asset[- ]backed|linked to|autocallable|buffer|barrier|"
    r"contingent (coupon|interest)|market[- ]linked|leveraged|worst[- ]performing|underlying (stock|index)",
    re.I,
)
SOVEREIGNS = re.compile(r"government of|republic of|kingdom of|\bkfw\b|development bank", re.I)


def doc_text(f):
    path = RAW_DIR / f"{f.accession_no}.txt"
    if path.exists():
        return path.read_text()
    text = (f.text() or "")[:20000]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


def find_candidates(days):
    end = date.today()
    start = end - timedelta(days=days)
    print(f"Reading FWP filings from {start} to {end}. This part is slow but free.\n")
    filings = get_filings(form="FWP", filing_date=f"{start}:{end}")

    seen, candidates = set(), []
    for i, f in enumerate(filings, 1):
        if i % 200 == 0:
            print(f"  ...checked {i} of {len(filings)} rows, {len(candidates)} candidates so far")
        if f.accession_no in seen or SOVEREIGNS.search(f.company):
            continue
        seen.add(f.accession_no)
        try:
            text = doc_text(f)
        except Exception as e:
            print(f"  could not read {f.company}: {e}")
            continue
        if PRICING.search(text) and BOND.search(text) and not EXCLUDE.search(text):
            candidates.append(f)

    candidates.sort(key=lambda f: f.filing_date)
    print(f"\n{len(candidates)} bond pricing term sheets out of {len(seen)} unique FWPs")
    return candidates


def main():
    args = sys.argv[1:]
    days = int(args[0]) if args and args[0].isdigit() else 30
    dry_run = "--dry-run" in args
    limit = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])

    candidates = find_candidates(days)
    todo = [f for f in candidates if not db.already_saved(f.accession_no)]
    print(f"{len(candidates) - len(todo)} already in the database, {len(todo)} left to extract")

    if limit:
        todo = todo[:limit]
    if dry_run:
        for f in todo:
            print(f"  {f.filing_date} | {f.company[:45]}")
        print(f"\nDry run. Extracting these would cost roughly ${len(todo) * 0.02:.2f}.")
        return

    print(f"\nExtracting {len(todo)} filings, roughly ${len(todo) * 0.02:.2f} of API usage.\n")
    saved = failed = 0
    for i, f in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {f.company[:45]}")
        try:
            terms = extract(f.accession_no)
            url = f"https://www.sec.gov/Archives/edgar/data/{f.cik}/{f.accession_no.replace('-', '')}/"
            n = db.save(terms, f.accession_no, form=f.form, filing_date=str(f.filing_date), url=url)
            saved += 1
            print(f"  saved {n} tranches\n")
        except Exception as e:
            failed += 1
            print(f"  FAILED: {e}\n")
        time.sleep(0.5)

    print(f"Done. {saved} filings saved, {failed} failed.\n")
    db.summary()


if __name__ == "__main__":
    main()
