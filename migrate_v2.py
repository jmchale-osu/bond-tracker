"""Add the version 2 columns. Safe to run more than once."""
import sqlite3
import db

NEW_DEAL_COLS = [
    ("ranking", "TEXT"),                 # senior unsecured, subordinated, first mortgage...
    ("is_secured", "INTEGER"),
    ("guarantees", "TEXT"),              # none, parent, subsidiaries, both
    ("guarantor_note", "TEXT"),
    ("change_of_control", "INTEGER"),    # 1 if holders can put the bonds on a change of control
    ("change_of_control_price", "REAL"), # usually 101
    ("coupon_step", "INTEGER"),          # 1 if the coupon steps on a ratings downgrade
    ("coupon_step_note", "TEXT"),
    ("structure_quote", "TEXT"),
    ("structure_source", "TEXT"),
    ("sic", "TEXT"),                     # EDGAR's industry code
    ("sector", "TEXT"),
    ("state_of_incorporation", "TEXT"),
    ("country", "TEXT"),
]


def main():
    conn = db.connect()
    have = {r[1] for r in conn.execute("PRAGMA table_info(deals)")}
    added = []
    for name, kind in NEW_DEAL_COLS:
        if name not in have:
            conn.execute(f"ALTER TABLE deals ADD COLUMN {name} {kind}")
            added.append(name)
    conn.commit()
    print(f"added {len(added)} columns: {', '.join(added) if added else 'none, already up to date'}")


if __name__ == "__main__":
    main()
