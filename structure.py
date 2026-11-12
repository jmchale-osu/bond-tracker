"""
Read each deal's prospectus for the structural terms Bill asked about:
ranking, security, guarantees, change of control protection, coupon steps.

    python structure.py --limit 5    try a few first
    python structure.py              everything missing
    python structure.py --redo       re-read every deal (use after changing rules.py)
    python structure.py --check      compare with what is stored, change nothing

Rule-based (rules.py), so it costs nothing.
"""
import re
import sys
from pathlib import Path
from datetime import date, timedelta

from edgar import set_identity, Company

import db
import rules
from parse_fwp import get_html, rows_of

set_identity(db.SEC_IDENTITY)

# The parts of a prospectus where these terms live
SECTIONS = [
    re.compile(r"\branking\b", re.I),
    re.compile(r"\bguarantee", re.I),
    re.compile(r"change of control", re.I),
    re.compile(r"interest rate adjustment|coupon step|rating event|step[- ]up", re.I),
]

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
    fallback = near = None
    for f in candidates(cik, filing_date, window):
        text = filing_text(f)
        if len(text) < 2000:
            continue
        flat = text.upper()
        if any(c in flat for c in cusips):
            return text, "cusip"
        if fallback is None and coupons and any(c in text for c in coupons):
            fallback = text
        if near is None and abs((f.filing_date - filing_date).days) <= 2 and re.search(r"preliminary prospectus supplement|subject to completion", text[:6000], re.I):
            near = text           # the preliminary prospectus for this deal: no coupon yet, same structure
    if fallback:
        return fallback, "coupon"
    return (near, "preliminary") if near else (None, None)


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


def read(conn, accession, issuer, filing_date, url):
    """The structure terms of one deal, from its term sheet and (when found) its prospectus."""
    cik = url.split("/data/")[1].split("/")[0] if url and "/data/" in url else None
    sheet = " ".join(" ".join(r) for r in rows_of(get_html(accession)))
    prospectus, matched = find_prospectus(conn, accession, cik, date.fromisoformat(filing_date))
    extra = excerpts(prospectus) if prospectus else ""
    both = sheet + " " + extra
    titles = [t for (t,) in conn.execute("SELECT title FROM tranches WHERE accession = ?", (accession,))]
    rank = rules.ranking(titles, sheet, extra)
    coc, coc_price = rules.change_of_control(both)
    step, step_note = rules.coupon_step(both)
    if step and re.search(r"change of control|repurchase", step_note or "", re.I):
        step, step_note = False, None
    source = "fwp" + (f"+424b:{matched}" if extra else "")
    return {"ranking": rank, "is_secured": int(rank in ("senior_secured", "first_mortgage")),
            "guarantees": rules.guarantees(issuer, both), "guarantor_note": None,
            "change_of_control": int(coc), "change_of_control_price": coc_price,
            "coupon_step": int(step), "coupon_step_note": step_note,
            "quote": None, "source": source + "+rules"}


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    redo, check = "--redo" in sys.argv, "--check" in sys.argv
    conn = db.connect()
    where = "" if redo or check else "WHERE ranking IS NULL"
    rows = conn.execute(f"""
        SELECT accession, issuer, filing_date, url, ranking, guarantees, change_of_control, coupon_step
        FROM deals {where} ORDER BY filing_date DESC
    """).fetchall()
    if check:
        rows = [r for r in rows if r[4] is not None]
    if limit:
        rows = rows[:limit]
    print(f"{len(rows)} deals to read\n")

    agree = {k: [0, 0] for k in ("ranking", "guarantees", "change_of_control", "coupon_step")}
    for i, (accession, issuer, filing_date, url, *stored) in enumerate(rows, 1):
        try:
            r = read(conn, accession, issuer, filing_date, url)
        except Exception as e:
            print(f"[{i}/{len(rows)}] {(issuer or '')[:42]}  FAILED: {e}")
            continue
        if check:
            for k, old in zip(agree, stored):
                if old is None or (k == "guarantees" and old == "not_stated"):
                    continue
                agree[k][1] += 1
                agree[k][0] += r[k] == old
                if r[k] != old:
                    print(f"  {k:17} {(issuer or '')[:34]:34} stored {old}, rules {r[k]}")
            continue
        conn.execute("""
            UPDATE deals SET ranking=?, is_secured=?, guarantees=?, guarantor_note=?,
                   change_of_control=?, change_of_control_price=?, coupon_step=?,
                   coupon_step_note=?, structure_quote=?, structure_source=?
            WHERE accession=?""",
            (r["ranking"], r["is_secured"], r["guarantees"], r["guarantor_note"], r["change_of_control"],
             r["change_of_control_price"], r["coupon_step"], r["coupon_step_note"], r["quote"],
             r["source"], accession))
        conn.commit()
        print(f"[{i}/{len(rows)}] {(issuer or '')[:42]:42} {r['ranking']}, change of control "
              f"{'yes' if r['change_of_control'] else 'no'}, coupon step {'yes' if r['coupon_step'] else 'no'}")
    if check:
        for k, (a, n) in agree.items():
            print(f"  {k:18} {a:3}/{n:<3} {100 * a / max(n, 1):5.1f}%")


if __name__ == "__main__":
    main()
