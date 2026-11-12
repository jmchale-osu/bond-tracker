"""
Read a bond pricing term sheet (FWP) without an AI model. Free, and it gives the same answer every time.

    python parse_fwp.py 0001193125-26-392006     print one filing's terms
    python parse_fwp.py --check                   score against the bonds Claude extracted earlier

Term sheets are tables of "label: value" rows. Some put each tranche in its own block (one value
per row, the block repeating); others put tranches side by side (several values per row, often
split across two tables when the page runs out of width). Both reduce to one rule: every value
found for a field goes to the next tranche that does not have that field yet.
"""
import collections
import json
import re
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
HTML_DIR = HERE / "data" / "html"

MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
         r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
DATE = re.compile(rf"({MONTH})\s+(\d{{1,2}}),?\s+(\d{{4}})", re.I)
DATE_DMY = re.compile(rf"(?<!\d)(\d{{1,2}})\s+({MONTH}),?\s+(\d{{4}})", re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONEY = re.compile(r"(?:(?:U\.?S\.?)?\$|€|£|USD|EUR|GBP)\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(million|billion|mm|bn)?", re.I)
PCT = re.compile(r"(\d{1,3}\.\d+)\s?%")
PRICE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s?%")
BPS = re.compile(r"(?:\+\s*|T\s*\+\s*|plus\s+)?(\d{1,4}(?:\.\d+)?)\s*(?:bps|bp|basis points?)\b"
                 r"|(?:T|UST|Treasury|Treasuries)\s*\+\s*(\d{1,4}(?:\.\d+)?)|(?<![\d.])\+\s*(\d{1,4}(?:\.\d+)?)(?![\d.%])", re.I)
CUSIP = re.compile(r"(?<![0-9A-Z])([0-9]{3}[0-9A-Z]{3}\s?[0-9A-Z]{2}\s?[0-9])(?![0-9A-Z])")
MOODYS = re.compile(r"(?<![\w])(Aaa|Aa[123]|A[123]|Baa[123]|Ba[123]|B[123]|Caa[123])(?![\w])")
SP = re.compile(r"(?<![\w+-])(AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC[+-]?)(?![\w+-])")
TITLE = re.compile(r"(\d{1,2}\.\d{2,4})\s?%\s+((?:(?:[A-Z][\w-]*|/)\s+){0,8}?(?:Notes|Bonds|Debentures))\s+due\s+(20\d\d)", re.I)
BOOK = re.compile(r"([A-Z][\w.&,' -]{2,60}?(?:LLC|L\.L\.C\.|Inc\.|Incorporated|Corp(?:oration|\.)?|plc|Limited|Ltd\.?|& Co\.(?: LLC)?|AG|S\.A\.))")

# (field, label pattern, label must not match). First match wins, so order matters.
FIELDS = [
    ("cusip", r"cusip", None),
    ("ratings", r"rating", r"change of control|downgrade|adjustment"),
    ("benchmark_yield_pct", r"benchmark.*yield|treasury.*(price|yield)|reference.*yield|ust spot|treasury spot", None),
    ("benchmark_treasury", r"benchmark|reference treasury|treasury benchmark", r"spread|yield|price"),
    ("spread_bps", r"spread", r"make|redemption|call|swap|fee"),
    ("make_whole_bps", r"make[- ]?whole|redemption", r"par|special|mandatory|change|tax|repurchase"),
    ("par_call_date", r"par call", None),
    ("yield_pct", r"yield", r"benchmark|treasury|payment|all-in|swap|reference|government"),
    ("price_pct_of_par", r"price", r"benchmark|treasury|redemption|repurchase|call|all-in|net|reference|government|to (the )?(issuer|company)|underwrit"),
    ("coupon_pct", r"coupon|interest rate|^rate|^interest$", r"payment|day count|reset|benchmark|record|adjustment|step|determination|floating rate period|base"),
    ("maturity_date", r"maturity", r"yield|index"),
    ("principal_usd", r"principal amount|^amount|size|aggregate|face amount", r"denomination|minimum|proceeds|outstanding"),
    ("trade_date", r"trade date|pricing date", None),
    ("settlement_date", r"settlement", None),
    ("ranking", r"ranking|security type|^status|^type of security|seniority", None),
    ("change_of_control", r"change of control", None),
    ("use_of_proceeds", r"use of proceeds", None),
    ("bookrunners", r"book[- ]?running|bookrunner|joint lead", None),
    ("issuer", r"^issuer$|^issuer:|^company", r"rating"),
]
TRANCHE = {"cusip", "benchmark_yield_pct", "benchmark_treasury", "spread_bps", "make_whole_bps",
           "par_call_date", "yield_pct", "price_pct_of_par", "coupon_pct", "maturity_date", "principal_usd"}
CORE = ("principal_usd", "coupon_pct", "maturity_date", "yield_pct", "price_pct_of_par", "spread_bps")


class Rows(HTMLParser):
    """Table rows as lists of cell texts, and other blocks as one-cell rows. A row whose first
    cell is blank is flagged, since it often continues the row above."""
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "table"}

    def __init__(self):
        super().__init__()
        self.rows, self.cells, self.buf, self.in_row = [], [], [], 0

    def flush_cell(self):
        text = re.sub(r"\s+", " ", unescape("".join(self.buf))).replace("\u200b", "").strip()
        self.buf = []
        return text

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_row, self.cells = 1, []
        elif tag in ("td", "th"):
            self.buf = []
        elif tag in self.BLOCK and not self.in_row:
            self.end_block()

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_row:
            self.cells.append(self.flush_cell())
        elif tag == "tr":
            cells = [c for c in self.cells if c]
            if cells:
                self.rows.append((not self.cells[0], cells))
            self.in_row, self.cells = 0, []
        elif tag in self.BLOCK and not self.in_row:
            self.end_block()

    def end_block(self):
        text = self.flush_cell()
        if text:
            self.rows.append((False, [text]))

    def handle_data(self, data):
        self.buf.append(data)


