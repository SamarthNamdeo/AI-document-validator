"""AICTE Document Validator, SIH 2026 prototype. Run: uvicorn main:app --reload  (API docs at /docs)
Pages: /  (institution)   /officials.html  (AICTE officials)"""
import json, os, re, uuid, mimetypes, threading, datetime as dt
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import engine

B = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(B, "data")
UP, OR = os.path.join(D, "uploads"), os.path.join(D, "originals")
for p in (UP, OR): os.makedirs(p, exist_ok=True)
CL = os.path.join(B, "config", "checklists.json")
RF, SN, AU, AP = (os.path.join(D, x) for x in ("reference.json", "seen.json", "audit.jsonl", "applications.json"))
app = FastAPI(title="AICTE Document Validator (prototype)")
LOCK = threading.RLock()
print("OCR engines:", engine.engines())

def rd(p, dflt):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except Exception: return dflt

def wr(p, o):  # write to a temp file, then swap it in, so a reader never sees a half-written file
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(o, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)

def now(): return dt.datetime.now().isoformat(timespec="seconds")

def audit(event, **kw):
    with open(AU, "a", encoding="utf-8") as f: f.write(json.dumps({"ts": now(), "event": event, **kw}) + "\n")

def save(folder, key, name, b):
    os.makedirs(folder, exist_ok=True); fn = f"{key}_{re.sub(r'[^A-Za-z0-9._-]', '_', os.path.basename(name))}"
    with open(os.path.join(folder, fn), "wb") as f: f.write(b)
    return fn

def readb(p):
    with open(p, "rb") as f: return f.read()

def serve(path, name):
    if not os.path.isfile(path): raise HTTPException(404, "File not found")
    return FileResponse(path, media_type=mimetypes.guess_type(name)[0] or "application/octet-stream")

def get_app(aid):
    a = next((x for x in rd(AP, []) if x["application_id"] == aid), None)
    if not a: raise HTTPException(404, "Application not found")
    return a

def stage_of(a): return a.get("stage") or (a.get("decision") or {}).get("status") or "PENDING_VERIFICATION"

def visible(a):  # only applications the AI model has passed on reach the officials
    s = stage_of(a); return s in ("PENDING_VERIFICATION", "VERIFIED") or (s == "REJECTED" and (a.get("decision") or {}).get("by") != "AI model")

def for_officials(aid):
    a = get_app(aid)
    if not visible(a): raise HTTPException(404, "This application has not been sent to officials (it is with the AI model, or the model rejected it)")
    return a

def update_app(aid, fn):
    with LOCK:
        apps = rd(AP, []); a = next((x for x in apps if x["application_id"] == aid), None)
        if not a: raise HTTPException(404, "Application not found")
        fn(a); wr(AP, apps); return a

def log_run(out, inst, kind, **extra):
    audit(kind, application_id=out["application_id"], application_type=out["application_type"], institution=inst, summary=out["summary"],
          documents=[{"doc": r["doc_id"], "file": r["file"], "verdict": r["verdict"], "risk": r["risk"],
                      "ref_status": (r.get("reference") or {}).get("status"), "codes": [f["code"] for f in r["findings"]]} for r in out["documents"]], **extra)

# ---------- shared: checklists ----------
@app.get("/api/checklists")
def get_checklists(): return rd(CL, {})

@app.put("/api/checklists")
async def put_checklists(req: Request):
    cl = await req.json(); wr(CL, cl); audit("checklist_updated", types=list(cl)); return {"ok": True}

