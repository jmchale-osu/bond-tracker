"""
Fill in use of proceeds from each deal's prospectus (424B5).

Term sheets carry the numbers; the prospectus carries the "Use of Proceeds"
section. This finds the matching 424B5 for any deal that is missing it.

Run:  python proceeds.py            (all deals missing it)
      python proceeds.py --limit 5  (try a few first)
"""
import re
import sys

from dotenv import load_dotenv
from anthropic import Anthropic
from edgar import set_identity, Company

import db
from extract import MODEL

load_dotenv()
set_identity("James McHale jtmchale912@gmail.com")

SECTION = re.compile(r"USE\s+OF\s+PROCEEDS", re.I)

PROCEEDS_TOOL = {
    "name": "record_use_of_proceeds",
    "description": "Record what the issuer says it will do with the money.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["acquisition", "refinancing", "general_corporate", "capex",
                         "shareholder_returns", "mixed", "not_stated"],
            },
            "quote": {"type": ["string", "null"], "description": "verbatim, under 200 characters"},
        },
        "required": ["category", "quote"],
    },
}

PROMPT = """This is the Use of Proceeds section of a bond prospectus.
Record the category and a verbatim quote using the tool.

Decide by what the issuer actually commits to:
- "acquisition" if the proceeds fund a named acquisition, merger or purchase, including
  deals conditioned on one closing.
- "refinancing" if the main stated use is repaying, redeeming or refinancing identified
  debt (named notes, a term loan, commercial paper).
- "general_corporate" if it is the standard list of general corporate purposes, even when
  that list mentions working capital, capital expenditure or repaying short-term borrowings
  as examples. Boilerplate breadth is not "mixed".
- "mixed" only when the issuer gives real weight to two specific uses, such as funding a
  named acquisition AND redeeming named notes.
- "not_stated" if the section says nothing usable.

<section>
{text}
</section>"""


def find_prospectus(cik, filing_date):
    """A 424B5 from the same issuer within a week of the term sheet."""
    filings = Company(int(cik)).get_filings(form="424B5")
    best = None
    for f in filings:
        gap = abs((f.filing_date - filing_date).days) if hasattr(f.filing_date, "days") or True else 99
        try:
            gap = abs((f.filing_date - filing_date).days)
        except TypeError:
            continue
        if gap <= 7 and (best is None or gap < best[0]):
            best = (gap, f)
    return best[1] if best else None


SPECIFIC = [
    (re.compile(r"acquisition|merger|purchase of", re.I), 3),
    (re.compile(r"redeem|repay|refinanc|retire|tender offer", re.I), 3),
    (re.compile(r"\$\s?[\d,]{7,}|approximately \$", re.I), 2),
    (re.compile(r"notes? due 20\d\d", re.I), 2),
    (re.compile(r"revolving credit|term loan|commercial paper", re.I), 1),
]


def proceeds_section(text):
    """The most deal-specific Use of Proceeds section, not the base prospectus boilerplate."""
    best, best_score = None, -1
    for hit in SECTION.finditer(text):
        chunk = text[hit.start():hit.start() + 4000]
        score = sum(points for pattern, points in SPECIFIC if pattern.search(chunk))
        if score > best_score:
            best, best_score = chunk, score
    return best


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    conn = db.connect()
    rows = conn.execute("""
        SELECT accession, issuer, filing_date, url FROM deals
        WHERE (use_of_proceeds IS NULL OR use_of_proceeds = 'not_stated')
        ORDER BY filing_date DESC
    """).fetchall()
    if limit:
        rows = rows[:limit]
    print(f"{len(rows)} deals missing use of proceeds\n")

    client = Anthropic()
    filled = missed = 0
    for i, (accession, issuer, filing_date, url) in enumerate(rows, 1):
        cik = url.split("/data/")[1].split("/")[0] if url and "/data/" in url else None
        print(f"[{i}/{len(rows)}] {(issuer or '')[:40]}")
        try:
            from datetime import date
            target = date.fromisoformat(filing_date)
            prospectus = find_prospectus(cik, target)
            if prospectus is None:
                print("  no 424B5 within a week\n")
                missed += 1
                continue
            section = proceeds_section(prospectus.text())
            if not section:
                print("  no Use of Proceeds section found\n")
                missed += 1
                continue
            response = client.messages.create(
                model=MODEL, max_tokens=400, tools=[PROCEEDS_TOOL],
                tool_choice={"type": "tool", "name": "record_use_of_proceeds"},
                messages=[{"role": "user", "content": PROMPT.format(text=section)}],
            )
            result = next(b.input for b in response.content if b.type == "tool_use")
            conn.execute("""UPDATE deals SET use_of_proceeds = ?, proceeds_quote = ?,
                            proceeds_source = '424b5' WHERE accession = ?""",
                         (result["category"], result.get("quote"), accession))
            conn.commit()
            filled += 1
            print(f"  {result['category']}: {(result.get('quote') or '')[:70]}\n")
        except Exception as e:
            missed += 1
            print(f"  FAILED: {e}\n")

    print(f"Done. {filled} filled in, {missed} missed.")


if __name__ == "__main__":
    main()
