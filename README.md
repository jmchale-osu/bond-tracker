# New Issue Credit Tracker

Tests a thesis: **the bond market prices what's in the prospectus.** Reads SEC filings for
every registered corporate bond deal since November 2024, reads each tranche's terms with a
rule-based parser, scores every bond against a fair value model out of sample, and checks
whether ranking, collateral, change of control puts, coupon steps and use of proceeds show
up in new issue spreads.

Free to run: no API keys. Every source is public (SEC EDGAR, FRED, the Federal Reserve).

**Live site: https://jmchale-osu.github.io/bond-tracker/**

| Page | What it shows |
|---|---|
| Thesis | The claim, a scorecard of five sub-claims with verdicts, and the chart that tests them |
| Evidence | Every bond behind each claim, what each term means, robustness checks |
| Model | Fair value model: out-of-sample error vs a baseline, bonds that came wide or inside, what moves spreads |
| Market | Weekly issuance, index spreads, the macro backdrop, cheap or rich by tenor |
| Deals | Every tranche with its CUSIP, searchable, each linked to its filing |
| Method | How the thesis is measured, limits, how it is built |

## How it works

`python weekly.py` runs every step. GitHub Actions runs it every Monday.

| Step | File | What it does |
|---|---|---|
| Find | `backfill.py` | EDGAR full-text search for FWPs with pricing terms ("Spread to Benchmark Treasury" and variants) |
| Read | `parse_fwp.py` | Parses each term sheet's tables: size, coupon, maturity, CUSIP, spread, yield, price, make-whole, par call, ratings |
| Prospectus only | `prospectus_deals.py` | Amazon, Oracle, Microsoft: price from the filing fee table, yield and spread computed over the Treasury curve |
| Structure | `structure.py`, `rules.py` | Ranking, guarantees, change of control, coupon steps from the term sheet and prospectus supplement |
| Proceeds | `proceeds.py`, `rules.py` | Use of proceeds: named acquisition, named debt to repay, or general corporate purposes |
| Enrich | `fred.py`, `enrich.py` | Index spreads and the Treasury curve from FRED; spread vs index for US dollar fixed rate bonds |
| Macro | `macro.py` | Inflation, jobs, the fed funds target, Fed decision and CPI and jobs report dates |
| Clean | `dedupe.py` | A bond filed twice counts once (CUSIP, or issuer + coupon + maturity) |
| Model | `model.py` | Ridge regression refit weekly on earlier deals only; scores each new bond out of sample |
| Test | `thesis.py` | Matched comparisons (same issuer and day, else same rating and maturity), resampled by issuer |
| Publish | `report.py` | Builds the six-page site into `site/` |

`python parse_fwp.py --check` scores the parser against 215 bonds extracted earlier by an LLM
and checked by hand: it finds 213, with coupon and maturity right on all of them and yield and
price on 99%. `extract.py` and `agent.py` are the earlier LLM versions, kept for reference.

## Checks

Every tranche is validated against its own arithmetic: benchmark yield plus spread
should equal the yield. Failures are flagged, not discarded. Floaters (spread to SOFR) and
non-dollar bonds (spread to Bunds or gilts) are kept out of the index comparison.

## Limits

Registered deals only, so most 144A high yield is out of scope. Index spreads are
option-adjusted and matched by rating category, so the comparison is directional.
Filings do not disclose order books, price talk or new issue concession.

Not investment advice.
