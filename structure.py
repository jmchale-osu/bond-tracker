"""
Read each deal's prospectus for the structural terms Bill asked about:
ranking, security, guarantees, change of control protection, coupon steps.

    python structure.py --limit 5    try a few first
    python structure.py              everything missing
    python structure.py --redo       re-read every deal (use after changing this file)

Costs roughly a cent per deal. Run migrate_v2.py once before this.
"""
import re
import sys
from pathlib import Path
from datetime import date, timedelta

from dotenv import load_dotenv
from anthropic import Anthropic
from edgar import set_identity, Company

import db
from extract import MODEL

load_dotenv()
set_identity("James McHale jtmchale912@gmail.com")

# The parts of a prospectus where these terms live
SECTIONS = [
    re.compile(r"\branking\b", re.I),
    re.compile(r"\bguarantee", re.I),
    re.compile(r"change of control", re.I),
    re.compile(r"interest rate adjustment|coupon step|rating event|step[- ]up", re.I),
]

TOOL = {
    "name": "record_structure",
    "description": "Record the structural terms of these notes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ranking": {
                "type": "string",
                "enum": ["senior_unsecured", "senior_secured", "first_mortgage",
                         "subordinated", "junior_subordinated", "other", "not_stated"],
            },
            "is_secured": {"type": "boolean"},
            "guarantees": {
                "type": "string",
                "enum": ["none", "parent", "subsidiaries", "both", "not_stated"],
                "description": ("who guarantees the notes. A finance subsidiary's notes guaranteed by the "
                                "parent company are 'parent'. Operating subsidiaries guaranteeing the parent's "
                                "notes are 'subsidiaries'."),
            },
            "guarantor_note": {"type": ["string", "null"], "description": "under 120 characters"},
            "change_of_control": {
                "type": "boolean",
                "description": "true only if holders can require repurchase on a change of control",
            },
            "change_of_control_price": {
                "type": ["number", "null"],
                "description": "percent of principal, usually 101. null if there is no such provision",
            },
            "coupon_step": {
                "type": "boolean",
                "description": ("true only if the interest rate on these notes rises when their credit "
                                "ratings are downgraded, or on a sustainability-linked target miss. A change "
                                "of control repurchase that needs a rating downgrade to trigger is NOT a coupon step."),
            },
            "coupon_step_note": {"type": ["string", "null"], "description": "under 120 characters"},
            "quote": {"type": "string", "description": "verbatim sentence on ranking, under 200 characters"},
        },
        "required": ["ranking", "is_secured", "guarantees", "change_of_control", "coupon_step", "quote"],
    },
}

PROMPT = """Below are excerpts from a corporate bond offering: the pricing term sheet and, when
we found it, the prospectus supplement for the same notes. Record the structural terms.

Only report what the documents say. The prospectus supplement is the authority on ranking,
security and guarantees; the term sheet often lists change of control terms. If neither covers
something, use "not_stated" or false rather than assuming the market standard. Use guarantees
"none" only when the document says the notes are not guaranteed, or describes them as solely
the issuer's obligations.

{text}"""


RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"


def cached_text(accession):
    """The term sheet we already downloaded."""
    path = RAW_DIR / f"{accession}.txt"
    return path.read_text() if path.exists() else ""


def filing_text(filing):
    """Text of a filing, cached on disk. Falls back to the raw attachment when edgartools can't parse it."""
    path = RAW_DIR / f"prospectus_{filing.accession_no}.txt"
    if path.exists():
        return path.read_text()
    text = ""
    try:
        text = filing.text() or ""
    except Exception:
        pass
    if len(text) < 2000:
        try:
            for a in filing.attachments:
                name = (getattr(a, "document", "") or "").lower()
                if name.endswith((".htm", ".html", ".txt")) and "ex" not in name.split(".")[0][-6:]:
                    raw = a.download()
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", "ignore")
                    raw = re.sub(r"(?s)<(script|style).*?</\1>", " ", raw or "")
                    raw = re.sub(r"<[^>]+>", " ", raw)
                    raw = re.sub(r"&nbsp;|&#160;", " ", raw)
                    if len(raw) > len(text):
                        text = raw
                    break
        except Exception:
            pass
    if text:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return text


def deal_keys(conn, accession):
    """CUSIPs and coupons of this deal, used to prove a prospectus is the right one."""
    cusips, coupons = set(), set()
    for cusip, coupon in conn.execute(
            "SELECT cusip, coupon_pct FROM tranches WHERE accession = ?", (accession,)):
        if cusip and len(cusip) >= 8:
            cusips.add(cusip.upper()[:9])
        if coupon:
            coupons.add(f"{coupon:.3f}%")
            coupons.add(f"{coupon:.2f}%")
    return cusips, coupons


def candidates(cik, filing_date, window):
    if not cik:
        return []
    try:
        company = Company(int(cik))
    except Exception:
        return []
    start = (filing_date - timedelta(days=window)).isoformat()
    end = (filing_date + timedelta(days=window)).isoformat()
    found = []
    for form in ("424B5", "424B2"):
        try:
            filings = company.get_filings(form=form, filing_date=f"{start}:{end}")
        except Exception:
            filings = None
        if filings is None:
            continue
        try:
            for f in filings:
                gap = abs((f.filing_date - filing_date).days)
                if gap <= window:
                    found.append((gap, form != "424B5", f))
        except Exception:
            continue
    found.sort(key=lambda x: (x[0], x[1]))
    return [f for _, _, f in found[:6]]


