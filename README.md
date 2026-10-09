# New Issue Credit Tracker

Reads SEC filings for every registered corporate bond deal, extracts each tranche's terms with an LLM, and compares pricing to the matching ICE BofA index.

**Live page:** https://jmchale-osu.github.io/bond-tracker/

## The question

When a company sells bonds, the prospectus says what the money is for. Deals that fund an acquisition add debt to the balance sheet; deals that refinance do not. This project tests whether buyers charge more for the first kind, using tranches read straight from filings rather than from a data vendor.

## How it works

| Step | Script | What it does |
|---|---|---|
| 1 | `backfill.py` | Finds pricing term sheets (FWPs) on EDGAR over a window of days and sends each to `extract.py` |
| 2 | `extract.py` | Uses Claude to turn a term sheet into structured tranche data, then checks the pricing math (benchmark + spread = yield) |
| 3 | `proceeds.py` | Finds each deal's 424B5 prospectus and pulls the use of proceeds, with a verbatim quote |
| 4 | `fred.py` | Downloads ICE BofA index spreads and Treasury yields from FRED |
| 5 | `enrich.py` | Computes each bond's spread minus the matching index OAS on its trade date |
| 6 | `dedupe.py` | Collapses duplicate tranches |
| 7 | `analysis.py` | Runs the tests against the database |
| 8 | `report.py` | Builds `index.html`, the interactive page |

`db.py` holds the SQLite schema (`data/bonds.db`). `find_bonds.py` and `save.py` are helpers for finding and extracting single filings.

## Run it

```
pip install anthropic edgartools python-dotenv
echo "ANTHROPIC_API_KEY=your-key" > .env
python backfill.py 30
python proceeds.py
python fred.py
python enrich.py
python dedupe.py
python report.py
```

## Limits

- Registered deals only. Most high yield is sold under Rule 144A and never reaches EDGAR.
- Index spreads are option-adjusted and matched by rating category, not exact notch, so the gap is directional.
- No order book data: filings do not disclose books, price talk or new issue concession.

Personal project. Not investment advice.
