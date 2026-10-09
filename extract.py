"""
Step 1 of the AI layer: turn a pricing term sheet (FWP) into structured data.

Run:  python extract.py                         (tests on the Xylem FWP)
      python extract.py 0001193125-26-392006    (any FWP accession number)
"""
import sys
import json

from dotenv import load_dotenv
from anthropic import Anthropic
from edgar import set_identity, find

load_dotenv()
set_identity("James McHale jtmchale912@gmail.com")

# Check docs.claude.com/en/docs/about-claude/models for the current Sonnet model name
MODEL = "claude-sonnet-4-5"
XYLEM_FWP = "0001193125-26-392006"

TERMS_TOOL = {
    "name": "record_bond_terms",
    "description": "Record the terms of every tranche in this bond pricing term sheet.",
    "input_schema": {
        "type": "object",
        "properties": {
            "issuer": {"type": "string"},
            "trade_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            "settlement_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            "bookrunners": {"type": "array", "items": {"type": "string"}},
            "use_of_proceeds_category": {
                "type": ["string", "null"],
                "enum": ["acquisition", "refinancing", "general_corporate", "capex",
                         "shareholder_returns", "mixed", "not_stated", None],
                "description": "null if the document does not say",
            },
            "use_of_proceeds_quote": {"type": ["string", "null"], "description": "verbatim, under 200 characters"},
            "tranches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "principal_usd": {"type": ["number", "null"]},
                        "coupon_pct": {"type": ["number", "null"]},
                        "maturity_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                        "benchmark_treasury": {"type": ["string", "null"]},
                        "benchmark_yield_pct": {"type": ["number", "null"]},
                        "spread_bps": {"type": ["number", "null"]},
                        "yield_pct": {"type": ["number", "null"]},
                        "price_pct_of_par": {"type": ["number", "null"]},
                        "make_whole_bps": {"type": ["number", "null"]},
                        "par_call_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                        "rating_moodys": {"type": ["string", "null"]},
                        "rating_sp": {"type": ["string", "null"]},
                        "rating_fitch": {"type": ["string", "null"]},
                    },
                    "required": ["title", "principal_usd", "coupon_pct", "maturity_date", "spread_bps", "yield_pct", "price_pct_of_par"],
                },
            },
        },
        "required": ["issuer", "tranches"],
    },
}

PROMPT = """Below is an SEC filing: a pricing term sheet for a corporate bond offering.
Extract the terms of every tranche using the record_bond_terms tool.

Rules:
- Use only numbers written in the document. Never estimate or calculate a value.
- If a field is not in the document, use null.
- Percentages as plain numbers (5.250% -> 5.25). Spreads in basis points (+50 bps -> 50).
- Dates as YYYY-MM-DD.
- Use of proceeds: only if the document states it. Quote it verbatim and pick a category.
  Funding an acquisition is "acquisition". Repaying or redeeming existing debt is
  "refinancing". If it says both, use "mixed". If the document is silent, use null.

<document>
{text}
</document>"""

XYLEM_GOLD = [
    {"coupon_pct": 5.25, "spread_bps": 50, "yield_pct": 5.265, "price_pct_of_par": 99.959, "maturity_date": "2029-09-28"},
    {"coupon_pct": 5.45, "spread_bps": 65, "yield_pct": 5.487, "price_pct_of_par": 99.841, "maturity_date": "2032-01-15"},
    {"coupon_pct": 5.85, "spread_bps": 85, "yield_pct": 5.862, "price_pct_of_par": 99.918, "maturity_date": "2037-01-15"},
]


def extract(accession):
    filing = find(accession)
    text = filing.text()
    print(f"{filing.company} | {filing.form} | {filing.filing_date} | {len(text):,} characters")
    response = Anthropic().messages.create(
        model=MODEL,
        max_tokens=4000,
        tools=[TERMS_TOOL],
        tool_choice={"type": "tool", "name": "record_bond_terms"},
        messages=[{"role": "user", "content": PROMPT.format(text=text[:60000])}],
    )
    terms = next(block.input for block in response.content if block.type == "tool_use")
    print(f"Tokens used: {response.usage.input_tokens:,} in, {response.usage.output_tokens:,} out\n")
    return terms


def check_math(terms):
    for t in terms["tranches"]:
        b, s, y = t.get("benchmark_yield_pct"), t.get("spread_bps"), t.get("yield_pct")
        if None in (b, s, y):
            continue
        ok = abs(b + s / 100 - y) < 0.002
        print(f"  {t['title'][:40]:40} {b} + {s}bps = {b + s / 100:.3f} vs {y}  {'OK' if ok else 'MISMATCH'}")


def grade(terms, gold):
    right = total = 0
    for got, want in zip(terms["tranches"], gold):
        for field, value in want.items():
            total += 1
            if got.get(field) == value:
                right += 1
            else:
                print(f"  WRONG {field}: got {got.get(field)}, expected {value}")
    print(f"\nScore: {right}/{total} fields correct")


if __name__ == "__main__":
    accession = sys.argv[1] if len(sys.argv) > 1 else XYLEM_FWP
    terms = extract(accession)
    print(json.dumps(terms, indent=2))
    print("\nMath check:")
    check_math(terms)
    if accession == XYLEM_FWP:
        grade(terms, XYLEM_GOLD)
