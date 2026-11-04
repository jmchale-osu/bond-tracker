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
backfill.py → proceeds.py → structure.py → issuer_info.py → fred.py → dedupe.py → enrich.py → agent.py recap → report.py
- Data: `data/bonds.db` (SQLite, committed). Term sheets come from EDGAR FWP/424B filings, extracted by Claude. Index spreads are ICE BofA OAS from FRED.
- `ANTHROPIC_API_KEY` lives in `.env` locally and as a repo secret. `weekly.py` checks the key first and stops on a 401.

## Thesis ("structure is priced")
- `thesis.py` scores five claims: subordination, collateral, change of control put, coupon step and acquisition funding.
- Peers are matched on the same issuer, day and maturity bucket where possible; otherwise on rating bucket × maturity bucket, using the gap vs the index.
- The range comes from a resample by issuer (1,000 draws, 5th–95th percentile).
- Verdicts: Holding / Not holding / Mixed / Too early (fewer than 5 bonds or fewer than 3 issuers).
- `report.py` builds the five pages in `site/`: index, evidence, market, deals, method.

## Writing on the site
No em dashes. Use "wide of" or "over" for a positive spread gap; "through" or "inside" only for a negative one.

## Context lives in Obsidian
- Vault: `/Users/jamesmchale/Library/Mobile Documents/com~apple~CloudDocs/claude/James Vault`. Read its `CLAUDE.md` before writing there.
- Project note: `Notes/Projects/New Issue Bond Tracker.md`. Session logs: `Notes/Logs/YYYY-MM-DD Title.md` (Session Log template).
- Start a session by reading the project note and the latest bond tracker log, instead of searching old transcripts.
- At the end of a session that changed anything, write a short log note and update the project note's status and next steps.
