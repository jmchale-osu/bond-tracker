"""
The agent: answers questions about the deals, and writes the weekly recap.

    python agent.py recap                      write the weekly recap to recap.md
    python agent.py "widest BBB deals in September?"
    python agent.py                            interactive, ask until you quit

It can only use numbers its tools return. The tools query your database and,
when it needs the issuer's own words, pull the filing back from EDGAR.
"""
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic
from edgar import set_identity, find

import db
from extract import MODEL

load_dotenv()
set_identity("James McHale jtmchale912@gmail.com")

RECAP_PATH = Path(__file__).resolve().parent / "recap.md"
MAX_STEPS = 8

SYSTEM = """You are a credit markets analyst working with a database of new corporate
bond issues read out of SEC filings.

Rules you must follow:
- Every number you state must come from a tool result in this conversation. Never
  estimate, never fill a gap from memory, never carry a number over from training data.
- If the tools do not answer the question, say exactly what is missing.
- "spread_vs_index_bps" is a deal's spread minus the matching ICE BofA index on its
  pricing date. Positive means it priced wider, which is cheaper for the buyer.
  Say "wide of" or "over" the index for a positive gap and "through" or "inside" only
  for a negative one. "Through" never describes a wider spread.
- Spreads are in basis points. Sizes are in dollars. Report sizes in millions or billions.
- The data covers SEC-registered deals only, so most high yield (sold under Rule 144A)
  is missing. Say so if a question is about the high yield market as a whole.
- Small samples are normal here. Give the count alongside any median or average.
- Write like a desk note: short sentences, specifics, no filler, no hedging language
  like "it appears that". Name issuers.
"""

TOOLS = [
    {
        "name": "query_tranches",
        "description": "List individual bonds, filtered and sorted. Use for 'which deals' questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": ["string", "null"], "description": "YYYY-MM-DD, pricing date on or after"},
                "end_date": {"type": ["string", "null"], "description": "YYYY-MM-DD, pricing date on or before"},
                "grade": {"type": ["string", "null"], "enum": ["IG", "HY", "split", None]},
                "proceeds": {"type": ["string", "null"], "description": "acquisition, refinancing, general_corporate, capex, shareholder_returns, mixed, not_stated"},
                "maturity_bucket": {"type": ["string", "null"], "description": "1-3y, 3-5y, 5-7y, 7-10y, 10-15y, 15y+"},
                "issuer_contains": {"type": ["string", "null"]},
                "order_by": {"type": "string", "enum": ["spread_vs_index_desc", "spread_vs_index_asc",
                                                        "size_desc", "date_desc", "spread_desc"]},
                "limit": {"type": "integer", "description": "1 to 50"},
            },
            "required": ["order_by", "limit"],
        },
    },
    {
        "name": "aggregate",
        "description": "Totals, counts and medians, optionally grouped. Use for 'how much', 'how many', 'typical' questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "group_by": {"type": "string", "enum": ["none", "week", "grade", "proceeds", "maturity_bucket", "issuer"]},
                "start_date": {"type": ["string", "null"]},
                "end_date": {"type": ["string", "null"]},
                "grade": {"type": ["string", "null"]},
                "proceeds": {"type": ["string", "null"]},
            },
            "required": ["group_by"],
        },
    },
    {
        "name": "read_filing",
        "description": ("Re-read the original SEC filing for a bond, to quote the issuer's own words or check "
                        "a term the database does not store. Give the bond_key from query_tranches, and a "
                        "phrase to search for inside the document."),
        "input_schema": {
            "type": "object",
            "properties": {
                "bond_key": {"type": "string", "description": "the bond_key returned by query_tranches"},
                "search_for": {"type": "string", "description": "e.g. 'use of proceeds', 'change of control', 'ranking'"},
            },
            "required": ["bond_key", "search_for"],
        },
    },
]

SELECT = """
    SELECT t.bond_key, d.issuer, t.title, t.principal_usd, t.coupon_pct, t.maturity_date,
           t.spread_bps, t.spread_vs_index_bps, t.grade, t.maturity_bucket,
           t.rating_moodys, t.rating_sp, d.use_of_proceeds, d.proceeds_quote,
           COALESCE(d.trade_date, d.filing_date) AS priced, d.bookrunners
    FROM tranches t JOIN deals d ON d.accession = t.accession
"""
PRICED = "COALESCE(d.trade_date, d.filing_date)"
ORDER = {
    "spread_vs_index_desc": "t.spread_vs_index_bps DESC",
    "spread_vs_index_asc": "t.spread_vs_index_bps ASC",
    "size_desc": "t.principal_usd DESC",
    "date_desc": "priced DESC",
    "spread_desc": "t.spread_bps DESC",
}


def where(args):
    clauses, params = [], []
    pairs = [(f"{PRICED} >= ?", args.get("start_date")), (f"{PRICED} <= ?", args.get("end_date")),
             ("t.grade = ?", args.get("grade")), ("d.use_of_proceeds = ?", args.get("proceeds")),
             ("t.maturity_bucket = ?", args.get("maturity_bucket"))]
    for clause, value in pairs:
        if value:
            clauses.append(clause)
            params.append(value)
    if args.get("issuer_contains"):
        clauses.append("LOWER(d.issuer) LIKE ?")
        params.append(f"%{args['issuer_contains'].lower()}%")
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


