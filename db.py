"""SQLite storage for rate schedule items (PWD / LGED / RHD / any other)."""
import csv
import os
import re
import sqlite3
from pathlib import Path

# Keep the local database with the application instead of the OS temp directory.
# Hosted deployments should set BOQ_DB to a persistent-volume path if they need
# learned quotations to survive a service replacement/redeploy.
DB_PATH = Path(os.environ.get("BOQ_DB", Path(__file__).parent / "data" / "boq_rates_items.db"))
DATA_DIR = Path(os.environ.get("BOQ_DATA_DIR", Path(__file__).parent / "data" / "schedules"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agency TEXT NOT NULL,
    edition TEXT NOT NULL,
    code TEXT,
    description TEXT NOT NULL,
    norm_desc TEXT NOT NULL,
    unit TEXT,
    rate REAL
);
CREATE INDEX IF NOT EXISTS idx_code ON items(code);
CREATE INDEX IF NOT EXISTS idx_agency ON items(agency, edition);
CREATE TABLE IF NOT EXISTS learned_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agency TEXT NOT NULL,
    edition TEXT NOT NULL,
    code TEXT,
    description TEXT NOT NULL,
    norm_desc TEXT NOT NULL,
    unit TEXT,
    rate REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agency, edition, norm_desc, unit)
);
CREATE INDEX IF NOT EXISTS idx_learned_desc ON learned_items(norm_desc);
"""

UNIT_MAP = {
    "cum": "cum", "m3": "cum", "cu.m": "cum", "cu m": "cum", "cubic meter": "cum", "cubic metre": "cum",
    "sqm": "sqm", "m2": "sqm", "sq.m": "sqm", "sq m": "sqm", "square meter": "sqm", "square metre": "sqm",
    "rm": "rm", "rmt": "rm", "r.m": "rm", "m": "rm", "meter": "rm", "metre": "rm", "running meter": "rm",
    "kg": "kg", "mt": "mt", "ton": "mt", "tonne": "mt", "nos": "nos", "no": "nos", "no.": "nos", "each": "nos",
    "ls": "ls", "l.s": "ls", "lump sum": "ls", "ltr": "ltr", "litre": "ltr", "liter": "ltr",
    "bag": "bag", "sft": "sft", "sqft": "sft", "cft": "cft", "set": "set", "pair": "pair",
}


def norm_unit(u):
    if not u:
        return ""
    u = re.sub(r"\s+", " ", str(u).strip().lower()).rstrip(".")
    return UNIT_MAP.get(u, UNIT_MAP.get(u.replace(".", ""), u))


STOPWORDS = {
    "and", "of", "in", "the", "for", "by", "with", "on", "at", "to", "a", "an", "as", "per", "etc", "all",
    "supply", "supplying", "providing", "provide", "fixing", "fix", "install", "installing", "installation",
    "placing", "place", "complete", "including", "work", "works", "item", "using", "used", "than", "or",
}
SYNONYMS = [
    (r"\bbrickwork\b", "brick work"), (r"\bearthwork\b", "earth work"),
    (r"\br\.?\s?c\.?\s?c\.?\b", "reinforced cement concrete"), (r"\bp\.?\s?c\.?\s?c\.?\b", "plain cement concrete"),
    (r"\bm\.\s?s\.?\b", "ms"), (r"\bg\.?\s?i\.?\b", "gi"), (r"\bc\.?\s?i\.?\b", "ci"),
    (r"\bsand\s*filling\b", "sand fill"), (r"\bplastering\b", "plaster"), (r"\bexcavating\b", "excavation"),
    (r"\bmanual labou?r\b", "manual"), (r"\bdeformed bars?\b", "deformed bar"), (r"\breinforcement bars?\b", "reinforcement bar"),
]


def norm_text(s):
    s = str(s or "").lower()
    s = s.replace("&", " and ")
    for pat, rep in SYNONYMS:
        s = re.sub(pat, rep, s)
    s = re.sub(r"(\d)\s*[:/]\s*(\d)", r"\1_\2", s)
    s = re.sub(r"(\d)\s*(mm|cm|mtr|kg|mpa|psi|nos)\b", r"\1\2", s)
    s = re.sub(r"[^a-z0-9_.% ]+", " ", s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)
    return " ".join(w for w in s.split() if w not in STOPWORDS)


def norm_code(c):
    return re.sub(r"[\s]+", "", str(c or "")).strip(" .").upper()


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def add_items(rows, agency, edition, replace=True):
    """rows: iterable of dicts with code, description, unit, rate."""
    con = connect()
    if replace:
        con.execute("DELETE FROM items WHERE agency=? AND edition=?", (agency, edition))
    n = 0
    for r in rows:
        desc = str(r.get("description") or "").strip()
        if not desc:
            continue
        try:
            rate = float(str(r.get("rate")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        con.execute(
            "INSERT INTO items(agency, edition, code, description, norm_desc, unit, rate) VALUES (?,?,?,?,?,?,?)",
            (agency, edition, norm_code(r.get("code")), desc, norm_text(desc), norm_unit(r.get("unit")), rate),
        )
        n += 1
    con.commit()
    con.close()
    return n


def add_learned_item(agency, edition, code, description, unit, rate):
    """Save a user-confirmed quotation independently of rebuilt official schedules."""
    desc = str(description or "").strip()
    if not desc or len(desc) > 2000:
        raise ValueError("Enter an item description (maximum 2,000 characters).")
    try:
        value = float(str(rate).replace(",", "").strip())
    except (TypeError, ValueError):
        raise ValueError("Enter a valid numeric rate.")
    if value < 0 or value > 1_000_000_000:
        raise ValueError("Rate must be between 0 and 1,000,000,000.")
    agency = str(agency or "").strip()[:40]
    edition = str(edition or "").strip()[:80]
    if not agency or not edition:
        raise ValueError("Choose an organization and enter the schedule edition.")
    con = connect()
    con.execute("""INSERT INTO learned_items(agency, edition, code, description, norm_desc, unit, rate)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(agency, edition, norm_desc, unit) DO UPDATE SET
                     code=excluded.code, description=excluded.description, rate=excluded.rate""",
                (agency, edition, norm_code(code), desc, norm_text(desc), norm_unit(unit), value))
    con.commit()
    con.close()


def schedules():
    con = connect()
    out = [dict(r) for r in con.execute(
        "SELECT agency, edition, COUNT(*) AS items FROM items GROUP BY agency, edition "
        "UNION ALL SELECT agency, edition, COUNT(*) AS items FROM learned_items GROUP BY agency, edition "
        "ORDER BY agency, edition")]
    con.close()
    return out


def delete_schedule(agency, edition):
    con = connect()
    con.execute("DELETE FROM items WHERE agency=? AND edition=?", (agency, edition))
    con.commit()
    con.close()


def load_items(agencies=None):
    con = connect()
    q, args = "SELECT * FROM items", []
    if agencies:
        q += " WHERE agency IN (%s)" % ",".join("?" * len(agencies))
        args = list(agencies)
    out = [dict(r) for r in con.execute(q, args)]
    lq, largs = "SELECT * FROM learned_items", []
    if agencies:
        lq += " WHERE agency IN (%s)" % ",".join("?" * len(agencies))
        largs = list(agencies)
    out.extend(dict(r) for r in con.execute(lq, largs))
    con.close()
    return out


def sync_from_csv(directory=None):
    """Load schedule files without deleting user-learned quotations."""
    from importer import read_schedule
    directory = Path(directory or DATA_DIR)
    con = connect()
    con.execute("DELETE FROM items")
    con.commit()
    con.close()
    total = 0
    for f in sorted(directory.glob("*")):
        if f.suffix.lower() not in (".csv", ".xlsx") or f.name.startswith(("_", "~")):
            continue
        agency, _, edition = f.stem.partition("_")
        if f.suffix.lower() == ".csv":
            with open(f, encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
        else:
            rows = read_schedule(f)
        total += add_items(rows, agency, edition or "current", replace=True)
    return total
