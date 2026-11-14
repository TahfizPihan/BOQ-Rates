"""Download rate schedules from the links in sources.json and save them as data/schedules/<AGENCY>_<EDITION>.csv

    python tools/build_rates.py                       # build everything in sources.json
    python tools/build_rates.py --only LGED           # only one agency
    python tools/build_rates.py --file x.pdf --agency PWD --edition 2022   # a local file instead of a link

On GitHub this runs automatically (see .github/workflows/build-rates.yml).
"""
import argparse
import csv
import json
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from importer import read_schedule  # noqa: E402

OUT = ROOT / "data" / "schedules"
MIN_ITEMS = 20  # fewer than this means the PDF layout was not understood; do not overwrite good data


def download(url, dest_dir):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    ext = ".pdf" if data[:4] == b"%PDF" else ".xlsx" if data[:2] == b"PK" else ".csv"
    p = Path(dest_dir) / ("schedule" + ext)
    p.write_bytes(data)
    print(f"  downloaded {len(data)/1e6:.1f} MB ({ext})")
    return p


def build(agency, edition, path):
    rows = read_schedule(path)
    seen, clean = set(), []
    for r in rows:
        key = (str(r["code"]).strip(), str(r["description"]).strip(), str(r["rate"]).strip())
        if key in seen:
            continue
        seen.add(key)
        clean.append({"code": key[0], "description": re.sub(r"\s+", " ", key[1]), "unit": str(r["unit"]).strip(), "rate": key[2].replace(",", "")})
    print(f"  {len(clean)} items read")
    for r in clean[:3] + clean[len(clean)//2:len(clean)//2 + 2]:
        print("   e.g.", r["code"], "|", r["description"][:60], "|", r["unit"], "|", r["rate"])
    if len(clean) < MIN_ITEMS:
        raise RuntimeError(f"only {len(clean)} items found; the PDF layout was not understood. Existing data left unchanged.")
    OUT.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9.\-]+", "-", edition)
    dest = OUT / f"{agency}_{name}.csv"
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["code", "description", "unit", "rate"])
        w.writeheader()
        w.writerows(clean)
    print(f"  saved {dest}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--agency")
    ap.add_argument("--edition")
    ap.add_argument("--only")
    a = ap.parse_args()
    if a.file:
        if not (a.agency and a.edition):
            sys.exit("--file needs --agency and --edition")
        build(a.agency, a.edition, a.file)
        return
    sources = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    failed = []
    for s in sources:
        if a.only and s["agency"].lower() != a.only.lower():
            continue
        if not s.get("url"):
            continue
        print(f"\n{s['agency']} {s['edition']}\n  {s['url']}")
        try:
            with tempfile.TemporaryDirectory() as d:
                build(s["agency"], s["edition"], download(s["url"], d))
        except Exception as e:  # keep going so one bad link does not block the others
            print("  FAILED:", e)
            failed.append(f"{s['agency']} {s['edition']}")
    if failed:
        sys.exit("\nFailed: " + ", ".join(failed))


if __name__ == "__main__":
    main()
