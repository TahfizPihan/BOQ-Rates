# BOQ Rate Matcher

Upload your BOQ (Excel or PDF). You get the **same file back as Excel** with the rate filled into the file's own Rate column.
Nothing else is added to your file: no extra columns, no extra sheets.

## What it does with your file
1. **Excel BOQ** is used exactly as it is (layout, colours, merged cells, column widths stay).
   **PDF BOQ** is first converted to an Excel sheet that looks like the PDF (title, table, notes).
2. For every item it finds the rate in the PWD / LGED / RHD schedule, **only on an exact match**:
   - the **description** is the same as the schedule's (upper/lower case, spaces and punctuation are ignored), or
   - the **item code** (in a column left of the description, or written in the description such as `4.1.2 Brick work...`)
     exists in the schedule and the description belongs to that item.
   Plain serial numbers (1, 2, 3...) are never treated as item codes.
3. The rate is written into the Rate column (and Amount = Qty x Rate if the Amount cell is empty).
   Rates already typed in the file are kept.
4. Items with no exact match are **left blank** and listed on the page (tap "items left blank"). Nothing is guessed.

If the same description is in more than one schedule with different rates, PWD is used first, then LGED, then RHD.

## One-time setup (about 15 minutes)
### 1. Put the code on GitHub
Create an empty repository on github.com, then in this folder:
```
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```
(If you already pushed the earlier version, just run `git push`.)

### 2. Load the rate schedules from their PDF links
1. In `sources.json` on GitHub check the links (add the RHD link).
2. Repo **Actions** tab -> **Build rate schedules** -> **Run workflow**. GitHub downloads each PDF once and saves the item
   codes, descriptions, units and rates in `data/schedules/`. You never need to open these files.
3. Read the run log: it shows how many items were read from each PDF and a few sample rows. Compare with the PDF.
   A PDF that cannot be read is reported and never overwrites existing data. In that case put the schedule as
   Excel/CSV into `data/schedules/` named `AGENCY_EDITION.xlsx` (columns: code, description, unit, rate).

### 3. Host it so every device can use it (free)
render.com -> **New** -> **Blueprint** -> pick the repo (`render.yaml` does the rest) and set **APP_PASSWORD**.
Open the address Render gives you on any phone or computer. The free plan sleeps when idle; the first visit takes about a minute.

## Daily use
Open the site -> choose your BOQ (.xlsx or .pdf) -> **Fill rates** -> **Download Excel**.
Options: rate column letter (only needed if the file has no column headed Rate), replace existing rates, choose agencies.

## Run on your own computer instead
Double-click `start.bat` (Windows) or run `./start.sh`, then open http://localhost:5000.

## Limits
- Old `.xls` files: save as `.xlsx` first. Scanned or picture-only PDFs cannot be read (BOQ or schedule).
- Exact matching is only as good as the schedule reading. If many items stay blank although you know they are in the
  schedule, the schedule PDF was probably read differently from how your BOQ words it. Send me the schedule file and the BOQ and I will adjust the reader.
- Check the blank rows before submitting a tender.
