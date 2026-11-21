"""Fill the rate column of the person's own BOQ file. Nothing else in the file is changed or added."""
import re

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import column_index_from_string, get_column_letter

from db import load_items
from exact import ExactMatcher, is_distinct_code

KEYS = {
    "item": ["item no", "item no.", "item code", "code", "sl", "sl no", "sl.", "s/n", "ref", "sn", "no."],
    "desc": ["description", "item of work", "items of work", "particulars", "description of item", "work item", "details"],
    "unit": ["unit", "uom"],
    "qty": ["qty", "quantity", "qty.", "quantities"],
    "rate": ["rate", "unit rate", "rate (tk)", "rate in tk", "rate (taka)", "price", "unit price"],
    "amount": ["amount", "total", "amount (tk)", "total amount", "amount in tk"],
}


def _is(cell, kind):
    c = re.sub(r"\s+", " ", str(cell or "").strip().lower())
    return bool(c) and any(c == w or (len(w) > 5 and w in c) for w in KEYS[kind])


def find_header(ws, scan_rows=40):
    for r in range(1, min(ws.max_row, scan_rows) + 1):
        cols = {}
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            for kind in KEYS:
                if kind not in cols and _is(v, kind):
                    cols[kind] = c
                    break
        if "desc" in cols and len(cols) >= 3:
            return r, cols
    return None, None


def _blank(v):
    return v is None or str(v).strip() in ("", "0", "0.0")


def _row_codes(ws, r, desc_col):
    """Anything in the columns left of the description that looks like an item code."""
    out = []
    for c in range(1, desc_col):
        v = ws.cell(r, c).value
        if v is None:
            continue
        out += [t for t in re.split(r"[\s,;]+", str(v).strip()) if is_distinct_code(t)]
    return out


def fill_boq(in_path, out_path, agencies=None, overwrite=False, rate_col=None):
    items = load_items(agencies)
    if not items:
        raise ValueError("No rate schedule is loaded yet (see README: add the schedule links and build them).")
    matcher = ExactMatcher(items)
    wb = load_workbook(in_path)
    res = {"items": 0, "by_code": 0, "by_desc": 0, "had_rate": 0, "conflicts": 0, "not_filled": []}
    found_table = False
    for ws in wb.worksheets:
        hr, cols = find_header(ws)
        if not hr:
            continue
        found_table = True
        if rate_col:
            try:
                cols["rate"] = column_index_from_string(str(rate_col).strip().upper())
            except ValueError:
                raise ValueError(f"'{rate_col}' is not a column letter (use letters such as F or G).")
            if cols["rate"] == cols["desc"]:
                raise ValueError("The rate column cannot be the Description column.")
        if "rate" not in cols:  # the file has no rate column at all: add one at the end, styled like its neighbour
            col = ws.max_column + 1
            ws.cell(hr, col, "Rate (Tk)")._style = ws.cell(hr, col - 1)._style
            cols["rate"] = col
        elif not ws.cell(hr, cols["rate"]).value:
            ws.cell(hr, cols["rate"], "Rate (Tk)")
        for r in range(hr + 1, ws.max_row + 1):
            desc = ws.cell(r, cols["desc"]).value
            if desc is None or not str(desc).strip() or _is(desc, "desc"):
                continue  # empty row, or a table header repeated on a new PDF page
            unit = ws.cell(r, cols["unit"]).value if "unit" in cols else None
            qty = ws.cell(r, cols["qty"]).value if "qty" in cols else None
            is_item = not (_blank(unit) and _blank(qty)) if ("unit" in cols or "qty" in cols) else True
            rate_cell = ws.cell(r, cols["rate"])
            if isinstance(rate_cell, MergedCell):
                continue
            if not _blank(rate_cell.value) and not overwrite:
                if is_item:
                    res["items"] += 1
                    res["had_rate"] += 1
                continue
            kind, it, conflict, info = matcher.match(_row_codes(ws, r, cols["desc"]), desc)
            if is_item:
                res["items"] += 1
            if it is None:
                if is_item:
                    res["not_filled"].append({
                        "sheet": ws.title, "row": r, "text": re.sub(r"\s+", " ", str(desc))[:80],
                        "reason": f"code {info} found, but its description is different" if kind == "MISMATCH" else "no exact match"})
                continue
            rate_cell.value = it["rate"]
            if rate_cell.number_format == "General":
                rate_cell.number_format = "#,##0.00"
            res["by_code" if kind == "CODE" else "by_desc"] += 1
            res["conflicts"] += bool(conflict)
            if "amount" in cols and "qty" in cols:
                amt = ws.cell(r, cols["amount"])
                if not isinstance(amt, MergedCell) and _blank(amt.value):
                    amt.value = f"=IFERROR({get_column_letter(cols['qty'])}{r}*{get_column_letter(cols['rate'])}{r},0)"
                    if amt.number_format == "General":
                        amt.number_format = "#,##0.00"
    if not found_table:
        raise ValueError("Could not find the BOQ table: a header row with Description and Unit / Qty / Rate columns.")
    wb.save(out_path)
    res["filled"] = res["by_code"] + res["by_desc"]
    return res
