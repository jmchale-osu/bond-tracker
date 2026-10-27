"""
The thesis: the market prices what is written in the prospectus.

Each claim compares bonds that have a feature with peers that do not, inside the same
rating bucket (AA, A, BBB, BB...) and maturity bucket. For every bond with the feature:

    difference = its spread vs index - median spread vs index of its peers

The premium is the median difference. The range is the 5th to 95th percentile over
1,000 resamples by issuer: bonds from one deal are not independent evidence, so a claim
that rests on one or two companies shows up as a wide range.

    python thesis.py        print the scorecard
"""
import random
from collections import Counter
from datetime import date, timedelta
from statistics import median

import db
from analysis import is_bdc
from enrich import rating_bucket

RESAMPLES = 1000
MIN_MATCHED = 5          # bonds, and
MIN_ISSUERS = 3          # companies, below which the verdict is "Too early"

SUB = ("subordinated", "junior_subordinated")
SECURED = ("senior_secured", "first_mortgage")


def senior(b):
    """Senior unsecured, so a test of one term is not picking up subordination or collateral."""
    return b["rank"] == "senior_unsecured"


# key, claim, plain explanation, expected sign, has-feature test, peer test
CLAIMS = [
    ("sub", "Subordination is paid for",
     "Subordinated and junior notes are repaid after senior debt in a default, so holders should demand more.",
     +1, lambda b: b["rank"] in SUB, senior),
    ("secured", "Collateral is worth something",
     "Secured notes and first mortgage bonds have a claim on specific assets, so they should price tighter.",
     -1, lambda b: b["rank"] in SECURED, senior),
    ("coc", "Buyers pay up for a change of control put",
     "A put lets holders sell back at 101 if the company is taken over. Bonds with one should price tighter.",
     -1, lambda b: senior(b) and b["coc"], lambda b: senior(b) and not b["coc"]),
    ("step", "Coupon steps mark weaker credits",
     "A coupon that rises on a downgrade is a sweetener issuers offer when buyers are nervous. Expect wider.",
     +1, lambda b: senior(b) and b["step"], lambda b: senior(b) and not b["step"]),
    ("acq", "Acquisition debt carries a concession",
     "Debt raised to buy another company adds leverage; refinancing does not. Expect acquisition deals wider.",
     +1, lambda b: b["proceeds"] == "acquisition", lambda b: b["proceeds"] == "refinancing"),
]


def load(conn):
    rows = conn.execute("""
        SELECT t.bond_key, d.issuer, t.spread_bps, t.spread_vs_index_bps, t.maturity_bucket, t.rating_moodys,
               t.rating_sp, d.ranking, d.change_of_control, d.coupon_step, d.use_of_proceeds,
               COALESCE(d.trade_date, d.filing_date)
        FROM tranches t JOIN deals d ON d.accession = t.accession
        WHERE t.spread_vs_index_bps IS NOT NULL AND t.maturity_bucket IS NOT NULL
    """).fetchall()
    out = []
    for key, issuer, spread, gap, bucket, moodys, sp, rank, coc, step, proceeds, priced in rows:
        rating = rating_bucket(moodys, sp)
        if rating and priced:
            out.append({"key": key, "issuer": issuer, "spread": spread, "gap": gap, "cell": (rating, bucket),
                        "rank": rank, "coc": bool(coc), "step": bool(step),
                        "proceeds": proceeds, "priced": priced})
    return out


def same_issue(b):
    return (b["issuer"], b["priced"], b["cell"][1])


def matched(bonds, has, peer):
    """(bond, its value, peer values, how matched) for every bond with the feature that has a peer.
    Peers from the same issuer, day and maturity come first: that holds the credit itself
    constant, so raw spreads compare directly (a gap vs index would hide the notching we
    want to see). Otherwise peers share the rating and maturity bucket, compared on gap vs index."""
    by_issue, by_cell = {}, {}
    for b in bonds:
        if peer(b):
            by_issue.setdefault(same_issue(b), []).append(b["spread"])
            by_cell.setdefault(b["cell"], []).append(b["gap"])
    out = []
    for b in bonds:
        if not has(b):
            continue
        if same_issue(b) in by_issue:
            out.append((b, b["spread"], by_issue[same_issue(b)], "issuer"))
        elif b["cell"] in by_cell:
            out.append((b, b["gap"], by_cell[b["cell"]], "cell"))
    return out


