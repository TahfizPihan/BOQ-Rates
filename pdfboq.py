"""Convert a PDF BOQ into an Excel sheet that looks like the PDF: title lines, notes and the table, in page order."""
from openpyxl import Workbook

from boq import find_header


def _clean(c):
    return "" if c is None else str(c).replace("\n", " ").strip()


def _num(s):
    t = str(s).replace(",", "").strip()
    try:
        return float(t) if t and t.replace(".", "", 1).replace("-", "", 1).isdigit() else s
    except ValueError:
        return s


def pdf_to_xlsx(pdf_path, xlsx_path):
    import pdfplumber
    rows, has_table = [], False
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            blocks = [(t.bbox[1], [[_clean(c) for c in r] for r in t.extract()]) for t in tables]
            has_table = has_table or bool(tables)

            def keep(obj, tables=tables):  # text that is not inside a table
                if obj.get("object_type") != "char":
                    return True
                return not any(t.bbox[0] <= obj["x0"] <= t.bbox[2] and t.bbox[1] <= obj["top"] <= t.bbox[3] for t in tables)

            for ln in page.filter(keep).extract_text_lines():
                blocks.append((ln["top"], [[ln["text"].strip()]]))
            for _, block in sorted(blocks, key=lambda b: b[0]):
                rows += [r for r in block if any(r)]
    if not has_table:
        raise ValueError("This PDF has no table lines I can read (it may be a scan or a picture). "
                         "Upload the BOQ as an Excel file, or a PDF made from Excel/Word with table borders.")
    width = max(len(r) for r in rows)
    wb = Workbook()
    ws = wb.active
    ws.title = "BOQ"
    for r in rows:
        ws.append(r + [""] * (width - len(r)))
    # only quantity / rate / amount columns become numbers; codes such as 4.10 stay exactly as written
    hr, cols = find_header(ws)
    if hr:
        for kind in ("qty", "rate", "amount"):
            if kind in cols:
                for r in range(hr + 1, ws.max_row + 1):
                    c = ws.cell(r, cols[kind])
                    c.value = _num(c.value)
    wb.save(xlsx_path)
    return len(rows)