def query_tranches(conn, args):
    sql_where, params = where(args)
    order = ORDER.get(args.get("order_by", "date_desc"), ORDER["date_desc"])
    skip_null = ""
    if "spread_vs_index" in args.get("order_by", ""):
        skip_null = ("AND " if sql_where else "WHERE ") + "t.spread_vs_index_bps IS NOT NULL"
    limit = max(1, min(int(args.get("limit", 10)), 50))
    rows = conn.execute(f"{SELECT} {sql_where} {skip_null} ORDER BY {order} LIMIT {limit}", params).fetchall()
    cols = ["bond_key", "issuer", "title", "size_usd", "coupon_pct", "maturity", "spread_bps",
            "spread_vs_index_bps", "grade", "maturity_bucket", "moodys", "sp",
            "use_of_proceeds", "proceeds_quote", "priced", "bookrunners"]
    return [dict(zip(cols, r)) for r in rows]


def aggregate(conn, args):
    sql_where, params = where(args)
    group = args.get("group_by", "none")
    expr = {
        "none": "'all'",
        "week": f"strftime('%Y-%W', {PRICED})",
        "grade": "t.grade",
        "proceeds": "d.use_of_proceeds",
        "maturity_bucket": "t.maturity_bucket",
        "issuer": "d.issuer",
    }[group]
    rows = conn.execute(f"""
        SELECT {expr} AS bucket, COUNT(*),
               SUM(t.principal_usd),
               AVG(t.spread_vs_index_bps),
               MIN({PRICED}), MAX({PRICED})
        FROM tranches t JOIN deals d ON d.accession = t.accession
        {sql_where}
        GROUP BY bucket ORDER BY bucket
    """, params).fetchall()

    out = []
    for bucket, count, total, avg_gap, first, last in rows:
        gaps = conn.execute(f"""
            SELECT t.spread_vs_index_bps FROM tranches t JOIN deals d ON d.accession = t.accession
            {sql_where} {"AND" if sql_where else "WHERE"} {expr} = ?
            AND t.spread_vs_index_bps IS NOT NULL ORDER BY t.spread_vs_index_bps
        """, params + [bucket]).fetchall()
        values = [g[0] for g in gaps]
        median_gap = None
        if values:
            mid = len(values) // 2
            median_gap = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
        out.append({
            "group": bucket, "tranches": count,
            "volume_usd": total,
            "median_spread_vs_index_bps": median_gap,
            "tranches_with_index_comparison": len(values),
            "first_priced": first, "last_priced": last,
        })
    return out


def read_filing(conn, args):
    """Go back to EDGAR and pull the passage the agent asked about."""
    row = conn.execute("""
        SELECT t.accession, d.issuer, d.url FROM tranches t JOIN deals d ON d.accession = t.accession
        WHERE t.bond_key = ?""", (args["bond_key"],)).fetchone()
    if not row:
        return {"error": f"no bond with key {args['bond_key']}"}
    accession, issuer, url = row
    try:
        text = find(accession).text()
    except Exception as e:
        return {"error": f"could not fetch {accession}: {e}"}

    needle = args["search_for"].lower()
    where_at = text.lower().find(needle)
    passage = text[max(0, where_at - 200):where_at + 2500] if where_at >= 0 else text[:2500]
    return {
        "issuer": issuer, "accession": accession, "source_url": url,
        "found_search_phrase": where_at >= 0,
        "passage": " ".join(passage.split()),
    }


HANDLERS = {"query_tranches": query_tranches, "aggregate": aggregate, "read_filing": read_filing}


def ask(question, conn, client, verbose=True):
    messages = [{"role": "user", "content": question}]
    for step in range(MAX_STEPS):
        response = client.messages.create(
            model=MODEL, max_tokens=2000, system=SYSTEM, tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": response.content})

        calls = [b for b in response.content if b.type == "tool_use"]
        if not calls:
            return "".join(b.text for b in response.content if b.type == "text")

        results = []
        for call in calls:
            if verbose:
                print(f"  [{call.name}] {json.dumps(call.input)[:110]}")
            try:
                output = HANDLERS[call.name](conn, call.input)
            except (sqlite3.Error, KeyError, ValueError) as e:
                output = {"error": str(e)}
            results.append({"type": "tool_result", "tool_use_id": call.id,
                            "content": json.dumps(output, default=str)[:20000]})
        messages.append({"role": "user", "content": results})
    return "Stopped after too many steps."


RECAP_PROMPT = """Write this week's primary market recap, covering {start} to {end}.

Use the tools to get: total volume and tranche count for the week, how that compares with
the four weeks before it, the largest deals, the mix by use of proceeds, and the tranches
that priced widest and tightest versus their index.

Structure, about 220 words:
1. One opening sentence: volume, number of tranches, and how it compares with recent weeks.
2. The notable deals, with issuer, size, tenor and spread.
3. What priced cheap or rich versus the index, and any pattern worth naming.
4. One closing line on what the mix of use of proceeds says about why companies issued.

Plain markdown, no headings, no bullet points. If the week has no deals, say that in one line."""


def main():
    conn = db.connect()
    client = Anthropic()
    args = sys.argv[1:]

    if args and args[0] == "recap":
        last = conn.execute("SELECT MAX(COALESCE(trade_date, filing_date)) FROM deals").fetchone()[0]
        end = date.fromisoformat(last) if last else date.today()
        start = end - timedelta(days=6)
        print(f"Writing the recap for {start} to {end}\n")
        text = ask(RECAP_PROMPT.format(start=start, end=end), conn, client)
        RECAP_PATH.write_text(f"<!-- {start} to {end}, written {date.today()} -->\n{text.strip()}\n")
        print(f"\n{text}\n\nSaved to {RECAP_PATH.name}. Run report.py then extras.py to put it on the page.")
        return

    if args:
        print(ask(" ".join(args), conn, client))
        return

    print("Ask about the deals. Ctrl+C to quit.\n")
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if question:
            print(f"\n{ask(question, conn, client)}\n")


if __name__ == "__main__":
    main()
