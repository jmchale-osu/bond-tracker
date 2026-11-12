"""
Rule-based reading of the terms that used to need an AI model: use of proceeds, ranking,
security, guarantees, change of control put and coupon step. Free and repeatable.

    python rules.py --check     compare with the labels Claude gave the current deals

Each rule looks for the phrases term sheets and prospectus supplements use for these terms.
"""
import re
import sys

# ---------------------------------------------------------------- use of proceeds

NAMED_DEAL = re.compile(
    r"\b(?:pending|proposed|previously announced|contemplated)\s+(?:acquisition|merger|purchase)\s+(?:of|by|with)\s+[A-Z]"
    r"|\b(?:fund|financ|pay)\w*\s+(?:all or )?(?:a portion of |part of )?the\s+(?:cash\s+)?(?:consideration|purchase price)\b"
    r"|\bthe\s+(?:[A-Z][\w&.'-]*\s+){1,5}(?:Acquisition|Merger|Transactions?)\b"
    r"|\bthe\s+(?:Acquisition|Merger)\b"
    r"|special mandatory redemption",
    re.M)
NAMED_DEBT = re.compile(
    r"(?:repay|redeem|refinanc|repurchase|retire|prepay|purchase|tender|discharge)\w*[^.]{0,200}?"
    r"(?:\d\.\d+\s?%[^.]{0,40}(?:notes|debentures)|notes due 20\d\d|term loan|tender offer|"
    r"outstanding (?:borrowings|amounts|indebtedness) under|commercial paper|revolving credit)",
    re.I)
GENERAL = re.compile(r"general corporate purposes", re.I)
MAY_INCLUDE = re.compile(r"(?:which|that) may include|including,? (?:without limitation|but not limited to)|such as", re.I)


def proceeds(text):
    """('acquisition' | 'refinancing' | 'mixed' | 'general_corporate' | 'not_stated', quote)."""
    if not text or len(text.strip()) < 20:
        return "not_stated", None
    flat = " ".join(text.split())[:1500]
    deal = NAMED_DEAL.search(flat)
    debt = NAMED_DEBT.search(flat)
    # repayment listed only as an example of general corporate purposes does not count
    if debt and GENERAL.search(flat) and MAY_INCLUDE.search(flat[:debt.start()]) and not re.search(
            r"\d\.\d+\s?%|due 20\d\d|tender offer", flat[debt.start():debt.end()], re.I):
        debt = None
    if deal and debt:
        category, hit = "mixed", deal
    elif deal:
        category, hit = "acquisition", deal
    elif debt:
        category, hit = ("mixed" if GENERAL.search(flat) and GENERAL.search(flat).start() < debt.start() else "refinancing"), debt
    elif GENERAL.search(flat):
        category, hit = "general_corporate", GENERAL.search(flat)
    else:
        return "not_stated", flat[:200]
    start = flat.rfind(". ", 0, hit.start()) + 2 if flat.rfind(". ", 0, hit.start()) >= 0 else 0
    return category, flat[start:start + 200]


def proceeds_section(text):
    """The deal-specific Use of Proceeds section of a prospectus, not the base boilerplate."""
    best, best_score = None, -1
    for hit in re.finditer(r"USE\s+OF\s+PROCEEDS", text, re.I):
        chunk = text[hit.start():hit.start() + 1500]
        score = (3 * bool(NAMED_DEAL.search(chunk)) + 3 * bool(NAMED_DEBT.search(chunk))
                 + 2 * bool(re.search(r"\$\s?[\d,]{7,}|approximately \$", chunk)) + bool(re.search(r"net proceeds", chunk, re.I)))
        if score > best_score:
            best, best_score = chunk, score
    return best


# ---------------------------------------------------------------- structure

def ranking(titles, term_sheet, prospectus=""):
    """Ranking from the notes' names first, then the term sheet, then the prospectus."""
    names = " ".join(t.lower() for t in titles if t)
    for word, rank in (("junior subordinated", "junior_subordinated"), ("first mortgage", "first_mortgage"),
                       ("subordinated", "subordinated"), ("senior secured", "senior_secured"),
                       ("secured", "senior_secured")):
        if word in names:
            return rank
    for text in (term_sheet, prospectus):
        flat = " ".join((text or "").split()).lower()
        if re.search(r"junior subordinated (?:notes|debentures|obligations)", flat):
            return "junior_subordinated"
        if re.search(r"first mortgage bonds", flat):
            return "first_mortgage"
        if re.search(r"(?:notes|they) will be (?:our |the issuer's )?(?:unsecured )?subordinated obligations|"
                     r"subordinated (?:and junior )?in right of payment to (?:all of )?(?:our|its|the issuer's) (?:existing and future )?senior", flat):
            return "subordinated"
        if re.search(r"senior secured (?:notes|obligations)|(?:notes|they) will be secured by", flat):
            return "senior_secured"
        if re.search(r"senior unsecured|unsecured and unsubordinated|unsubordinated and unsecured|"
                     r"senior (?:notes|debt securities)\b[^.]{0,80}rank (?:equally|pari passu)|"
                     r"rank equally (?:in right of payment )?with all (?:of )?(?:our|its) (?:other )?(?:existing and future )?(?:senior )?unsecured", flat):
            return "senior_unsecured"
    if re.search(r"\bsenior\b", names) or re.search(r"\bnotes\b", names):
        return "senior_unsecured"     # plain "Notes due 2031" of an investment grade issuer
    return "not_stated"


