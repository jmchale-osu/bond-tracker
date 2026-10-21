"""
Add each issuer's industry and domicile from EDGAR's free company API.
No model, no API key, just a public JSON endpoint per company.

    python issuer_info.py
"""
import json
import time
import urllib.request

import db

HEADERS = {"User-Agent": "James McHale jtmchale912@gmail.com"}

# EDGAR gives a numeric SIC code; these are the groups a credit desk thinks in
SECTORS = [
    (range(1, 1000), "Agriculture"),
    (range(1000, 1500), "Metals & Mining"),
    (range(1500, 1800), "Construction"),
    (range(2000, 2200), "Food & Beverage"),
    (range(2200, 2400), "Textiles & Apparel"),
    (range(2400, 2600), "Paper & Packaging"),
    (range(2600, 2800), "Chemicals"),
    (range(2800, 2900), "Pharma & Chemicals"),
    (range(2900, 3000), "Energy & Refining"),
    (range(3000, 3600), "Industrials"),
    (range(3600, 3700), "Electronics"),
    (range(3700, 3800), "Autos & Aerospace"),
    (range(3800, 4000), "Instruments"),
    (range(4000, 4300), "Transport"),
    (range(4400, 4600), "Transport"),
    (range(4800, 4900), "Telecom & Media"),
    (range(4900, 5000), "Utilities"),
    (range(5000, 5200), "Wholesale"),
    (range(5200, 6000), "Retail"),
    (range(6000, 6200), "Banks"),
    (range(6200, 6300), "Financials"),
    (range(6300, 6500), "Insurance"),
    (range(6500, 6800), "Real Estate"),
    (range(7000, 8000), "Services"),
    (range(8000, 8100), "Healthcare"),
    (range(8200, 9000), "Services"),
]


def sector_for(sic):
    try:
        code = int(sic)
    except (TypeError, ValueError):
        return None
    for span, name in SECTORS:
        if code in span:
            return name
    return "Other"


def company(cik):
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as r:
        return json.load(r)


def main():
    conn = db.connect()
    rows = conn.execute("""
        SELECT accession, issuer, url FROM deals WHERE sic IS NULL AND url IS NOT NULL
    """).fetchall()
    print(f"{len(rows)} deals missing issuer details\n")

    cache, filled, missed = {}, 0, 0
    for i, (accession, issuer, url) in enumerate(rows, 1):
        cik = url.split("/data/")[1].split("/")[0] if "/data/" in url else None
        if not cik:
            missed += 1
            continue
        try:
            if cik not in cache:
                cache[cik] = company(cik)
                time.sleep(0.15)        # the SEC asks for under 10 requests a second
            info = cache[cik]
            sic = info.get("sic")
            conn.execute("""UPDATE deals SET sic=?, sector=?, state_of_incorporation=?, country=?
                            WHERE accession=?""",
                         (sic, sector_for(sic), info.get("stateOfIncorporation"),
                          (info.get("addresses", {}).get("business", {}) or {}).get("country")
                          or ("US" if info.get("stateOfIncorporation") else None),
                          accession))
            conn.commit()
            filled += 1
            if i % 20 == 0 or i == len(rows):
                print(f"  {i}/{len(rows)} done")
        except Exception as e:
            missed += 1
            print(f"  {(issuer or '')[:34]}: {e}")

    print(f"\nDone. {filled} updated, {missed} missed.\n")
    for sector, count, volume in conn.execute("""
        SELECT d.sector, COUNT(*), SUM(t.principal_usd)/1e9
        FROM tranches t JOIN deals d ON d.accession = t.accession
        WHERE d.sector IS NOT NULL GROUP BY d.sector ORDER BY 3 DESC"""):
        print(f"  {sector:22} {count:4} tranches  ${volume:7.1f}B")


if __name__ == "__main__":
    main()
