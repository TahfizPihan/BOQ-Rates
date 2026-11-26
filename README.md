# BOQ Rate Matcher

Upload your BOQ (Excel or PDF). You get the same file back as Excel with rates filled in. Unrelated columns (including organization/agency columns) are preserved.

## What it does
- Fills rates only for exact description matches or a schedule item code confirmed by the description. Similar items are shown as suggestions for human review; they are never silently priced.
- Lists each unmatched item with possible schedule matches and a form to enter its confirmed quotation (organization, edition, code, unit, and rate).
- Saves user-confirmed quotations in a separate learned-rate table. They survive official schedule refreshes and match future uploads when the BOQ description and unit agree.
- Supports PWD, LGED, RHD, and other schedule sources. When rates conflict, PWD is preferred, then LGED, then RHD.
- Keeps rates already in the BOQ unless you select “Replace rates already in the file.”

## Load the official schedules
`sources.json` is configured with the current PWD and LGED sources and the two RHD PDFs supplied for the 2026 and 2024 editions. To build/load them:

1. Open the repository's **Actions** tab.
2. Select **Build rate schedules** → **Run workflow**.
3. Check the workflow log for the number of items read from each PDF. Failed/low-count imports do not replace existing schedule data.
4. After the workflow succeeds, allow the web service to redeploy/restart so it loads the new CSV files.

PDF extraction is layout-dependent. Verify the counts and sample rows in the action log, and check rates before tender submission. Picture-only/scanned PDFs may need OCR or an Excel/CSV source.

## Remembering quotations
Local use stores learned rates in `data/boq_rates_items.db`. Hosted services should set `BOQ_DB` to a persistent-volume path to keep user quotations across service replacement or redeploy; the default filesystem on many free hosting plans is ephemeral. Do not commit the database file or share the service without protecting it with `APP_PASSWORD`.

## Daily use
1. Upload `.xlsx`, `.xlsm`, or a text-based `.pdf` BOQ and click **Fill rates**.
2. Download the Excel output and review the unmatched items.
3. For each missing rate, enter the quotation from the appropriate PWD/LGED/RHD schedule and click **Save quotation**. It is then available for future BOQs with the same item description/unit.

Excel layout is preserved as far as openpyxl allows. Scanned PDFs, old `.xls` workbooks, and highly irregular PDFs need conversion to a readable Excel file first.