def find_prospectus(conn, accession, cik, filing_date, window=21):
    """The prospectus supplement that contains this deal's CUSIP, or failing that its coupon."""
    cusips, coupons = deal_keys(conn, accession)
    fallback = None
    for f in candidates(cik, filing_date, window):
        text = filing_text(f)
        if len(text) < 2000:
            continue
        flat = text.upper()
        if any(c in flat for c in cusips):
            return text, "cusip"
        if fallback is None and coupons and any(c in text for c in coupons):
            fallback = text
    return (fallback, "coupon") if fallback else (None, None)


def excerpts(text, window=3000, cap=16000):
    """Stitch together the passages that mention each structural term."""
    out, used = [], []
    for pattern in SECTIONS:
        for hit in pattern.finditer(text):
            start, end = max(0, hit.start() - 400), hit.start() + window
            if any(start < u_end and u_start < end for u_start, u_end in used):
                continue
            used.append((start, end))
            out.append(" ".join(text[start:end].split()))
            break                      # one passage per term is enough
    return "\n\n...\n\n".join(out)[:cap]


def ranking_from_titles(titles):
    """The ranking the notes' own names state, when every tranche in the deal agrees. A fallback
    prospectus matched by coupon can belong to a concurrent offering of different notes."""
    titles = [(t or "").lower() for t in titles]
    if not titles:
        return None
    for word, ranking in (("junior subordinated", "junior_subordinated"),
                          ("subordinated", "subordinated"),
                          ("first mortgage", "first_mortgage"),
                          ("senior secured", "senior_secured")):
        if all(word in t for t in titles):
            return ranking
    return None


def check_ranking(conn, accession, ranking):
    """Override a senior ranking the tranche titles contradict."""
    titles = [t for (t,) in conn.execute("SELECT title FROM tranches WHERE accession = ?", (accession,))]
    stated = ranking_from_titles(titles)
    if stated and stated != ranking and ranking in ("senior_unsecured", "senior_secured", "not_stated"):
        return stated
    return ranking


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    redo = "--redo" in sys.argv
    conn = db.connect()
    rows = conn.execute(f"""
        SELECT accession, issuer, filing_date, url FROM deals
        {"WHERE structure_source IS NULL OR structure_source NOT LIKE '%424b:%'" if redo
         else "WHERE ranking IS NULL"} ORDER BY filing_date DESC
    """).fetchall()
    if limit:
        rows = rows[:limit]
    print(f"{len(rows)} deals to read{' (redo)' if redo else ''}\n")

    client = Anthropic()
    filled = missed = 0
    for i, (accession, issuer, filing_date, url) in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {(issuer or '')[:42]}")
        cik = url.split("/data/")[1].split("/")[0] if url and "/data/" in url else None
        try:
            fwp = cached_text(accession)
            fwp_part = " ".join(fwp.split())[:6000]
            prospectus, matched = find_prospectus(conn, accession, cik, date.fromisoformat(filing_date))
            pro_part = excerpts(prospectus) if prospectus else ""

            parts = []
            if fwp_part:
                parts.append(f"<term_sheet>\n{fwp_part}\n</term_sheet>")
            if pro_part:
                parts.append(f"<prospectus_supplement>\n{pro_part}\n</prospectus_supplement>")
            source = "+".join(n for n, x in (("fwp", fwp_part), (f"424b:{matched}", pro_part)) if x)
            if sum(len(x) for x in (fwp_part, pro_part)) < 400:
                print("  nothing to read\n")
                missed += 1
                continue

            response = client.messages.create(
                model=MODEL, max_tokens=800, tools=[TOOL],
                tool_choice={"type": "tool", "name": "record_structure"},
                messages=[{"role": "user", "content": PROMPT.format(text="\n\n".join(parts))}],
            )
            r = next(b.input for b in response.content if b.type == "tool_use")
            note = (r.get("coupon_step_note") or "").lower()
            if r["coupon_step"] and ("change of control" in note or "repurchase" in note):
                r["coupon_step"] = False      # a rating trigger on the put, not a coupon step
            ranking = check_ranking(conn, accession, r["ranking"])
            if ranking != r["ranking"]:
                print(f"  ranking {r['ranking']} contradicts the note titles, using {ranking}")
                r["ranking"], r["quote"] = ranking, f"(from note titles; matched prospectus disagreed) {r['quote']}"
            conn.execute("""
                UPDATE deals SET ranking=?, is_secured=?, guarantees=?, guarantor_note=?,
                       change_of_control=?, change_of_control_price=?, coupon_step=?,
                       coupon_step_note=?, structure_quote=?, structure_source=?
                WHERE accession=?""",
                (r["ranking"], int(r["is_secured"]), r["guarantees"], r.get("guarantor_note"),
                 int(r["change_of_control"]), r.get("change_of_control_price"),
                 int(r["coupon_step"]), r.get("coupon_step_note"), r.get("quote"), source, accession))
            conn.commit()
            filled += 1
            print(f"  [{source}] {r['ranking']}, guarantees: {r['guarantees']}, "
                  f"change of control: {'yes' if r['change_of_control'] else 'no'}, "
                  f"coupon step: {'yes' if r['coupon_step'] else 'no'}\n")
        except Exception as e:
            if "credit balance" in str(e):
                print("  STOPPED: the API says your credit balance is too low.\n")
                break
            missed += 1
            print(f"  FAILED: {e}\n")

    print(f"Done. {filled} filled in, {missed} missed.")


if __name__ == "__main__":
    main()