SERIES_TAG = re.compile(r"^(?:20\d\d|Floating|Fixed|\d{1,2}\.\d+\s?%)[^:]{0,60}:")


def rows_of(html):
    p = Rows()
    p.feed(html)
    p.end_block()
    out = []
    for blank_first, cells in p.rows:
        merged = []
        for c in cells:                                   # "4.500" | "%" split across cells
            if merged and re.fullmatch(r"[%)\s]+", c):
                merged[-1] += c
            else:
                merged.append(c)
        cells = merged
        if len(cells) == 1 and ":" in cells[0][:70] and not SERIES_TAG.match(cells[0]):
            label, value = cells[0].split(":", 1)         # "Label: value" written as a paragraph
            cells = [label, value]
        # "2031 Notes: $500,000,000" on its own row, under a row labelled "Principal Amount"
        if out and len(out[-1]) > 1 and classify(cells[0]) is None and re.search(r"\d", cells[0]) and (
                SERIES_TAG.match(cells[0]) or blank_first):
            out[-1] = out[-1] + cells
            continue
        out.append(cells)
    return out


def iso_parts(year, month, day):
    return f"{int(year):04d}-{MONTHS[month[:3].lower()]:02d}-{int(day):02d}"


def dates(text):
    found = [(m.start(), iso_parts(m.group(3), m.group(1), m.group(2))) for m in DATE.finditer(text)]
    found += [(m.start(), iso_parts(m.group(3), m.group(2), m.group(1))) for m in DATE_DMY.finditer(text)]
    return [d for _, d in sorted(found)]


def iso(m):
    return iso_parts(m.group(3), m.group(1), m.group(2))


def money(m):
    v = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    return v * (1e9 if unit in ("billion", "bn") else 1e6 if unit in ("million", "mm") else 1)


NONE = re.compile(r"\s*(none|n/a|na|not applicable|-|—|–)\.?\s*", re.I)
FLOAT = re.compile(r"SOFR|floating|compounded|EURIBOR|SONIA", re.I)


