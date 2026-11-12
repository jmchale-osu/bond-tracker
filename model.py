"""
Fair value model: what spread should a new bond have priced at, given what it is and the
market that day? Every bond is scored out of sample: the model is fit only on deals priced
before that bond's week, then asked for its spread. A bond that came wider than the model
said came cheap.

    python model.py

The same regression, fit on everything, also gives the model's answer to each thesis claim:
the coefficient on subordination, collateral, the change of control put, the coupon step and
acquisition funding, holding rating, maturity, market level, size and sector constant. The
range comes from refitting on resamples of issuers (1,000 draws), like the scorecard.

Saves to the database: model_bonds (fair spread and residual per bond), model_weeks (error
per week, model vs a baseline of index spread plus a tenor average) and model_terms
(coefficients with ranges).
"""
import math
from collections import defaultdict
from datetime import date, timedelta

import numpy as np

import db
from enrich import index_on, rating_bucket

NOTCH = {r: i for i, r in enumerate(["aaa", "aa1", "aa2", "aa3", "a1", "a2", "a3", "baa1", "baa2", "baa3",
                                     "ba1", "ba2", "ba3", "b1", "b2", "b3", "caa1", "caa2", "caa3"])}
NOTCH_SP = {r: i for i, r in enumerate(["aaa", "aa+", "aa", "aa-", "a+", "a", "a-", "bbb+", "bbb", "bbb-",
                                        "bb+", "bb", "bb-", "b+", "b", "b-", "ccc+", "ccc", "ccc-"])}
CLAIMS = {"sub": "Subordinated", "secured": "Secured", "coc": "Change of control put",
          "step": "Coupon step", "acq": "Acquisition funding"}
SECTORS = ["Banks", "Insurance", "Utilities", "Real Estate", "Transport", "Industrials", "Services"]
MIN_TRAIN = 150            # bonds needed before the model scores anything
RIDGE = 2.0                # light shrinkage; the structure terms are rare


def notch(moodys, sp):
    m = NOTCH.get((moodys or "").strip().lower())
    s = NOTCH_SP.get((sp or "").strip().lower())
    return m if m is not None else s


def load(conn):
    rows = conn.execute("""
        SELECT t.bond_key, d.issuer, t.spread_bps, t.rating_moodys, t.rating_sp, t.maturity_date,
               t.principal_usd, COALESCE(d.trade_date, d.filing_date), d.ranking, d.change_of_control,
               d.coupon_step, d.use_of_proceeds, d.sector, d.country, t.grade
        FROM tranches t JOIN deals d ON d.accession = t.accession
        WHERE t.spread_bps IS NOT NULL AND COALESCE(t.is_floating, 0) = 0
          AND COALESCE(t.currency, 'USD') = 'USD' AND COALESCE(t.math_check, '') <> 'computed'
    """).fetchall()
    bonds = []
    for key, issuer, spread, moodys, sp, maturity, size, priced, rank, coc, step, uop, sector, country, grade in rows:
        n = notch(moodys, sp)
        if n is None or not maturity or not priced:
            continue
        years = (date.fromisoformat(maturity) - date.fromisoformat(priced)).days / 365.25
        bucket = rating_bucket(moodys, sp)
        family = "hy_rating" if grade == "HY" else "ig_rating"
        label = bucket if bucket in (("BB", "B", "CCC") if grade == "HY" else ("AAA", "AA", "A", "BBB")) else (
            "HY_ALL" if grade == "HY" else "BBB")
        oas = index_on(conn, family, label, priced)
        if oas is None or years <= 0.5:
            continue
        rank = rank or ""
        bonds.append({
            "key": key, "issuer": issuer, "spread": spread, "priced": priced,
            "week": (date.fromisoformat(priced) - timedelta(days=date.fromisoformat(priced).weekday())).isoformat(),
            "oas": oas * 100, "notch": n, "years": years, "size": size or 5e8,
            "sub": int(rank in ("subordinated", "junior_subordinated")),
            "secured": int(rank in ("senior_secured", "first_mortgage")),
            "coc": int(bool(coc)), "step": int(bool(step)), "acq": int(uop == "acquisition"),
            "sector": sector or "", "foreign": int(bool(country) and country != "US"),
        })
    return bonds


def issuer_history(bonds):
    """For each bond, how wide of the index the same issuer's earlier deals came (earlier weeks only,
    so the model never sees the answer). Issuers carry their own credit story; this is the market's
    last word on it."""
    seen = defaultdict(list)
    for week in sorted({b["week"] for b in bonds}):
        batch = [b for b in bonds if b["week"] == week]
        for b in batch:
            past = seen[b["issuer"]]
            b["has_history"] = int(bool(past))
            b["history"] = float(np.mean(past)) if past else 0.0
        for b in batch:
            seen[b["issuer"]].append(b["spread"] - b["oas"] - 8 * math.log(b["years"]))


def features(b):
    """One row of the design matrix. Names line up with NAMES."""
    ly = math.log(b["years"])
    return ([1.0, b["oas"], b["notch"], b["notch"] ** 2 / 10, ly, ly * ly, math.log(b["size"] / 1e9), b["foreign"],
             b["has_history"], b["history"]]
            + [b[c] for c in CLAIMS] + [int(b["sector"] == s) for s in SECTORS])


NAMES = (["intercept", "index_oas", "notch", "notch_sq", "log_years", "log_years_sq", "log_size", "foreign",
          "has_history", "issuer_history"]
         + list(CLAIMS) + [f"sector_{s}" for s in SECTORS])


