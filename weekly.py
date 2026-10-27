"""
The weekly update: find new deals, read them, compare them to the index, rebuild the site.

    python weekly.py            run every step
    python weekly.py --dry-run  show what backfill would pick up, change nothing

Runs every Monday on GitHub Actions (.github/workflows/weekly.yml), and works the same
locally. Each step only does work that is missing, so a rerun is cheap. The search window
reaches back a week past the newest deal in the database, so a missed week is caught up
and filings that arrive late are not lost. Any failing step stops the run before the site
is rebuilt.
"""
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

import db

HERE = Path(__file__).resolve().parent
MIN_DAYS = 10


def window():
    """Days back to search: from a week before the newest deal we have, at least MIN_DAYS."""
    last = db.connect().execute("SELECT MAX(filing_date) FROM deals").fetchone()[0]
    if not last:
        return 30
    return max(MIN_DAYS, (date.today() - date.fromisoformat(last)).days + 7)


def run(*args):
    print(f"\n=== {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, *args], cwd=HERE, check=True)


def main():
    load_dotenv(HERE / ".env")
    days = window()
    if "--dry-run" in sys.argv:
        run("backfill.py", str(days), "--dry-run")
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Add it to .env locally, or as a repository secret on GitHub.")

    run("backfill.py", str(days))       # new term sheets, extracted by Claude
    run("proceeds.py")                  # use of proceeds, for deals missing it
    run("structure.py")                 # ranking, guarantees, CoC, coupon steps, for deals missing them
    run("issuer_info.py")               # sector and domicile from EDGAR
    run("fred.py")                      # index spreads and Treasury yields
    run("dedupe.py")                    # a deal filed twice counts once
    run("enrich.py")                    # spread vs index
    run("agent.py", "recap")            # the weekly note
    run("report.py")                    # the site
    print(f"\nWeekly update done: searched the last {days} days.")


if __name__ == "__main__":
    main()