def values(field, text):
    """Every value of this field in one cell, in order."""
    if field == "principal_usd":
        return [v for v in (money(m) for m in MONEY.finditer(text)) if v >= 1e7]
    if field == "currency":
        codes = []
        for m in MONEY.finditer(text):
            if money(m) >= 1e7:
                sign = m.group(0)[:3].upper()
                codes.append("EUR" if "€" in sign or sign == "EUR" else "GBP" if "£" in sign or sign == "GBP" else "USD")
        return codes
    if field in ("coupon_pct", "yield_pct", "price_pct_of_par", "benchmark_yield_pct"):
        found = [float(x) for x in (PRICE if field == "price_pct_of_par" else PCT).findall(text)]
        if field == "price_pct_of_par":
            found = [v for v in found if 50 <= v <= 130]
        if field == "benchmark_yield_pct":
            found = [v for v in found if v < 20]          # "95.060% / 2.910%" is price, then yield
        if field == "coupon_pct" and FLOAT.search(text):
            # a floater ("Compounded SOFR + 0.84%"), or the fixed leg of a fixed-to-floating note
            first = PCT.search(text)
            return [None] if not first or re.search(r"(\+|plus)\s*$", text[:first.start()], re.I) else found[:1]
        return found
    if field in ("maturity_date", "trade_date", "settlement_date"):
        return dates(text)
    if field == "par_call_date":
        return [None] if NONE.fullmatch(text) else dates(text)
    if field in ("spread_bps", "make_whole_bps"):
        if NONE.fullmatch(text):
            return [None]
        found = [float(next(g for g in m.groups() if g)) for m in BPS.finditer(text)
                 if not re.search(r"adjustment of\s*$", text[:m.start()], re.I)]
        if not found and field == "spread_bps":     # "Plus 0.847%", "0.600%"
            found = [round(float(x) * 100, 2) for x in re.findall(r"(\d\.\d+)\s?%", text) if float(x) < 6]
        return found
    if field == "float_margin":                 # "Compounded SOFR + 0.84%" or "+ 84 bps"
        m = re.search(r"(?:SOFR|EURIBOR|SONIA|Rate)[^|%]{0,40}?(?:\+|plus)\s*(\d{1,3}(?:\.\d+)?)\s*(%|bps|bp|basis points?)", text, re.I)
        return [] if not m else [round(float(m.group(1)) * (100 if m.group(2) == "%" else 1), 2)]
    if field == "cusip":
        return [c.replace(" ", "") for c in CUSIP.findall(text)]
    if field == "benchmark_treasury":
        found = re.findall(rf"\d{{1,2}}(?:\.\d+)?%[^|]*?(?:due|maturing)\s+(?:{MONTH}\s+\d{{1,2}},?\s+)?\d{{4}}", text, re.I)
        return [re.sub(r"\s+", " ", f).strip() for f in found]
    return [text]


def row_values(field, cells):
    """Values across a row's cells. A cell with words but no value (N/A, SOFR) holds a tranche's
    place when its neighbours have values, so the columns stay lined up."""
    per = []
    for c in cells:
        # "2029 Notes: 4.850% ... Floating Rate Notes: SOFR + 0.60%" in one cell: one piece per series
        pieces = re.split(r"(?=\b(?:20\d\d|Floating Rate|Fixed Rate)[^:|\d]{0,40}Notes?:)", c)
        if len(pieces) > 2:
            found = []
            for piece in pieces:
                v = values(field, piece)
                found += v if v else ([None] if SERIES_TAG.match(piece.strip()) else [])
            per.append(found if any(x is not None for x in found) else [])
        else:
            per.append(values(field, c))
    if len(cells) > 1 and any(per):
        per = [v if v else ([None] if re.search(r"[A-Za-z—–-]", c) else []) for v, c in zip(per, cells)]
    return [v for vs in per for v in vs]


def par_calls(text):
    """Par call dates in redemption prose, in tranche order: "prior to <date> (the Par Call
    Date)", "par call on or after <date>", "on or after <date>, ... 100% of the principal"."""
    found = []
    for m in DATE.finditer(text):
        before, after = text[max(0, m.start() - 45):m.start()].lower(), text[m.end():m.end() + 320].lower()
        if ("prior to" in before[-15:] and "par call date" in after[:300]) or (
                "on or after" in before[-15:] and ("par call" in (before + after[:60]) or
                                             re.search(r"^[^.;]{0,100}100%", after) and "greater of" not in after[:100])):
            d = iso(m)
            if not found or found[-1] != d:
                found.append(d)
    return found