def fit(X, y):
    """Ridge regression on standardised columns (the intercept is not shrunk)."""
    mu, sd = X.mean(0), X.std(0)
    mu[0], sd[0] = 0, 1
    sd[sd == 0] = 1
    Z = (X - mu) / sd
    penalty = RIDGE * np.eye(X.shape[1])
    penalty[0, 0] = 0
    beta = np.linalg.solve(Z.T @ Z + penalty, Z.T @ y)
    coef = beta / sd
    coef[0] = beta[0] - np.sum(beta[1:] * mu[1:] / sd[1:])
    return coef


def baseline(train, b):
    """What a desk would guess with no model: today's index spread plus the average gap for the tenor."""
    gaps = [t["spread"] - t["oas"] for t in train if abs(math.log(t["years"]) - math.log(b["years"])) < 0.35]
    return b["oas"] + (float(np.median(gaps)) if gaps else 0.0)


def main():
    conn = db.connect()
    conn.executescript("""
        DROP TABLE IF EXISTS model_bonds; DROP TABLE IF EXISTS model_weeks; DROP TABLE IF EXISTS model_terms;
        CREATE TABLE model_bonds (bond_key TEXT PRIMARY KEY, week TEXT, fair_bps REAL, residual_bps REAL, baseline_bps REAL);
        CREATE TABLE model_weeks (week TEXT PRIMARY KEY, bonds INTEGER, train INTEGER, mae_model REAL, mae_baseline REAL);
        CREATE TABLE model_terms (term TEXT PRIMARY KEY, estimate REAL, lo REAL, hi REAL, bonds INTEGER, issuers INTEGER);
    """)
    bonds = sorted(load(conn), key=lambda b: b["priced"])
    issuer_history(bonds)
    if len(bonds) < MIN_TRAIN + 20:
        print(f"Only {len(bonds)} bonds; the model needs {MIN_TRAIN + 20}.")
        return
    by_week = defaultdict(list)
    for b in bonds:
        by_week[b["week"]].append(b)

    scored = []
    for week in sorted(by_week):
        train = [b for b in bonds if b["week"] < week]
        if len(train) < MIN_TRAIN:
            continue
        coef = fit(np.array([features(b) for b in train]), np.array([b["spread"] for b in train]))
        errs, base_errs = [], []
        for b in by_week[week]:
            fair = float(np.array(features(b)) @ coef)
            base = baseline(train, b)
            conn.execute("INSERT INTO model_bonds VALUES (?,?,?,?,?)",
                         (b["key"], week, round(fair, 1), round(b["spread"] - fair, 1), round(base, 1)))
            errs.append(abs(b["spread"] - fair))
            base_errs.append(abs(b["spread"] - base))
            scored.append((b["spread"] - fair, b["spread"] - base))
        conn.execute("INSERT INTO model_weeks VALUES (?,?,?,?,?)",
                     (week, len(errs), len(train), round(float(np.mean(errs)), 1), round(float(np.mean(base_errs)), 1)))

    # The thesis, as the model sees it: fit on everything, resample issuers for the range
    X = np.array([features(b) for b in bonds])
    y = np.array([b["spread"] for b in bonds])
    coef = fit(X, y)
    issuers = sorted({b["issuer"] for b in bonds})
    rows_of = defaultdict(list)
    for i, b in enumerate(bonds):
        rows_of[b["issuer"]].append(i)
    rng = np.random.default_rng(7)
    draws = []
    for _ in range(1000):
        pick = [i for name in rng.choice(issuers, len(issuers)) for i in rows_of[name]]
        draws.append(fit(X[pick], y[pick]))
    draws = np.array(draws)
    for j, name in enumerate(NAMES):
        if name == "intercept":
            continue
        with_it = [b for b in bonds if features(b)[j]] if name in CLAIMS or name.startswith("sector_") or name == "foreign" else bonds
        lo, hi = np.percentile(draws[:, j], [5, 95])
        conn.execute("INSERT INTO model_terms VALUES (?,?,?,?,?,?)",
                     (name, round(float(coef[j]), 2), round(float(lo), 2), round(float(hi), 2),
                      len(with_it), len({b["issuer"] for b in with_it})))
    # Rating and maturity enter as curves; report their slope where most bonds sit
    j = {n: NAMES.index(n) for n in NAMES}
    derived = {
        "rating_at_bbb": lambda c: c[j["notch"]] + 2 * c[j["notch_sq"]] * 8 / 10,          # one notch lower, at BBB
        "maturity_at_10y": lambda c: (c[j["log_years"]] + 2 * c[j["log_years_sq"]] * math.log(10)) * math.log(2),
    }
    for name, f in derived.items():
        lo, hi = np.percentile([f(d) for d in draws], [5, 95])
        conn.execute("INSERT INTO model_terms VALUES (?,?,?,?,?,?)",
                     (name, round(float(f(coef)), 2), round(float(lo), 2), round(float(hi), 2), len(bonds), len(issuers)))
    conn.commit()

    model_mae = np.mean([abs(a) for a, _ in scored])
    base_mae = np.mean([abs(b) for _, b in scored])
    print(f"{len(bonds)} bonds; {len(scored)} scored out of sample over {len(set(w for w in by_week if w >= min(conn.execute('SELECT week FROM model_weeks').fetchone())))} weeks")
    print(f"  mean absolute error: model {model_mae:.1f} bps, baseline (index + tenor average) {base_mae:.1f} bps")
    print("  structure terms (bps, holding the rest constant):")
    for name in CLAIMS:
        est, lo, hi, n, k = conn.execute("SELECT estimate, lo, hi, bonds, issuers FROM model_terms WHERE term = ?", (name,)).fetchone()
        print(f"    {CLAIMS[name]:22} {est:+6.1f}  ({lo:+.0f} to {hi:+.0f})  {n} bonds, {k} issuers")


if __name__ == "__main__":
    main()
