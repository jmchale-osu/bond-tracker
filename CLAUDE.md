# Bond tracker: notes for Claude

New-issue investment-grade bond tracker. A resume project for James (recruiting for credit / DCM). Live site: https://jmchale-osu.github.io/bond-tracker/

## Work without asking
- James wants you to act on your own. Commit, push, rerun the pipeline, rebuild the site and trigger the workflow without checking in.
- Only stop for what you genuinely cannot do: creating or rotating API keys, signing in, paying for anything.
- Copying keys that already exist in `.env` into GitHub secrets is pre-approved (`gh secret set NAME --repo jmchale-osu/bond-tracker --body ...`). Never print key values.

## Publishing
- Remote repo: `jmchale-osu/bond-tracker`. GitHub Pages builds from the Actions workflow (`.github/workflows/weekly.yml`), not from a branch.
- This local checkout has no remote. To publish, clone the remote into the scratchpad, copy the changed files in, commit and push:
  `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push`
- `gh` is at `/opt/homebrew/bin/gh`, logged in as jmchale-osu.
- The workflow runs Mondays 13:00 UTC, on demand (`gh workflow run "Weekly update" -R jmchale-osu/bond-tracker`), and republishes on any push that touches `site/`.

## Pipeline (`python weekly.py`, or `--dry-run`)
backfill.py → fred.py → macro.py → prospectus_deals.py → proceeds.py → structure.py → issuer_info.py → dedupe.py → enrich.py → model.py → report.py
- No paid APIs. Term sheets are found with EDGAR full-text search and read by `parse_fwp.py` (rules, no LLM). `python parse_fwp.py --check` scores it against the 215 LLM-extracted bonds; rerun it after changing the parser.
- Use of proceeds and structure come from `rules.py`. Amazon, Oracle and Microsoft file no FWP: `prospectus_deals.py` computes their spreads from the filing fee table (math_check = 'computed', kept out of the index comparison).
- SEC requests use `db.SEC_IDENTITY` as the User-Agent (SEC requires a contact). Keep requests under 10 a second.
- Data: `data/bonds.db` (SQLite, committed). Raw HTML cache in `data/html/` (not committed). Index spreads and the Treasury curve are from FRED.
- Only US dollar fixed rate bonds get a spread vs index (floaters are a spread to SOFR; euro bonds to Bunds).
- `model.py`: ridge regression refit each week on earlier deals; tables model_bonds, model_weeks, model_terms.

## Thesis ("structure is priced")
- `thesis.py` scores five claims: subordination, collateral, change of control put, coupon step and acquisition funding.
- Peers are matched on the same issuer, day and maturity bucket where possible; otherwise on rating bucket × maturity bucket, using the gap vs the index.
- The range comes from a resample by issuer (1,000 draws, 5th–95th percentile).
- Verdicts: Holding / Not holding / Mixed / Too early (fewer than 5 bonds or fewer than 3 issuers).
- `thesis.TIMING` tests whether bonds priced around Fed, CPI and jobs days come wider. It uses the same method but sits on the Market page, off the scorecard, because timing is not a prospectus term.
- `report.py` builds the five pages in `site/`: index, evidence, market, deals, method.

## Writing on the site
No em dashes. Use "wide of" or "over" for a positive spread gap; "through" or "inside" only for a negative one.

## Context lives in Obsidian
- Vault: `/Users/jamesmchale/Library/Mobile Documents/com~apple~CloudDocs/claude/James Vault`. Read its `CLAUDE.md` before writing there.
- Project note: `Notes/Projects/New Issue Bond Tracker.md`. Session logs: `Notes/Logs/YYYY-MM-DD Title.md` (Session Log template).
- Start a session by reading the project note and the latest bond tracker log, instead of searching old transcripts.
- At the end of a session that changed anything, write a short log note and update the project note's status and next steps.
