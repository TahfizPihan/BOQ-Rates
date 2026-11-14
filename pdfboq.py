"""Turn a PDF BOQ into an Excel grid so it can be priced like any other BOQ."""
from openpyxl import Workbook


def pdf_to_xlsx(pdf_path, xlsx_path):
    import pdfplumber
    grid = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for r in table:
                    cells = [("" if c is None else str(c).replace("\n", " ").strip()) for c in r]
                    if any(cells):
                        grid.append(cells)
    if not grid:
        raise ValueError("No table found in this PDF. It may be a scanned image or have no table lines. "
                         "Upload the BOQ as an Excel file instead, or a text-based PDF.")
    width = max(len(r) for r in grid)
    wb = Workbook()
    ws = wb.active
    ws.title = "BOQ"
    for r in grid:
        row = r + [""] * (width - len(r))
        # keep numbers numeric so Qty x Rate formulas work
        out = []
        for c in row:
            try:
                out.append(float(c.replace(",", "")) if c and c.replace(",", "").replace(".", "", 1).isdigit() else c)
            except ValueError:
                out.append(c)
        ws.append(out)
    wb.save(xlsx_path)
    return len(grid)
