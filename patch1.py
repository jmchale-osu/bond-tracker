from pathlib import Path

def patch(name, pairs):
    p = Path(name); s = p.read_text(); ok = True
    for old, new in pairs:
        if old not in s:
            print(f"  FAIL in {name}: could not find {old[:50]!r}"); ok = False
        else:
            s = s.replace(old, new, 1)
    if ok:
        p.write_text(s); print(f"  patched {name}")

patch("extract.py", [
    ('            "bookrunners": {"type": "array", "items": {"type": "string"}},',
     '            "bookrunners": {"type": "array", "items": {"type": "string"}},\n'
     '            "use_of_proceeds_category": {\n'
     '                "type": ["string", "null"],\n'
     '                "enum": ["acquisition", "refinancing", "general_corporate", "capex",\n'
     '                         "shareholder_returns", "mixed", "not_stated", None],\n'
     '                "description": "null if the document does not say",\n'
     '            },\n'
     '            "use_of_proceeds_quote": {"type": ["string", "null"], "description": "verbatim, under 200 characters"},'),
    ('- Dates as YYYY-MM-DD.',
     '- Dates as YYYY-MM-DD.\n'
     '- Use of proceeds: only if the document states it. Quote it verbatim and pick a category.\n'
     '  Funding an acquisition is "acquisition". Repaying or redeeming existing debt is\n'
     '  "refinancing". If it says both, use "mixed". If the document is silent, use null.'),
])

patch("db.py", [
    ('    bookrunners     TEXT,',
     '    bookrunners     TEXT,\n'
     '    use_of_proceeds TEXT,\n'
     '    proceeds_quote  TEXT,\n'
     '    proceeds_source TEXT,'),
    ('    math_check         TEXT,',
     '    math_check         TEXT,\n'
     '    grade              TEXT,\n'
     '    maturity_bucket    TEXT,\n'
     '    spread_vs_index_bps REAL,'),
    ('"INSERT OR REPLACE INTO deals VALUES (?,?,?,?,?,?,?,?,?,?,?)"',
     '"INSERT OR REPLACE INTO deals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"'),
    ('                ", ".join(terms.get("bookrunners") or []),',
     '                ", ".join(terms.get("bookrunners") or []),\n'
     '                terms.get("use_of_proceeds_category"),\n'
     '                terms.get("use_of_proceeds_quote"),\n'
     '                "fwp" if terms.get("use_of_proceeds_category") else None,'),
    ('            values = [bond_key(t, accession), accession] + [t.get(f) for f in TRANCHE_FIELDS] + [math_check(t)]',
     '            values = ([bond_key(t, accession), accession] + [t.get(f) for f in TRANCHE_FIELDS]\n'
     '                      + [math_check(t), grade(t), maturity_bucket(t), None])'),
    ('def bond_key(t, accession):',
     'IG_MOODYS = {"aaa", "aa1", "aa2", "aa3", "a1", "a2", "a3", "baa1", "baa2", "baa3"}\n'
     'IG_SP = {"aaa", "aa+", "aa", "aa-", "a+", "a", "a-", "bbb+", "bbb", "bbb-"}\n\n\n'
     'def grade(t):\n'
     '    """IG, HY, split when the agencies disagree, or None when unrated here."""\n'
     '    m, s = (t.get("rating_moodys") or "").strip().lower(), (t.get("rating_sp") or "").strip().lower()\n'
     '    calls = [r in ig for r, ig in ((m, IG_MOODYS), (s, IG_SP)) if r]\n'
     '    if not calls:\n'
     '        return None\n'
     '    if all(calls):\n'
     '        return "IG"\n'
     '    return "HY" if not any(calls) else "split"\n\n\n'
     'def maturity_bucket(t):\n'
     '    """Years to maturity from the trade, bucketed the way index families are."""\n'
     '    md = t.get("maturity_date")\n'
     '    if not md:\n'
     '        return None\n'
     '    try:\n'
     '        years = (date.fromisoformat(md) - date.today()).days / 365.25\n'
     '    except ValueError:\n'
     '        return None\n'
     '    for limit, name in ((3, "1-3y"), (5, "3-5y"), (7, "5-7y"), (10, "7-10y"), (15, "10-15y")):\n'
     '        if years <= limit:\n'
     '            return name\n'
     '    return "15y+"\n\n\n'
     'def bond_key(t, accession):'),
    ('from datetime import datetime, timezone',
     'from datetime import date, datetime, timezone'),
])