# ---------- institution page: submit, then the AI model checks every document in the background ----------
@app.post("/api/validate")
async def validate(req: Request, bg: BackgroundTasks):
    form = await req.form(); t = form.get("application_type"); cl = rd(CL, {})
    if t not in cl: raise HTTPException(400, "Unknown application type")
    inst = (form.get("institution_name") or "").strip()
    if not inst: raise HTTPException(400, "The institution name is required")
    files = {}
    for d in cl[t]:
        u = form.get("f__" + d["id"])
        if u is not None and hasattr(u, "read"):
            b = await u.read()
            if b: files[d["id"]] = (u.filename, b)
    missing = [d["name"] for d in cl[t] if d.get("required", True) and d["id"] not in files]
    if missing: raise HTTPException(400, "Upload all required documents first. Missing: " + ", ".join(missing))
    aid = uuid.uuid4().hex[:8].upper()
    stored = {k: {"name": n, "path": save(os.path.join(UP, aid), k, n, b)} for k, (n, b) in files.items()}
    with LOCK:
        apps = rd(AP, []); apps.append({"application_id": aid, "application_type": t, "institution": inst, "submitted_at": now(), "stage": "AI_VERIFICATION", "files": stored, "result": None}); wr(AP, apps)
    audit("application_submitted", application_id=aid, application_type=t, institution=inst, documents=list(files))
    bg.add_task(ai_process, aid)
    return {"application_id": aid, "stage": "AI_VERIFICATION"}

def ai_process(aid):
    a = get_app(aid)
    try:
        docs = rd(CL, {}).get(a["application_type"], [])
        files = {k: (v["name"], readb(os.path.join(UP, aid, v["path"]))) for k, v in a["files"].items()}
        seen = rd(SN, {}); out = engine.run(docs, files, a["institution"], rd(RF, []), seen); wr(SN, seen)
        out.update(application_id=aid, application_type=a["application_type"])
        passed, reasons = engine.ai_gate(out); t = now(); text = "\n".join(reasons)[:1500]
        def done(x):
            x["result"] = out; x["ai"] = {"finished_at": t, "passed": passed, "reasons": reasons}
            if passed: x["stage"] = "PENDING_VERIFICATION"
            else: x["stage"] = "REJECTED"; x["decision"] = {"status": "REJECTED", "reason": text, "decided_at": t, "by": "AI model"}
        update_app(aid, done); log_run(out, a["institution"], "ai_passed" if passed else "ai_rejected", **({} if passed else {"reason": text}))
    except Exception as e:  # never leave an application stuck: send it to the officials for a manual check
        def fail(x): x["stage"] = "PENDING_VERIFICATION"; x["ai"] = {"finished_at": now(), "passed": None, "error": str(e)}; x["result"] = {"documents": [], "summary": {}, "institution_used": a["institution"]}
        update_app(aid, fail); audit("ai_error", application_id=aid, institution=a["institution"], error=str(e))

# ---------- officials page ----------
@app.get("/api/applications")
def list_apps():
    return [{**{k: a[k] for k in ("application_id", "application_type", "institution", "submitted_at")}, "summary": a["result"]["summary"], "decision": (a.get("decision") or {}).get("status"),
             "ai_passed_at": (a.get("ai") or {}).get("finished_at")} for a in reversed(rd(AP, [])) if visible(a)]

@app.get("/api/applications/{aid}")
def app_detail(aid: str): return for_officials(aid)

@app.get("/api/applications/{aid}/file/{doc_id}")
def app_file(aid: str, doc_id: str):
    f = get_app(aid)["files"].get(doc_id)
    if not f: raise HTTPException(404, "File not found")
    return serve(os.path.join(UP, aid, f["path"]), f["name"])

@app.post("/api/applications/{aid}/decision")
async def decide(aid: str, req: Request):
    body = await req.json(); st = body.get("decision")
    if st not in ("VERIFIED", "REJECTED"): raise HTTPException(400, "Decision must be VERIFIED or REJECTED")
    a = for_officials(aid); reason = (body.get("reason") or "").strip()[:500] if st == "REJECTED" else ""
    dec = {"status": st, "reason": reason, "decided_at": now(), "by": "AICTE official"}
    def f(x): x["decision"] = dec; x["stage"] = st
    update_app(aid, f)
    audit("application_" + st.lower(), application_id=aid, institution=a["institution"], documents=list(a["files"]), reason=reason)
    return dec

@app.post("/api/applications/{aid}/reverify")
def reverify(aid: str):
    a = for_officials(aid); docs = rd(CL, {}).get(a["application_type"])
    if docs is None: raise HTTPException(400, "Application type no longer exists in the checklists")
    files = {k: (v["name"], readb(os.path.join(UP, aid, v["path"]))) for k, v in a["files"].items()}
    inst = "" if a["institution"] == "(not provided)" else a["institution"]
    out = engine.run(docs, files, inst, rd(RF, []), {})
    out.update(application_id=aid, application_type=a["application_type"], reverified_at=now()); update_app(aid, lambda x: x.__setitem__("result", out))
    log_run(out, inst, "reverified"); return out

