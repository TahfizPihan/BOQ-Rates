# BOQ Rate Matcher

Open it from any device, upload a BOQ (**Excel or PDF**), and download an **Excel** file with the rate filled in for every
item. Rates come from the PWD / LGED / RHD rate-schedule PDFs that you point it to with web links.

```
your phone / laptop  ->  hosted app (Render)  ->  data/schedules/*.csv  <-  GitHub Action  <-  PDF links in sources.json
```

## One-time setup (about 15 minutes)

### 1. Put the code on GitHub
Create an empty repository on github.com (private is fine), then in this folder:
```
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

### 2. Build the rate schedules from the PDF links
1. Open `sources.json` on GitHub and check the links (PWD and LGED are filled in; add the RHD link, then commit).
2. Go to the repo's **Actions** tab -> **Build rate schedules** -> **Run workflow**.
   (It also runs by itself whenever you edit `sources.json`.)
3. Open the finished run and read the log: it shows how many items were read from each PDF and a few sample rows.
   Compare the samples with the PDF. The new files appear in `data/schedules/` (e.g. `LGED_2022.csv`).
4. If a PDF cannot be read (the log says so, and existing data is never overwritten), download the schedule as Excel
   or fix it by hand, name it `AGENCY_EDITION.xlsx` or `.csv` (columns: code, description, unit, rate) and drop it into
   `data/schedules/` on GitHub.

### 3. Host it so every device can use it (free)
1. render.com -> **New** -> **Blueprint** (or Web Service) -> connect the GitHub repo. `render.yaml` sets everything up.
2. When asked, set **APP_PASSWORD** to a password of your choice. Anyone opening the site must enter it (any user name).
3. Open the URL Render gives you (bookmark it on your phone and laptop).
   Render's free plan sleeps when idle, so the first visit after a while takes about a minute to wake up.

Every time the rate CSV files change on GitHub, Render redeploys and the app uses the new rates automatically.

## Daily use
1. Open the site, enter the password.
2. Choose or drop your BOQ (.xlsx or .pdf). Optional: type the column letter where rates should go (e.g. `F`);
   leave it blank to use the file's own Rate column (one is added if missing).
3. Tap **Find rates & create Excel**, then **Download Excel**.

The Excel has your BOQ with Rate (and Amount = Qty x Rate) filled in, extra columns for the matched code/description/source,
and a **Match Report** sheet. Colours: green = matched by item code, blue = by description, yellow = **CHECK**, red = no match.

## Adding a new edition later
Add a new entry to `sources.json` (agency, edition, url) and the Action builds it. Old editions stay until you delete their CSV.
Use the *Use only* tick-boxes on the page to choose agencies when several are loaded.

## Run on your own computer instead
Double-click `start.bat` (Windows) or run `./start.sh`; the page opens at http://localhost:5000.
To test the rate builder locally: `python tools/build_rates.py --file schedule.pdf --agency PWD --edition 2022`.

## How matching works
Item code in the BOQ is looked up first. Otherwise the description is compared with every schedule item; mix ratios (1:2:4),
sizes (12 mm) and units must agree. 85%+ is filled in, 60-85% is filled but marked CHECK, below 60% is left blank.
Rates already typed into the BOQ are kept unless you tick *Replace rates already in the file*.

## Limits
- Scanned (image-only) PDFs cannot be read for either the schedule or the BOQ. Use Excel or a text PDF.
- PDF layouts vary a lot. Always check the Action log samples and the CHECK / red rows before submitting a tender.
- The rate tables are only as current as the PDF links in `sources.json`.
