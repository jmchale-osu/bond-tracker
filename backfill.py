"""
Backfill: find bond pricing term sheets (FWPs) filed over a window, read each one with the
rule-based parser (parse_fwp.py) and save it. Free: no API key.

    python backfill.py 30 --dry-run          list candidates, save nothing
    python backfill.py 30                    the last 30 days
    python backfill.py --since 2024-11-01    everything since a date (the two-year backfill)

Candidates come from EDGAR full-text search: FWPs that contain the phrases a bond pricing
term sheet uses ("Spread to Benchmark Treasury" and its variants). Filings already in the
database are skipped, so you can stop and restart.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

import db
from parse_fwp import get_html, parse

SEARCH = "https://efts.sec.gov/LATEST/search-index"
PHRASES = ['"Spread to Benchmark"', '"Spread to Treasury"', '"Spread to Benchmark Treasury"',
           '"Benchmark Treasury"', '"Reoffer Spread"', '"Re-offer Spread"']
EXCLUDE = re.compile(
    r"convertible|exchangeable|asset[- ]backed|linked to|autocallable|buffer|barrier|"
    r"contingent (coupon|interest)|market[- ]linked|leveraged|worst[- ]performing|underlying (stock|index)",
    re.I,
)
SOVEREIGNS = re.compile(r"government of|republic of|kingdom of|\bkfw\b|development bank|province of|"
                        r"united mexican|state of israel", re.I)


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": db.SEC_IDENTITY})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 + 3 * attempt)


def search(phrase, start, end):
    """Every FWP hit for one phrase, a month at a time (a query returns at most 10,000)."""
    out, lo = [], start
    while lo <= end:
        hi = min(end, lo + timedelta(days=31))
        offset = 0
        while True:
            q = urllib.parse.urlencode({"q": phrase, "forms": "FWP", "dateRange": "custom",
                                        "startdt": lo.isoformat(), "enddt": hi.isoformat(), "from": offset})
            hits = fetch_json(f"{SEARCH}?{q}")["hits"]
            batch = hits["hits"]
            out += batch
            offset += len(batch)
            if not batch or offset >= hits["total"]["value"]:
                break
            time.sleep(0.2)
        lo = hi + timedelta(days=1)
    return out


def find_candidates(start, end):
    print(f"Searching EDGAR for bond term sheets filed {start} to {end}.")
    found = {}
    for phrase in PHRASES:
        hits = search(phrase, start, end)
        for h in hits:
            acc, name = h["_id"].split(":", 1)
            src = h["_source"]
            company = re.sub(r"\s*\(.*$", "", (src.get("display_names") or [""])[0]).strip()
            if acc in found or SOVEREIGNS.search(company):
                continue
            cik = int((src.get("ciks") or ["0"])[0])
            found[acc] = {"accession": acc, "company": company, "filing_date": src.get("file_date"), "cik": cik,
                          "doc_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{name}"}
        print(f"  {phrase:32} {len(hits):5} hits, {len(found):5} filings so far")
    return sorted(found.values(), key=lambda c: c["filing_date"])


def window(args):
    if "--since" in args:
        return date.fromisoformat(args[args.index("--since") + 1]), date.today()
    days = int(args[0]) if args and args[0].isdigit() else 30
    return date.today() - timedelta(days=days), date.today()


def main():
    args = sys.argv[1:]
    start, end = window(args)
    candidates = find_candidates(start, end)
    todo = [c for c in candidates if not db.already_saved(c["accession"])]
    print(f"\n{len(candidates)} candidates, {len(candidates) - len(todo)} already in the database, {len(todo)} to read\n")
    if "--dry-run" in args:
        for c in todo:
            print(f"  {c['filing_date']} | {c['company'][:50]}")
        return

    saved = skipped = failed = 0
    for i, c in enumerate(todo, 1):
        try:
            html = get_html(c["accession"], c["doc_url"])
            terms = parse(html)
            text = re.sub(r"<[^>]+>", " ", html)
            if not terms["tranches"] or EXCLUDE.search(text[:30000]):
                skipped += 1
                continue
            terms["issuer"] = terms.get("issuer") or c["company"]
            terms["is_final_pricing"] = True
            url = f"https://www.sec.gov/Archives/edgar/data/{c['cik']}/{c['accession'].replace('-', '')}/"
            n = db.save(terms, c["accession"], form="FWP", filing_date=c["filing_date"], url=url)
            saved += 1
            if saved % 25 == 0 or len(todo) < 60:
                print(f"[{i}/{len(todo)}] {c['filing_date']} {terms['issuer'][:40]:40} {n} bonds")
        except Exception as e:
            failed += 1
            print(f"[{i}/{len(todo)}] {c['company'][:40]} FAILED: {e}")
        time.sleep(0.12)                 # SEC asks for at most 10 requests a second

    print(f"\nDone. {saved} term sheets saved, {skipped} were not bond term sheets, {failed} failed.\n")


if __name__ == "__main__":
    main()