def guarantees(issuer, text):
    flat = " ".join((text or "").split())
    finance_co = re.search(r"\b(finance|financing|funding|capital|holdings?|operating|L\.?P\.?)\b", issuer or "", re.I)
    listed = re.search(r"\b(Parent )?Guarantors?\)?\s*:?\s+(?!will|shall|may|of|under|and|to)[A-Z]", flat)
    parent = re.search(r"guaranteed[^.]{0,80}?\bby\s+(?:its |our |the )?(?:parent|[A-Z][\w&.,' -]{2,60}?"
                       r"(?:Inc\.|Corporation|plc|Company|Ltd\.?|N\.V\.|S\.A\.|SA|AG|Holdings|Trust))", flat)
    subs = re.search(r"subsidiary guarant|guaranteed[^.]{0,80}by (?:each of )?(?:certain of )?(?:our|its|the issuer's) "
                     r"(?:wholly[- ]owned )?(?:domestic )?subsidiar", flat, re.I)
    if subs and (parent or listed and finance_co):
        return "both"
    if subs:
        return "subsidiaries"
    if parent or listed:
        named = (parent or listed).group(0).lower()
        return "parent" if finance_co or "parent" in named else "subsidiaries"
    if re.search(r"will not be guaranteed|are not guaranteed|solely (?:the )?obligations? of", flat, re.I):
        return "none"
    return "none" if text else "not_stated"


def change_of_control(text):
    """(holders can make the issuer buy back the notes on a change of control, price)."""
    flat = " ".join((text or "").split())
    hit = re.search(r"change of control (?:repurchase|triggering|offer|put)[\s\S]{0,900}?(10[01](?:\.\d+)?)\s?%", flat, re.I) or \
        re.search(r"change of control[^.]{0,400}?(10[01](?:\.\d+)?)\s?%", flat, re.I) or \
        re.search(r"(10[01](?:\.\d+)?)\s?%[^.]{0,300}?change of control", flat, re.I)
    if hit:
        return True, float(hit.group(1))
    return False, None


def coupon_step(text):
    """(coupon rises on a downgrade or a missed sustainability target, note)."""
    flat = " ".join((text or "").split())
    hit = re.search(r"interest rate adjustment|interest rate (?:payable )?(?:on (?:each series of )?(?:the )?notes )?will be subject to adjustment"
                    r"|(?:coupon|interest rate) step[- ]?up|step[- ]?up (?:date|margin|event)|sustainability performance target", flat, re.I)
    if not hit:
        return False, None
    return True, flat[hit.start():hit.start() + 120]


# ---------------------------------------------------------------- check against Claude's labels

def check():
    import db
    from parse_fwp import get_html, rows_of
    conn = db.connect()
    rows = conn.execute("""SELECT accession, issuer, use_of_proceeds, proceeds_source, ranking, guarantees,
                                  change_of_control, coupon_step FROM deals
                           WHERE accession IN (SELECT accession FROM tranches)""").fetchall()
    agree = {k: [0, 0] for k in ("proceeds", "ranking", "guarantees", "change_of_control", "coupon_step")}
    misses = []
    for acc, issuer, uop, src, rank, guar, coc, step in rows:
        page = " ".join(" ".join(r) for r in rows_of(get_html(acc)))
        titles = [t for (t,) in conn.execute("SELECT title FROM tranches WHERE accession = ?", (acc,))]
        quote = re.search(r"use of proceeds:?\s*(.{0,1200})", page, re.I)
        got = {
            "proceeds": proceeds(quote.group(1) if quote else "")[0] if src == "fwp" else None,
            "ranking": ranking(titles, page),
            "guarantees": guarantees(issuer, page),
            "change_of_control": int(change_of_control(page)[0]),
            "coupon_step": int(coupon_step(page)[0]),
        }
        want = {"proceeds": uop, "ranking": rank, "guarantees": guar, "change_of_control": coc, "coupon_step": step}
        for k in agree:
            if got[k] is None or want[k] is None or (k == "guarantees" and want[k] == "not_stated"):
                continue
            agree[k][1] += 1
            agree[k][0] += got[k] == want[k]
            if got[k] != want[k]:
                misses.append((k, acc, (issuer or "")[:30], want[k], got[k]))
    for k, (a, n) in agree.items():
        print(f"  {k:18} {a:3}/{n:<3} {100 * a / max(n, 1):5.1f}%")
    return misses


if __name__ == "__main__":
    if "--check" in sys.argv:
        for m in check():
            print("  ", m)