# ---------- track page ----------
@app.get("/api/track/{aid}")
def track(aid: str):
    a = get_app(aid.strip().upper()); dc = a.get("decision") or {}; ai = a.get("ai") or {}; r = a.get("result"); st = stage_of(a)
    names = {d["id"]: d["name"] for d in rd(CL, {}).get(a["application_type"], [])}
    docs = ([{"doc_id": d["doc_id"], "doc_name": d["doc_name"], "file": d["file"], "uploaded": bool(d.get("file")), "optional": d["verdict"] == "OPTIONAL"} for d in r["documents"]] if r and r.get("documents") else
            [{"doc_id": k, "doc_name": names.get(k, k), "file": v["name"], "uploaded": True, "optional": False} for k, v in a["files"].items()])
    return {"application_id": a["application_id"], "institution": a["institution"], "application_type": a["application_type"], "submitted_at": a["submitted_at"],
            "status": st, "reason": dc.get("reason", ""), "decided_at": dc.get("decided_at"), "rejected_by": (dc.get("by") or "AICTE official") if st == "REJECTED" else None,
            "ai_finished_at": ai.get("finished_at"), "ai_passed": ai.get("passed"), "documents": docs}

@app.get("/api/track/{aid}/result")
def track_result(aid: str):
    a = get_app(aid.strip().upper()); r = a.get("result")
    if not r: raise HTTPException(409, "AI verification is still in progress")
    return {**r, "stage": stage_of(a), "reasons": (a.get("ai") or {}).get("reasons", [])}

@app.get("/api/track/{aid}/file/{doc_id}")
def track_file(aid: str, doc_id: str): return app_file(aid.strip().upper(), doc_id)

@app.get("/api/status")
def status(): return {"ocr": engine.engines()}

@app.get("/api/reference")
def get_reference(): return rd(RF, [])

@app.post("/api/originals/extract")
async def extract_original(req: Request):
    f = (await req.form()).get("file")
    if f is None or not hasattr(f, "read"): raise HTTPException(400, "No file")
    d = engine.load(f.filename, await f.read())
    return {"fields": engine.extract_fields(d["text"]), "text_found": len(d["text"].strip()) >= 40, "engine": d["ocr"], "ocr_missing": bool(d.get("ocr_missing")), "error": d.get("error")}

@app.post("/api/originals")
async def add_original(req: Request):
    form = await req.form(); rid = uuid.uuid4().hex[:8]
    rec = {"id": rid, **{k: (form.get(k) or "").strip() for k in ("doc_type", "institution_name", "issuing_authority", "issued_to", "ref_no", "issue_date", "expiry_date")}}
    if not rec["doc_type"] or not rec["institution_name"]: raise HTTPException(400, "Institution and document type are required")
    f = form.get("file")
    if f is not None and hasattr(f, "read"):
        b = await f.read()
        if b: rec["original_file"] = f.filename; rec["path"] = save(OR, rid, f.filename, b)
    db = rd(RF, []); db.append(rec); wr(RF, db)
    audit("original_added", id=rid, institution=rec["institution_name"], doc_type=rec["doc_type"], file=rec.get("original_file")); return rec

@app.get("/api/originals/{rid}/file")
def original_file(rid: str):
    r = next((x for x in rd(RF, []) if x.get("id") == rid and x.get("path")), None)
    if not r: raise HTTPException(404, "File not found")
    return serve(os.path.join(OR, r["path"]), r["original_file"])

@app.delete("/api/reference/{rid}")
def del_reference(rid: str):
    wr(RF, [r for r in rd(RF, []) if r.get("id") != rid]); audit("reference_deleted", id=rid); return {"ok": True}

@app.get("/api/audit")
def get_audit():
    try:
        with open(AU, encoding="utf-8") as f: return [json.loads(l) for l in f][-200:][::-1]
    except FileNotFoundError: return []

app.mount("/", StaticFiles(directory=os.path.join(B, "static"), html=True), name="static")