def estimate(pairs):
    return median(v - median(p) for _, v, p, _ in pairs) if pairs else None


def interval(pairs, rng):
    """Resample issuers (all of each one's bonds together), and each bond's peers, to see how much
    the median moves."""
    by_issuer = {}
    for pair in pairs:
        by_issuer.setdefault(pair[0]["issuer"], []).append(pair)
    groups = list(by_issuer.values())
    if len(groups) < 2:
        return None, None
    draws = []
    for _ in range(RESAMPLES):
        sample = [pair for _ in groups for pair in groups[rng.randrange(len(groups))]]
        draws.append(median(v - median([p[rng.randrange(len(p))] for _ in p]) for _, v, p, _ in sample))
    draws.sort()
    return draws[int(.05 * RESAMPLES)], draws[int(.95 * RESAMPLES) - 1]


def verdict(n, issuers, lo, hi, sign):
    if n < MIN_MATCHED or issuers < MIN_ISSUERS or lo is None:
        return "Too early"
    lo, hi = round(lo), round(hi)          # under a basis point is noise
    if (lo > 0 and sign > 0) or (hi < 0 and sign < 0):
        return "Holding"
    if (lo > 0 and sign < 0) or (hi < 0 and sign > 0):
        return "Not holding"
    return "Mixed"


def week_ends(bonds):
    """The Sunday closing each week with a deal, used to replay the estimate as data arrived."""
    ends = set()
    for b in bonds:
        d = date.fromisoformat(b["priced"])
        ends.add((d + timedelta(days=6 - d.weekday())).isoformat())
    return sorted(ends)


def scorecard(conn=None):
    conn = conn or db.connect()
    bonds = load(conn)
    rng = random.Random(7)
    weeks = week_ends(bonds)
    claims = []
    for key, claim, why, sign, has, peer in CLAIMS:
        pairs = matched(bonds, has, peer)
        lo, hi = interval(pairs, rng)
        trend = []
        for end in weeks:
            so_far = matched([b for b in bonds if b["priced"] <= end], has, peer)
            if len(so_far) >= 3:
                trend.append([end, round(estimate(so_far), 1), len(so_far)])
        est = estimate(pairs)
        issuers = len({b["issuer"] for b, *_ in pairs})
        # Robustness: without specialty finance lenders, and how much rests on one company
        no_sf = matched([b for b in bonds if not is_bdc(b["issuer"])], has, peer)
        top = Counter(b["issuer"] for b, *_ in pairs).most_common(1)
        claims.append({
            "key": key, "claim": claim, "why": why, "sign": sign,
            "est": None if est is None else round(est, 1),
            "lo": None if lo is None else round(lo, 1), "hi": None if hi is None else round(hi, 1),
            "n": len(pairs), "issuers": issuers, "peers": sum(1 for b in bonds if peer(b)),
            "verdict": verdict(len(pairs), issuers, lo, hi, sign), "trend": trend,
            "ex_sf": round(estimate(no_sf), 1) if no_sf else None, "n_ex_sf": len(no_sf),
            "top_issuer": top[0][0] if top else None,
            "top_share": round(top[0][1] / len(pairs), 2) if top else None,
            "points": [{"key": b["key"], "issuer": b["issuer"], "cell": " ".join(b["cell"]),
                        "diff": round(v - median(p), 1), "npeers": len(p), "how": how}
                       for b, v, p, how in pairs],
        })
    return {"claims": claims, "bonds": len(bonds), "as_of": max(b["priced"] for b in bonds)}


if __name__ == "__main__":
    card = scorecard()
    print(f"{card['bonds']} bonds with a rating, tenor and index comparison, through {card['as_of']}\n")
    for c in card["claims"]:
        est = "n/a" if c["est"] is None else f"{c['est']:+.0f} bps"
        span = "" if c["lo"] is None else f"  range {c['lo']:+.0f} to {c['hi']:+.0f}"
        print(f"  {c['verdict']:12} {c['claim']:44} {est:>9}{span}  {c['n']} bonds, {c['issuers']} issuers")