def classify(label):
    label = label.lower().strip(" :*†‡")
    if len(label) > 90:
        return None
    for field, want, avoid in FIELDS:
        if re.search(want, label) and not (avoid and re.search(avoid, label)):
            return field
    return None


def ratings(text):
    t = text.replace("’", "'")
    out = {"rating_moodys": None, "rating_sp": None, "rating_fitch": None}
    m = MOODYS.search(t)
    if m:
        out["rating_moodys"] = m.group(1)
    rest = MOODYS.sub(" ", t)
    letters = SP.findall(rest)
    has_sp = re.search(r"S\s*&\s*P|Standard", t, re.I)
    has_fitch = re.search(r"Fitch", t, re.I)
    if letters:
        if has_fitch and not has_sp:
            out["rating_fitch"] = letters[0]
        else:
            out["rating_sp"] = letters[0]
            if has_fitch and len(letters) > 1:
                out["rating_fitch"] = letters[1]
    return out


def parse(html):
    rows = [r for r in rows_of(html) if len(r) > 1]
    tranches, deal, labels = [], {}, {}
    filled, state = {}, {"opener": None, "epoch": 0, "start": 0}
    seen = {}

    def put(field, found):
        """A term sheet is a run of blocks that each open with the same field (side-by-side
        tables open once per table; one-block-per-tranche sheets once per tranche). The opening
        row's values go to the next tranches; other rows fill the tranches that block opened.
        A field repeated inside a block keeps its first value (Treasury spread before swap spread)."""
        if not found or all(v is None for v in found) and seen.get(field) == state["epoch"]:
            return
        if state["opener"] is None:
            state["opener"] = field
        if field == state["opener"]:
            start = filled.get(field, 0)
            state["epoch"] += 1
            state["start"] = start
        elif seen.get(field) == state["epoch"]:
            return
        else:
            start = state["start"]
        seen[field] = state["epoch"]
        for k, v in enumerate(found):
            while len(tranches) <= start + k:
                tranches.append({})
            tranches[start + k][field] = v
        filled[field] = max(filled.get(field, 0), start + len(found))

    def table(header, after):
        """A grid with a header row ("Series | Par Call Date | Make-Whole Spread") and a row per
        tranche. Fills only what the term rows above left empty."""
        cols = []
        for c in header[1:]:
            if classify(c) not in TRANCHE:
                break
            cols.append(classify(c))
        width = len(cols) + 1
        data = header[width:]
        for r in after:
            if len(r) != width or classify(r[0]):
                break
            data += r
        for t, start in enumerate(range(0, len(data) - width + 1, width)):
            chunk = data[start:start + width]
            for field, cell in zip(cols, chunk[1:]):
                v = values(field, cell)
                while len(tranches) <= t:
                    tranches.append({})
                if v and tranches[t].get(field) is None:
                    tranches[t][field] = v[0]

    labelled = [(classify(r[0]), r) for r in rows]
    # A deal total listed ahead of the tranche sizes ("Aggregate Principal Amount: $3,750,000,000")
    sizes = [(i, row_values("principal_usd", r[1:])) for i, (f, r) in enumerate(labelled) if f == "principal_usd"]
    flat = [v for _, vs in sizes for v in vs if v]
    skip = {sizes[0][0]} if len(sizes) > 1 and len(sizes[0][1]) == 1 and len(flat) > 2 and \
        abs(flat[0] - sum(flat[1:])) < 1 else set()

    for i, (field, cells) in enumerate(labelled):
        if not field and len(cells) >= 3 and classify(cells[1]) in TRANCHE:
            table(cells, [r for _, r in labelled[i + 1:]])
            continue
        if not field or i in skip:
            continue
        if field in TRANCHE:
            found = row_values(field, cells[1:])
            text = " ".join(cells[1:])
            if field == "make_whole_bps":
                put("par_call_date", par_calls(text))
                if re.search(r"(?:\+|plus)\s*\d|basis point|bps", text, re.I):
                    found = [float(x) for x in re.findall(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*(?:bps|bp|basis points?)", text, re.I)]
            put(field, found)
            if field == "principal_usd" and found:
                put("currency", row_values("currency", cells[1:]))
            if field == "coupon_pct":
                margin = row_values("float_margin", cells[1:])
                if any(m is not None for m in margin):
                    put("float_margin", margin)
        elif field not in deal or field == "ratings" and re.search(r"issuer", labels.get(field, ""), re.I) \
                and re.search(r"securit|issue\b|notes", cells[0], re.I):
            deal[field] = " | ".join(cells[1:])         # a security rating beats the issuer rating
            labels[field] = cells[0]

    n = max([filled.get(f, 0) for f in CORE] + [0])
    # a tranche needs a maturity and one price term; stray values (fee tables, footnotes) have neither
    tranches = [t for t in tranches[:n] if t.get("maturity_date") and any(
        t.get(f) is not None for f in ("principal_usd", "coupon_pct", "yield_pct", "spread_bps"))]
    page = re.sub(r"\s+", " ", " ".join(" ".join(r) for r in rows_of(html)))
    titles = {}
    for coupon, kind, year in TITLE.findall(page):
        titles.setdefault((round(float(coupon), 4), year), f"{float(coupon):.3f}% {kind.strip()} due {year}")
    floaters = re.findall(r"Floating Rate (?:Senior )?Notes due (20\d\d)", page, re.I)

    by_year = collections.defaultdict(set)
    for coupon, year in titles:
        by_year[year].add(coupon)
    sizes = {}       # "US$800,000,000 principal amount of 5.100% Notes due 2028"
    for amount, coupon in re.findall(r"\$\s?([\d,]{9,})\s+(?:aggregate\s+)?principal amount of\s+(?:its\s+|our\s+|the\s+)?(\d{1,2}\.\d+)\s?%", page, re.I):
        sizes.setdefault(round(float(coupon), 4), float(amount.replace(",", "")))
    rate = ratings(deal.get("ratings", ""))
    for t in tranches:
        if not t.get("coupon_pct"):
            t["coupon_pct"] = None
            year = (t.get("maturity_date") or "")[:4]
            if len(by_year[year]) == 1 and year not in floaters:      # coupon only in the title
                t["coupon_pct"] = next(iter(by_year[year]))
        year = (t.get("maturity_date") or "")[:4]
        t["title"] = titles.get((round(t["coupon_pct"], 4), year)) if t.get("coupon_pct") is not None else None
        t["is_floating_rate"] = t.get("coupon_pct") is None and (year in floaters or not t.get("yield_pct"))
        if not t["title"]:
            t["title"] = (f"Floating Rate Notes due {year}" if t["is_floating_rate"]
                          else f"{t.get('coupon_pct') or ''}% Notes due {year}".strip())
        total = sum(x.get("principal_usd") or 0 for x in tranches)
        if t.get("coupon_pct") is not None and sizes.get(round(t["coupon_pct"], 4)) and (
                not t.get("principal_usd") or len(tranches) > 1 and t["principal_usd"] > total / 2):
            t["principal_usd"] = sizes[round(t["coupon_pct"], 4)]
        margin = t.pop("float_margin", None)
        if t["is_floating_rate"]:
            if t.get("spread_bps") is None:
                t["spread_bps"] = margin
            t["yield_pct"] = t["benchmark_yield_pct"] = None   # its spread is to SOFR, not Treasuries
        t.update(rate)
    trade = dates(deal.get("trade_date", ""))
    settle = dates(deal.get("settlement_date", ""))
    issuer = re.split(r"\s+\(|,\s+an?\s|\s+\|", deal.get("issuer", ""))[0].strip(" .,") or None
    books = []
    for name in BOOK.findall(deal.get("bookrunners", "")):
        name = name.strip(" ,")
        if name not in books:
            books.append(name)
    return {
        "issuer": issuer,
        "trade_date": trade[0] if trade else None,
        "settlement_date": settle[0] if settle else None,
        "bookrunners": books[:12],
        "ranking_text": deal.get("ranking"),
        "change_of_control_text": deal.get("change_of_control"),
        "use_of_proceeds_quote": (deal.get("use_of_proceeds") or "")[:400] or None,
        "tranches": tranches,
    }


def get_html(accession, url=None):
    """The filing's main document, cached in data/html/. With the document's URL (from full-text
    search) it is one request; without, edgartools finds the filing first."""
    path = HTML_DIR / f"{accession}.html"
    if path.exists():
        return path.read_text(errors="replace")
    import db
    if url:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": db.SEC_IDENTITY})
        with urllib.request.urlopen(req, timeout=60) as r:
            html = r.read().decode("utf-8", "replace")
    else:
        from edgar import find, set_identity
        set_identity(db.SEC_IDENTITY)
        html = find(accession).html() or ""
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(html)
    return html


def check():
    """Field-by-field agreement with the tranches Claude extracted, matched on coupon and maturity."""
    import db
    conn = db.connect()
    fields = ["principal_usd", "coupon_pct", "maturity_date", "spread_bps", "yield_pct", "price_pct_of_par",
              "benchmark_yield_pct", "make_whole_bps", "par_call_date", "rating_moodys", "rating_sp"]
    right = {f: 0 for f in fields}
    total = {f: 0 for f in fields}
    found = expected = 0
    misses = []
    for (acc,) in conn.execute("SELECT accession FROM deals ORDER BY accession"):
        gold = conn.execute(f"SELECT title, {', '.join(fields)} FROM tranches WHERE accession = ?", (acc,)).fetchall()
        got = parse(get_html(acc))["tranches"]
        expected += len(gold)
        for g in gold:
            g = dict(zip(["title"] + fields, g))
            same = [t for t in got if t.get("maturity_date") == g["maturity_date"]]
            match = next((t for t in same if t.get("coupon_pct") == g["coupon_pct"]), None)
            if not match:
                misses.append((acc, g["title"]))
                continue
            found += 1
            for f in fields:
                if g[f] is None:
                    continue
                total[f] += 1
                v = match.get(f)
                ok = v == g[f] or (isinstance(v, float) and isinstance(g[f], (int, float)) and abs(v - g[f]) < 1e-6)
                right[f] += ok
                if not ok and len(misses) < 400:
                    misses.append((acc, f, g[f], v))
    print(f"Tranches found: {found}/{expected}")
    for f in fields:
        print(f"  {f:20} {right[f]:4}/{total[f]:<4} {100 * right[f] / max(total[f], 1):5.1f}%")
    return misses


def fill_cusips():
    """Add CUSIPs (and fix the floater flag) on bonds already stored, matched on coupon and maturity."""
    import db
    conn = db.connect()
    added = 0
    for (acc,) in conn.execute("SELECT DISTINCT accession FROM tranches").fetchall():
        got = parse(get_html(acc))["tranches"]
        for key, coupon, maturity in conn.execute(
                "SELECT bond_key, coupon_pct, maturity_date FROM tranches WHERE accession = ? AND cusip IS NULL", (acc,)).fetchall():
            match = [t for t in got if t.get("maturity_date") == maturity and t.get("coupon_pct") == coupon and t.get("cusip")]
            if len(match) == 1:
                conn.execute("UPDATE tranches SET cusip = ? WHERE bond_key = ?", (match[0]["cusip"], key))
                added += 1
        for key, coupon, maturity in conn.execute(
                "SELECT bond_key, coupon_pct, maturity_date FROM tranches WHERE accession = ? AND currency IS NULL", (acc,)).fetchall():
            match = [t for t in got if t.get("maturity_date") == maturity and t.get("coupon_pct") == coupon]
            currency = {t.get("currency") for t in match} if match else {t.get("currency") for t in got}
            if len(currency) == 1 and None not in currency:
                conn.execute("UPDATE tranches SET currency = ? WHERE bond_key = ?", (currency.pop(), key))
    conn.commit()
    total, have = conn.execute("SELECT COUNT(*), COUNT(cusip) FROM tranches").fetchone()
    print(f"Added {added} CUSIPs; {have} of {total} bonds have one")


if __name__ == "__main__":
    if "--fill-cusips" in sys.argv:
        fill_cusips()
    elif "--check" in sys.argv:
        for m in check()[:60]:
            print("  ", m)
    else:
        print(json.dumps(parse(get_html(sys.argv[1])), indent=2))
