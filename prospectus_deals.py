"""
Deals that come with no pricing term sheet. Some of the biggest issuers (Amazon, Oracle,
Microsoft) file only a final prospectus. Its filing-fee exhibit lists each tranche with its
size and the total offering price, which gives the price; the yield follows from price,
coupon and maturity, and the spread is that yield over the Treasury curve on the pricing day.

    python prospectus_deals.py --since 2024-11-01

These spreads are computed, not quoted, so they are flagged (math_check = 'computed') and
left out of the index comparison: the prospectus gives no ratings.
"""
import re
import sys
import time
import urllib.parse
from datetime import date, timedelta

import db
from backfill import SEARCH, fetch_json
from parse_fwp import DATE, TITLE, get_html, iso, rows_of

ISSUERS = {1018724: "Amazon.com, Inc.", 1341439: "Oracle Corporation", 789019: "Microsoft Corporation"}
TENORS = {"1y": 1, "2y": 2, "3y": 3, "5y": 5, "7y": 7, "10y": 10, "20y": 20, "30y": 30}


def business_day_before(d):
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def finals(cik, start, end):
    """Final prospectuses: 424B filings that carry a filing-fee exhibit."""
    q = urllib.parse.urlencode({"q": '"Notes due"', "forms": "424B2,424B5", "ciks": f"{cik:010d}",
                                "dateRange": "custom", "startdt": start.isoformat(), "enddt": end.isoformat()})
    docs = {}
    for h in fetch_json(f"{SEARCH}?{q}")["hits"]["hits"]:
        acc, name = h["_id"].split(":", 1)
        docs.setdefault(acc, {"date": h["_source"]["file_date"]})["fees" if "filingfee" in name.replace("-", "").lower()
                                                                     else "main"] = name
    return {a: d for a, d in docs.items() if "fees" in d and "main" in d}


def ytm(price, coupon, years):
    """Semi-annual yield to maturity, percent, by bisection."""
    n = max(1, round(years * 2))
    lo, hi = 0.0, 20.0
    for _ in range(80):
        y = (lo + hi) / 2
        r = y / 200
        pv = sum(coupon / 2 / (1 + r) ** k for k in range(1, n + 1)) + 100 / (1 + r) ** n
        lo, hi = (y, hi) if pv > price else (lo, y)
    return round((lo + hi) / 2, 3)


def treasury(conn, on, years):
    """The Treasury curve on a day, interpolated to a maturity."""
    curve = []
    for label, t in TENORS.items():
        row = conn.execute("SELECT value FROM market_data WHERE family='treasury' AND label=? AND date<=? "
                           "ORDER BY date DESC LIMIT 1", (label, on)).fetchone()
        if row:
            curve.append((t, row[0]))
    if len(curve) < 2:
        return None
    if years <= curve[0][0]:
        return curve[0][1]
    for (t0, y0), (t1, y1) in zip(curve, curve[1:]):
        if years <= t1:
            return y0 + (y1 - y0) * (years - t0) / (t1 - t0)
    return curve[-1][1]


def read(conn, cik, acc, doc):
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
    fees_html = get_html(f"fees-{acc}", base + doc["fees"])
    fees = rows_of(fees_html)
    main = " ".join(" ".join(r) for r in rows_of(get_html(acc, base + doc["main"])))
    header = " ".join(" ".join(r) for r in fees[:3])
    foreign = re.search(r"\b(EUR|GBP|CHF|JPY|CAD|AUD)(?=[\s\d:])|€|£", fees_html)    # often only in the XBRL units
    currency = ("EUR" if foreign.group(0) == "€" else "GBP" if foreign.group(0) == "£" else foreign.group(0)) if foreign else "USD"
    stated = re.findall(r"\b(20\d\d-\d\d-\d\d)\b", header)
    trade = stated[0] if stated else business_day_before(date.fromisoformat(doc["date"])).isoformat()
    maturities = {}
    for m in re.finditer(rf"(?:mature|due) on ({DATE.pattern})", main, re.I):
        d = DATE.search(m.group(1))
        maturities.setdefault(iso(d)[:4], iso(d))
    tranches = []
    for r in fees:
        r = [re.sub(r"(Notes|Bonds|Debentures)\s*due", r"\1 due", c) for c in r]
        if len(r) < 4 or not any(re.search(r"(Notes|Bonds|Debentures) due 20\d\d", c) for c in r):
            continue
        title = next((c for c in r if re.search(r"(Notes|Bonds|Debentures) due 20\d\d", c)), None)
        nums = [float(x.replace(",", "")) for c in r for x in re.findall(r"^\$?\s?([\d,]{7,}(?:\.\d+)?)$", c.strip())]
        if not title or len(nums) < 2:
            continue
        amount, total = nums[0], nums[1]
        year = re.search(r"due (20\d\d)", title).group(1)
        coupon = re.match(r"\s*(\d{1,2}\.\d+)%", title)
        maturity = maturities.get(year) or f"{year}{trade[4:]}"
        years = (date.fromisoformat(maturity) - date.fromisoformat(trade)).days / 365.25
        price = round(100 * total / amount, 3)
        t = {"title": title, "principal_usd": amount, "maturity_date": maturity, "price_pct_of_par": price,
             "currency": currency, "is_floating_rate": coupon is None}
        if coupon:
            t["coupon_pct"] = float(coupon.group(1))
            t["yield_pct"] = ytm(price, t["coupon_pct"], years)
            bench = treasury(conn, trade, years) if currency == "USD" else None   # sizes are USD equivalents
            if bench is not None:
                t["benchmark_yield_pct"] = round(bench, 3)
                t["benchmark_treasury"] = "Treasury curve, interpolated (computed)"
                t["spread_bps"] = round((t["yield_pct"] - bench) * 100)
        tranches.append(t)
    return {"issuer": ISSUERS[cik], "trade_date": trade, "is_final_pricing": True, "tranches": tranches}


def main():
    args = sys.argv[1:]
    start = date.fromisoformat(args[args.index("--since") + 1]) if "--since" in args else date.today() - timedelta(days=30)
    conn = db.connect()
    for cik, name in ISSUERS.items():
        for acc, doc in sorted(finals(cik, start, date.today()).items(), key=lambda x: x[1]["date"]):
            if db.already_saved(acc):
                continue
            terms = read(conn, cik, acc, doc)
            if not terms["tranches"]:
                print(f"  {doc['date']} {name:22} no tranches read from {acc}")
                continue
            db.save(terms, acc, form="424B", filing_date=doc["date"],
                    url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/")
            conn.execute("UPDATE tranches SET math_check = 'computed' WHERE accession = ?", (acc,))
            conn.commit()
            total = sum(t["principal_usd"] for t in terms["tranches"]) / 1e9
            print(f"  {terms['trade_date']} {name:22} {len(terms['tranches'])} tranches, ${total:.1f}B")
            time.sleep(0.2)


if __name__ == "__main__":
    main()
