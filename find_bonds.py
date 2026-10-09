"""
Find new corporate bond deals on EDGAR from the last N days.

Reads the cover page of each 424B5 filing, keeps plain bond deals,
and skips stock offerings, converts, ABS, structured notes, sovereigns,
and preliminary (unpriced) prospectuses.

Run:  python find_bonds.py          (last 14 days)
      python find_bonds.py 7        (last 7 days)
"""
import re
import sys
import csv
from datetime import date, timedelta
from pathlib import Path

from edgar import set_identity, get_filings

set_identity("James McHale jtmchale912@gmail.com")

DAYS_BACK = int(sys.argv[1]) if len(sys.argv) > 1 else 14
FORMS = ["424B5"]
BASE = Path(__file__).resolve().parent
RAW_DIR = BASE / "data" / "raw"
OUT_CSV = BASE / "data" / "bonds.csv"

BOND = re.compile(r"(notes?|bonds?|debentures?|series)\b[^.$]{0,40}?\bdue\s+(20\d{2})", re.I)
TITLE = re.compile(r"\$\s?[\d,\.]+\s*(?:million|billion)?[^$]{0,120}?(?:notes?|bonds?|debentures?|series)\b[^.$]{0,40}?\bdue\s+20\d{2}", re.I)
EXCLUDE = re.compile(
    r"convertible|exchangeable|asset[- ]backed|subject to completion|"
    r"linked to|autocallable|buffer|barrier|contingent (coupon|interest)|market[- ]linked|"
    r"leveraged|digital|trigger|callable contingent",
    re.I,
)
SOVEREIGNS = re.compile(r"government of|republic of|kingdom of|state of israel|\bkfw\b|export development|development bank", re.I)


def cover_text(f):
    path = RAW_DIR / f"{f.accession_no}.txt"
    if path.exists():
        return path.read_text()
    text = (f.text() or "")[:8000]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    end = date.today()
    start = end - timedelta(days=DAYS_BACK)
    print(f"Searching {', '.join(FORMS)} from {start} to {end}...")
    filings = get_filings(form=FORMS, filing_date=f"{start}:{end}")

    seen, rows = set(), []
    for i, f in enumerate(filings, 1):
        if i % 50 == 0:
            print(f"  ...checked {i} of {len(filings)} rows")
        if f.accession_no in seen:
            continue
        seen.add(f.accession_no)
        if SOVEREIGNS.search(f.company):
            continue
        try:
            cover = cover_text(f)
        except Exception as e:
            print(f"  could not read {f.company}: {e}")
            continue
        if not BOND.search(cover) or EXCLUDE.search(cover):
            continue
        title = TITLE.search(cover)
        rows.append({
            "filing_date": str(f.filing_date),
            "form": f.form,
            "company": f.company,
            "title": " ".join(title.group(0).split())[:140] if title else "",
            "url": f"https://www.sec.gov/Archives/edgar/data/{f.cik}/{f.accession_no.replace('-', '')}/",
        })
        print(f"  {f.filing_date} | {f.company[:35]:35} | {rows[-1]['title'][:70]}")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["filing_date", "form", "company", "title", "url"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} likely bond deals out of {len(seen)} unique filings. Saved to {OUT_CSV}")


if __name__ == "__main__":
    main()
