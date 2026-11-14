"""Fill an Excel BOQ with rates from the saved schedules, keeping the original layout."""
import re
from copy import copy
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font
from openpyxl.utils import column_index_from_string, get_column_letter

from matcher import Matcher
from db import load_items

KEYS = {
    "item": ["item no", "item no.", "item code", "code", "sl", "sl no", "sl.", "s/n", "ref", "sn", "no."],
    "desc": ["description", "item of work", "items of work", "particulars", "description of item", "work item", "details"],
    "unit": ["unit", "uom"],
    "qty": ["qty", "quantity", "qty.", "quantities"],
    "rate": ["rate", "unit rate", "rate (tk)", "rate in tk", "rate (taka)", "price", "unit price"],
    "amount": ["amount", "total", "amount (tk)", "total amount", "amount in tk"],
}
FILLS = {
    "CODE": PatternFill("solid", fgColor="C6EFCE"),
    "DESC": PatternFill("solid", fgColor="DDEBF7"),
    "REVIEW": PatternFill("solid", fgColor="FFEB9C"),
    "NONE": PatternFill("solid", fgColor="FFC7CE"),
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


def fill_boq(in_path, out_path, agencies=None, threshold=85, overwrite=False, progress=None, rate_col=None):
    items = load_items(agencies)
    if not items:
        raise ValueError("No rate schedule loaded for the selected agencies. Import a schedule first.")
    matcher = Matcher(items)
    wb = load_workbook(in_path)
    report = []
    for ws in wb.worksheets:
        hr, cols = find_header(ws)
        if not hr:
            continue
        # the person can name the column the rates must go into (e.g. "F")
        if rate_col:
            try:
                cols["rate"] = column_index_from_string(str(rate_col).strip().upper())
            except ValueError:
                raise ValueError(f"'{rate_col}' is not a valid column letter (use letters such as F or G).")
            if _is(ws.cell(hr, cols["rate"]).value, "desc") or cols["rate"] == cols["desc"]:
                raise ValueError("The rate column cannot be the Description column.")
            if not ws.cell(hr, cols["rate"]).value:
                ws.cell(hr, cols["rate"], "Rate (Tk)")
        # add rate / amount columns if the BOQ has none
        last = max(ws.max_column, cols.get("rate", 0))
        if "rate" not in cols:
            last += 1
            cols["rate"] = last
            ws.cell(hr, last, "Rate (Tk)")
        extra = {}
        for name in ("Matched Code", "Matched Description", "Source", "Match %", "Status"):
            last += 1
            extra[name] = last
            h = ws.cell(hr, last, name)
            h.font = Font(bold=True)
        if "amount" not in cols and "qty" in cols:
            last += 1
            cols["amount"] = last
            ws.cell(hr, last, "Amount (Tk)")
        total_rows = ws.max_row - hr
        for r in range(hr + 1, ws.max_row + 1):
            desc = ws.cell(r, cols["desc"]).value
            if not desc or not str(desc).strip() or _is(desc, "desc"):
                continue  # empty row, or a repeated table header (PDF pages)
            qty = ws.cell(r, cols["qty"]).value if "qty" in cols else None
            unit = ws.cell(r, cols["unit"]).value if "unit" in cols else None
            item_cell = ws.cell(r, cols["item"]).value if "item" in cols else None
            # skip pure heading rows (no unit and no quantity)
            if "qty" in cols and not qty and not unit:
                continue
            m = matcher.match(item_cell, desc, unit, threshold=threshold)
            it = m["item"]
            existing = ws.cell(r, cols["rate"]).value
            if it and (overwrite or existing in (None, "", 0)):
                cell = ws.cell(r, cols["rate"], it["rate"])
                cell.number_format = "#,##0.00"
            if "amount" in cols and "qty" in cols and it:
                q = get_column_letter(cols["qty"])
                rt = get_column_letter(cols["rate"])
                ws.cell(r, cols["amount"], f"=IFERROR({q}{r}*{rt}{r},0)").number_format = "#,##0.00"
            if it:
                ws.cell(r, extra["Matched Code"], it["code"] or "")
                ws.cell(r, extra["Matched Description"], it["description"][:250])
                ws.cell(r, extra["Source"], f'{it["agency"]} {it["edition"]}')
            ws.cell(r, extra["Match %"], m["score"])
            st = ws.cell(r, extra["Status"], {"CODE": "Matched by code", "DESC": "Matched by description",
                                              "REVIEW": "CHECK", "NONE": "No match"}[m["status"]])
            st.fill = FILLS[m["status"]]
            report.append({"sheet": ws.title, "row": r, "description": str(desc)[:120], "status": m["status"],
                           "score": m["score"], "code": it["code"] if it else "", "rate": it["rate"] if it else None,
                           "unit_boq": unit, "unit_sched": it["unit"] if it else "", "source": f'{it["agency"]} {it["edition"]}' if it else "",
                           "alts": [f'{a["code"]} | {a["description"][:70]} | {a["rate"]}' for a in m["alts"]]})
            if progress:
                progress((r - hr) / max(total_rows, 1))
        for name, c in extra.items():
            ws.column_dimensions[get_column_letter(c)].width = 14 if name in ("Match %", "Status", "Source", "Matched Code") else 48
    if not report:
        raise ValueError("Could not find a BOQ table (a header row with Description + Unit/Qty/Rate columns).")
    add_report_sheet(wb, report)
    wb.save(out_path)
    return report


def add_report_sheet(wb, report):
    """Second sheet: every BOQ item with the schedule item it was matched to, and alternatives to check."""
    ws = wb.create_sheet("Match Report", 0)
    heads = ["BOQ Sheet", "BOQ Row", "BOQ Item Description", "BOQ Unit", "Status", "Match %",
             "Schedule", "Schedule Code", "Schedule Unit", "Rate (Tk)", "Other close items (code | description | rate)"]
    ws.append(heads)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E78")
    label = {"CODE": "Matched by code", "DESC": "Matched by description", "REVIEW": "CHECK", "NONE": "No match"}
    for r in report:
        ws.append([r["sheet"], r["row"], r["description"], r["unit_boq"], label[r["status"]], r["score"],
                   r["source"], r["code"], r["unit_sched"], r["rate"], "\n".join(r["alts"])])
        ws.cell(ws.max_row, 5).fill = FILLS[r["status"]]
        ws.cell(ws.max_row, 10).number_format = "#,##0.00"
    for i, w in enumerate([12, 9, 60, 10, 22, 9, 14, 14, 12, 14, 80], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
