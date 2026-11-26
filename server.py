"""BOQ Rate Matcher - web server."""
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
from pdfboq import pdf_to_xlsx

WORK = Path(tempfile.gettempdir()) / "boq_rates_work"
WORK.mkdir(exist_ok=True)
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
RESULTS = {}
ITEMS = db.sync_from_csv()


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


@app.post("/api/learn")
def learn_rate():
    data = request.get_json(silent=True) or {}
    try:
        db.add_learned_item(data.get("agency"), data.get("edition"), data.get("code"),
                            data.get("description"), data.get("unit"), data.get("rate"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(ok=True, message="Saved. This quotation can be matched on future uploads."), 201


@app.post("/api/process")
def process():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="Choose a BOQ file first."), 400
    d = WORK / uuid.uuid4().hex
    d.mkdir()
    name = Path(f.filename).name
    src = d / name
    f.save(src)
    ext = src.suffix.lower()
    try:
        if ext == ".pdf":
            x = d / (src.stem + ".xlsx")
            pdf_to_xlsx(src, x)
            src = x
        elif ext == ".xls":
            return jsonify(error="Old .xls files are not supported. Open it in Excel and Save As .xlsx, or upload the PDF."), 400
        elif ext not in (".xlsx", ".xlsm"):
            return jsonify(error="Upload the BOQ as an Excel (.xlsx) or PDF file."), 400
        out = d / (Path(name).stem + "_rates.xlsx")
        res = fill_boq(src, out, agencies=request.form.getlist("agencies") or None,
                       overwrite=request.form.get("overwrite") == "1",
                       rate_col=request.form.get("rate_col", "").strip() or None)
    except Exception as e:
        return jsonify(error=str(e)), 400
    rid = uuid.uuid4().hex
    RESULTS[rid] = out
    return jsonify(id=rid, filename=out.name, **res)


@app.get("/download/<rid>")
def download(rid):
    p = RESULTS.get(rid)
    if not p or not p.exists():
        return "Expired - upload the BOQ again", 404
    return send_file(p, as_attachment=True, download_name=p.name)


if __name__ == "__main__":
    url = "http://localhost:5000"
    print(f"\n  BOQ Rate Matcher running at {url}  ({ITEMS} rate items loaded)\n  Press Ctrl+C to stop\n")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
