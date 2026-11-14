"""Read a rate schedule (xlsx / csv / pdf) into rows of code, description, unit, rate."""
import re
import pandas as pd

HEADER_WORDS = {
    "code": ["item code", "code", "item no", "item no.", "sl", "sl no", "sl.", "s/n", "ref", "schedule no", "no."],
    "description": ["description", "item of work", "items of work", "particulars", "description of item", "details", "work item"],
    "unit": ["unit", "uom"],
    "rate": ["rate", "unit rate", "rate (tk)", "rate in tk", "rate (taka)", "price", "amount (tk)", "rate tk", "rate/unit"],
}

UNIT_PAT = (r"(?:cu\.?\s?m|sq\.?\s?m|r\.?\s?m|rmt|rm|kg|mt|nos?\.?|l\.?\s?s\.?|ltr|litre|liter|bag|sft|cft|sqft|set|pair|"
            r"each|ton|tonne|quintal|m2|m3|m|job|point|%|lot|bundle|coil|sheet|pcs|piece|day|month|hour)")
CODE_TOKEN = r"(?=[\w\-./]*\d)[A-Za-z0-9][\w\-./]*"
LINE_WITH_CODE = re.compile(rf"^\s*({CODE_TOKEN})\s+(.+?)\s+({UNIT_PAT})\s+([\d,]+(?:\.\d+)?)\s*$", re.I)
LINE_NO_CODE = re.compile(rf"^\s*(.{{8,}}?)\s+({UNIT_PAT})\s+([\d,]+(?:\.\d+)?)\s*$", re.I)


def _match_header(cell, kind):
    c = re.sub(r"\s+", " ", str(cell or "").strip().lower())
    if not c:
        return False
    return any(c == w or (len(w) > 4 and w in c) for w in HEADER_WORDS[kind])


def detect_columns(header_cells):
    """Return {kind: index} for a candidate header row, or None if not enough found."""
    found = {}
    for kind in ("description", "rate", "unit", "code"):
        for i, c in enumerate(header_cells):
            if i in found.values():
                continue
            if _match_header(c, kind):
                found[kind] = i
                break
    return found if "description" in found and "rate" in found else None


def _blank(v):
    return v is None or str(v).strip() in ("", "None", "nan")


def _is_number(v):
    try:
        return float(str(v).replace(",", "")) > 0
    except (TypeError, ValueError):
        return False


def _continues(prev_desc, desc):
    """Is `desc` the wrapped second line of the previous item's description?"""
    return desc[:1].islower() or prev_desc.rstrip().endswith((",", "-", "(", " and", " of", " with", " in", " for"))


def _rows_from_grid(grid):
    """grid: list of lists. Finds the header row, then maps the rest. Handles repeated headers
    (every PDF page) and descriptions wrapped onto a second line."""
    cols, out = None, []
    for row in grid:
        row = [("" if c is None else str(c).replace("\n", " ").strip()) for c in row]
        det = detect_columns(row)
        if det:
            cols = det
            continue
        if not cols:
            continue
        get = lambda k: row[cols[k]] if k in cols and cols[k] < len(row) else ""
        desc, rate, unit, code = get("description"), get("rate"), get("unit"), get("code")
        if _blank(desc):
            continue
        if _is_number(rate):
            out.append({"code": code, "description": desc, "unit": unit, "rate": rate})
        elif out and _blank(rate) and _blank(unit) and _blank(code) and _continues(out[-1]["description"], desc):
            out[-1]["description"] += " " + desc
    return out


def read_excel_or_csv(path):
    if str(path).lower().endswith((".csv", ".tsv")):
        df = pd.read_csv(path, header=None, dtype=str, keep_default_na=False,
                         sep="\t" if str(path).lower().endswith(".tsv") else ",", encoding="utf-8-sig")
        return _rows_from_grid(df.values.tolist())
    rows = []
    for _, df in pd.read_excel(path, sheet_name=None, header=None, dtype=str).items():
        rows += _rows_from_grid(df.fillna("").values.tolist())
    return rows


def read_pdf(path):
    import pdfplumber
    grid = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for r in table:
                    grid.append(r)
    rows = _rows_from_grid(grid)
    if len(rows) >= 5:
        return rows
    # Fallback for PDFs without ruled tables: parse text lines such as
    #   "4.1.2  Brick work in cement mortar (1:6) ... cum  8,450.00"
    rows, pending = [], None  # pending = an item whose description wraps onto later lines
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                s = line.strip()
                if not s:
                    continue
                m = LINE_WITH_CODE.match(line)
                if m:
                    rows.append({"code": m[1], "description": m[2], "unit": m[3], "rate": m[4]})
                    pending = None
                    continue
                start = re.match(rf"^({CODE_TOKEN})\s+(\S.*)$", s)
                if start and not (pending and _continues(" ".join(pending["parts"]), s)):
                    pending = {"code": start[1], "parts": [start[2]], "n": 1}   # new item, first line only
                    continue
                if pending:
                    tail = re.match(rf"^(.*?)\s*\b({UNIT_PAT})\s+([\d,]+(?:\.\d+)?)\s*$", s, re.I)
                    if tail:
                        desc = " ".join(pending["parts"] + ([tail[1]] if tail[1] else []))
                        rows.append({"code": pending["code"], "description": desc, "unit": tail[2], "rate": tail[3]})
                        pending = None
                    elif pending["n"] < 6:
                        pending["parts"].append(s)
                        pending["n"] += 1
                    else:
                        pending = None
                    continue
                m = LINE_NO_CODE.match(line)
                if m:
                    rows.append({"code": "", "description": m[1], "unit": m[2], "rate": m[3]})
                    continue
                if rows and not re.search(r"\d[\d,]*\.\d\d\s*$", s) and _continues(rows[-1]["description"], s):
                    rows[-1]["description"] += " " + s
    return rows


def read_schedule(path):
    p = str(path).lower()
    if p.endswith(".pdf"):
        return read_pdf(path)
    return read_excel_or_csv(path)
