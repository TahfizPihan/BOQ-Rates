"""BOQ Rate Matcher - web server.
Local:   python server.py   -> http://localhost:5000
Hosted:  gunicorn server:app   (see README / render.yaml). Set APP_PASSWORD to require a login.
"""
import hmac
import os
import tempfile
import threading
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file

import db
from boq import fill_boq
from matcher import Matcher
from pdfboq import pdf_to_xlsx

WORK = Path(tempfile.gettempdir()) / "boq_rates_work"
WORK.mkdir(exist_ok=True)
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
RESULTS = {}  # download id -> output file
ITEMS = db.sync_from_csv()  # load the rate schedules saved in data/schedules


@app.before_request
def login():
    pw = os.environ.get("APP_PASSWORD")
    if not pw or request.path == "/healthz":
        return None
    a = request.authorization
    if a and hmac.compare_digest((a.password or "").encode(), pw.encode()):
        return None
    return Response("Password required", 401, {"WWW-Authenticate": 'Basic realm="BOQ Rate Matcher"'})


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/schedules")
def list_schedules():
    return jsonify(db.schedules())


@app.post("/api/process")
def process():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="Choose a BOQ file first."), 400
    d = WORK / uuid.uuid4().hex
    d.mkdir()
    src = d / Path(f.filename).name
    f.save(src)
    ext = src.suffix.lower()
    try:
        if ext == ".pdf":
            x = src.with_suffix(".xlsx")
            pdf_to_xlsx(src, x)
            src = x
        elif ext == ".csv":
            import pandas as pd
            x = src.with_suffix(".xlsx")
            pd.read_csv(src, header=None, dtype=str, keep_default_na=False).to_excel(x, header=False, index=False)
            src = x
        elif ext not in (".xlsx", ".xlsm"):
            return jsonify(error="Upload the BOQ as an Excel (.xlsx) or PDF file."), 400
        out = d / (src.stem + "_priced.xlsx")
        rep = fill_boq(src, out, agencies=request.form.getlist("agencies") or None,
                       threshold=int(request.form.get("threshold", 85)),
                       overwrite=request.form.get("overwrite") == "1",
                       rate_col=request.form.get("rate_col", "").strip() or None)
    except Exception as e:
        return jsonify(error=str(e)), 400
    rid = uuid.uuid4().hex
    RESULTS[rid] = out
    return jsonify(
        id=rid, filename=out.name, total=len(rep),
        matched=sum(r["status"] in ("CODE", "DESC") for r in rep),
        check=sum(r["status"] == "REVIEW" for r in rep),
        none=sum(r["status"] == "NONE" for r in rep), rows=rep)


@app.get("/download/<rid>")
def download(rid):
    p = RESULTS.get(rid)
    if not p or not p.exists():
        return "Expired - upload the BOQ again", 404
    return send_file(p, as_attachment=True, download_name=p.name)


@app.get("/api/search")
def search():
    q = request.args.get("q", "").strip()
    items = db.load_items()
    if not q or not items:
        return jsonify([])
    code = db.norm_code(q)
    out = [(100, i) for i in items if i["code"] == code] + Matcher(items).search(q, 20)
    seen, rows = set(), []
    for s, i in out:
        if i["id"] in seen:
            continue
        seen.add(i["id"])
        rows.append({"score": s, "agency": i["agency"], "edition": i["edition"], "code": i["code"],
                     "description": i["description"], "unit": i["unit"], "rate": i["rate"]})
    return jsonify(rows)


if __name__ == "__main__":
    url = "http://localhost:5000"
    print(f"\n  BOQ Rate Matcher running at {url}  ({ITEMS} rate items loaded)\n  Press Ctrl+C to stop\n")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
