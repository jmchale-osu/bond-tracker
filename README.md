# New Issue Credit Tracker

Tests a thesis: **the bond market prices what's in the prospectus.** Reads SEC filings for
every registered corporate bond deal, extracts each tranche's terms with an LLM, and checks
whether ranking, collateral, change of control puts, coupon steps and use of proceeds show
up in new issue spreads.

**Live site: https://jmchale-osu.github.io/bond-tracker/**

| Page | What it shows |
|---|---|
| Thesis | The claim, a scorecard of five sub-claims with verdicts, and the chart that tests them |
| Evidence | Every bond behind each claim, what each term means, robustness checks |
| Market | Weekly issuance, BBB and BB index spreads, cheap or rich by tenor |
| Deals | Every tranche, searchable, each linked to its filing |
| Method | Latest weekly note, how the thesis is measured, limits, how it is built |

## How it works

| Step | File | What it does |
|---|---|---|
| Find | `backfill.py` | Scans EDGAR FWP filings for bond pricing term sheets |
| Extract | `extract.py` | Claude returns structured terms, using only numbers printed in the filing |
| Classify | `proceeds.py` | Finds each deal's 424B5 and categorizes use of proceeds with a verbatim quote |
| Enrich | `fred.py`, `enrich.py` | Pulls index spreads and Treasury yields from FRED, computes spread vs index |
| Test | `thesis.py` | Matched comparisons (same issuer and day, else same rating and maturity), resampled by issuer |
| Explore | `analysis.py` | Raw cuts: tenor mix, supply vs rate expectations, structure |
| Publish | `report.py` | Builds the five-page site into `site/`; upload that folder's contents to GitHub Pages |

## Checks

Every tranche is validated against its own arithmetic: benchmark yield plus spread
should equal the yield. Failures are flagged, not discarded. Bonds are deduplicated
so a deal filed by several co-registrants counts once.

## Limits

Registered deals only, so most 144A high yield is out of scope. Index spreads are
option-adjusted and matched by rating category, so the comparison is directional.
Filings do not disclose order books, price talk or new issue concession.

Not investment advice.
