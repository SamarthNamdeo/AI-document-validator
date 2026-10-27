"""Document analysis engine. Every finding is an advisory indicator for human review, never proof of forgery."""
import io, os, re, shutil, hashlib, difflib, zipfile, datetime as dt
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image, ImageChops, ImageOps, ImageFilter

try: import pytesseract
except Exception: pytesseract = None
try: import fitz  # PyMuPDF
except Exception: fitz = None
try: from pypdf import PdfReader
except Exception: PdfReader = None

W = {"high": 35, "medium": 15, "low": 5, "info": 0}
EDIT_SW = ["photoshop", "gimp", "canva", "pixlr", "picsart", "illustrator", "ilovepdf", "smallpdf", "sejda", "paint.net"]
AI_SW = ["midjourney", "dall-e", "dalle", "stable diffusion", "firefly", "openai", "leonardo", "ideogram", "c2pa", "comfyui", "automatic1111"]
SUSPECT = re.compile(r"lorem ipsum|specimen|sample copy|\bdraft\b|x{4,}|\[insert|as an ai language model|duplicate copy|void|cancelled", re.I)
PAT = {
    "institution_name": r"(?:name of (?:the )?institution|institution(?: name)?|college name|institute)\s*[:;\-–|]\s*(.+)",
    "issuing_authority": r"(?:issued by|issuing authority|authority)\s*[:;\-–|]\s*(.+)",
    "issued_to": r"(?:issued to|granted to|awarded to|name of (?:the )?(?:applicant|person|signatory)|in favou?r of)\s*[:;\-–|]\s*(.+)",
    "issue_date": r"(?:date of issue|issued on|issue date|dated)\s*[:;\-–|]\s*(.+)",
    "expiry_date": r"(?:valid (?:up ?to|till|until)|expiry date|expires on|date of expiry)\s*[:;\-–|]\s*(.+)",
    "ref_no": r"(?:certificate no|reference no|ref(?:erence)?\.? ?no|file no|registration no|licen[cs]e no|document no)\.?\s*[:;\-–|]\s*(\S+)",
}
DRX = re.compile(r"\d{1,2}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9},?\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}")
FMTS = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"]


def F(sev, code, msg, ev=""): return {"severity": sev, "code": code, "message": msg, "evidence": ev}
def norm(s): return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower().replace("&", "and"))).strip()
def same_name(a, b):
    # same institution: near-identical text, or one name is a (long enough) part of the other. "...Indore" is not "...Bhopal".
    na, nb = norm(a), norm(b)
    if not na or not nb: return False
    if difflib.SequenceMatcher(None, na, nb).ratio() >= 0.9: return True
    sh, lg = sorted((na, nb), key=len); return sh in lg and len(sh) >= 0.6 * len(lg)

def sim(a, b): return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio() if a and b else 0.0


def pdate(s):
    m = DRX.search(s or "")
    if not m: return None
    t = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", m.group()).replace(",", "")
    t = re.sub(r"\s*([/\-.])\s*", r"\1", t)
    for f in FMTS:
        try: return dt.datetime.strptime(t, f).date()
        except ValueError: pass
    return None


# ---------- 1. extraction (text layer, DOCX parsing, OCR) ----------
EXTS_IMG = ("jpg", "jpeg", "png", "tif", "tiff", "bmp", "webp")
_T, _rapid = None, None

def tess_ok():
    global _T
    if _T is None:
        if pytesseract and not shutil.which("tesseract"):  # Windows installs often are not on PATH
            for c in (r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
                if os.path.isfile(c): pytesseract.pytesseract.tesseract_cmd = c; break
        try: pytesseract.get_tesseract_version(); _T = True
        except Exception: _T = False
    return _T

def rapid_ok():
    # RapidOCR is installed with pip alone (models are inside the package), so it needs no separate program
    global _rapid
    if _rapid is None:
        _rapid = False
        for mod in ("rapidocr_onnxruntime", "rapidocr"):
            try: _rapid = (mod, __import__(mod, fromlist=["RapidOCR"]).RapidOCR()); break
            except Exception: continue
    return bool(_rapid)

def engines():
    return {"tesseract": tess_ok(), "rapidocr": rapid_ok(), "pymupdf": bool(fitz), "pypdf": bool(PdfReader)}

def prep(img):
    # OCR preprocessing: fix orientation, grayscale, stretch contrast, resize to a readable size, sharpen
    g = ImageOps.autocontrast(ImageOps.exif_transpose(img).convert("L"))
    if max(g.size) < 1800:
        f = 1800 / max(g.size); g = g.resize((int(g.width * f), int(g.height * f)), Image.LANCZOS)
    elif max(g.size) > 3200: g.thumbnail((3200, 3200))
    return g.filter(ImageFilter.SHARPEN)

def ocr(img):
    # returns (text, mean confidence 0-100, engine name); engine is None when no OCR engine is installed
    g = prep(img)
    if tess_ok():
        def tess(im, psm):
            d = pytesseract.image_to_data(im, config=f"--psm {psm}", output_type=pytesseract.Output.DICT)
            lines, cf = {}, []
            for i, w in enumerate(d["text"]):
                if str(w).strip():
                    lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(str(w))
                    if float(d["conf"][i]) >= 0: cf.append(float(d["conf"][i]))
            return "\n".join(" ".join(v) for v in lines.values()), (sum(cf) / len(cf) if cf else 0.0)
        try:
            best, top = ("", 0.0), -1.0  # try other page layouts, then sideways or upside-down scans; keep the most confident reading
            for ang, psm in ((0, 6), (0, 4), (0, 11), (90, 6), (270, 6), (180, 6)):
                t, c = tess(g if ang == 0 else g.rotate(ang, expand=True), psm)
                if len(t.strip()) * c > top: best, top = (t, c), len(t.strip()) * c
                if len(best[0].strip()) >= 80 and best[1] >= 70: break
            return best[0], best[1], "tesseract"
        except Exception: pass
    if rapid_ok():
        try:
            mod, eng = _rapid; out = eng(np.asarray(g.convert("RGB")))
            if mod == "rapidocr_onnxruntime": res = out[0] or []  # [[box, text, score], ...]
            else: res = list(zip(out.boxes if out.boxes is not None else [], out.txts or [], out.scores or []))
            items = sorted((b[0][1], b[0][0], t, float(sc), abs(b[2][1] - b[0][1])) for b, t, sc in res)
            ln = []
            for y, x, t, sc, h in items:  # group boxes into text lines, left to right
                if ln and abs(y - ln[-1][0]) < 0.6 * h: ln[-1][1].append((x, t))
                else: ln.append([y, [(x, t)]])
            return "\n".join(" ".join(t for _, t in sorted(l[1])) for l in ln), (100 * sum(i[3] for i in items) / len(items) if items else 0.0), mod
        except Exception: pass
    return "", None, None

def docx_text(data):
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml"))
    para = lambda p: "".join("\t" if e.tag == ns + "tab" else (e.text or "") for e in p.iter() if e.tag in (ns + "t", ns + "tab"))
    out = []
    for ch in root.find(ns + "body"):
        if ch.tag == ns + "p": out.append(para(ch))
        elif ch.tag == ns + "tbl":
            for tr in ch.iter(ns + "tr"):  # two-column rows become "label: value" lines
                cells = [" ".join(para(p) for p in tc.iter(ns + "p")).strip() for tc in tr.findall(ns + "tc")]
                out.append(": ".join(cells) if len(cells) == 2 else " | ".join(cells))
    return "\n".join(out)

RTF_SKIP = {"fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer", "themedata", "colorschememapping", "datastore", "latentstyles", "listtable", "listoverridetable", "rsidtbl"}

def kind_of(ext, data):
    # decide the real file type from the first bytes, so a wrong or missing extension does not matter
    h = data[:8]
    if h.startswith(b"%PDF"): return "pdf"
    if h.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"BM", b"II*\x00", b"MM\x00*")) or (h.startswith(b"RIFF") and data[8:12] == b"WEBP"): return "img"
    if h.startswith(b"{\\rtf"): return "rtf"
    if h.startswith(b"\xd0\xcf\x11\xe0"): return "doc"
    if h.startswith(b"PK"):
        try: names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except Exception: return ext
        return "docx" if "word/document.xml" in names else "odt" if "content.xml" in names else "xlsx" if "xl/workbook.xml" in names else ext
    return ext

def decode_text(data):
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"): return data.decode("utf-16", "ignore")
    return data.decode("utf-8", "ignore")

def rtf_text(data):
    s, out, depth, skip, i = data.decode("latin-1"), [], 0, None, 0
    while i < len(s):
        c = s[i]
        if c == "{":
            depth += 1; i += 1; m = re.match(r"\\(\*|[a-z]+)", s[i:i + 40])
            if skip is None and m and (m.group(1) == "*" or m.group(1) in RTF_SKIP): skip = depth
        elif c == "}":
            if skip == depth: skip = None
            depth -= 1; i += 1
        elif c == "\\":
            m = re.match(r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\(.)", s[i:], re.S)
            if not m: i += 1; continue
            i += m.end()
            if skip is not None: continue
            w, n, hx, ch = m.groups()
            if hx: out.append(bytes.fromhex(hx).decode("cp1252", "ignore"))
            elif w in ("par", "line", "row"): out.append("\n")
            elif w in ("tab", "cell"): out.append("\t")
            elif w == "u" and n: out.append(chr(int(n) % 65536)); i += 1
            elif ch in ("\\", "{", "}"): out.append(ch)
        else:
            if skip is None and c not in "\r\n": out.append(c)
            i += 1
    return "".join(out)

def odt_text(data):
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("content.xml"))
    T, TB = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}", "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
    out = []
    def walk(e):
        if e.tag in (T + "p", T + "h"): out.append("".join(e.itertext()))
        elif e.tag == TB + "table-row":
            cells = ["".join(c.itertext()).strip() for c in e if c.tag == TB + "table-cell"]
            out.append(": ".join(cells) if len(cells) == 2 else " | ".join(cells))
        else:
            for ch in e: walk(ch)
    walk(root); return "\n".join(out)

def xlsx_text(data):
    z = zipfile.ZipFile(io.BytesIO(data)); M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    ss = ["".join(t.text or "" for t in si.iter(M + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(M + "si")] if "xl/sharedStrings.xml" in z.namelist() else []
    out = []
    for n in sorted(x for x in z.namelist() if x.startswith("xl/worksheets/sheet")):
        for row in ET.fromstring(z.read(n)).iter(M + "row"):
            vals = []
            for c in row.iter(M + "c"):
                v, t = c.find(M + "v"), c.get("t")
                if t == "s" and v is not None: vals.append(ss[int(v.text)])
                elif t == "inlineStr": vals.append("".join(x.text or "" for x in c.iter(M + "t")))
                elif v is not None: vals.append(v.text or "")
            vals = [x.strip() for x in vals if x and x.strip()]
            if vals: out.append(": ".join(vals) if len(vals) == 2 else " | ".join(vals))
    return "\n".join(out)

def html_text(data):
    import html as _h
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", decode_text(data))
    s = re.sub(r"(?i)</(p|div|tr|li|h\d|table)>|<br\s*/?>", "\n", s); s = re.sub(r"(?i)</t[dh]>", "\t", s)
    return _h.unescape(re.sub(r"<[^>]+>", "", s))

def doc_text(data):
    # legacy .doc: ask LibreOffice or antiword when installed, otherwise pull the readable text out of the file (best effort)
    import subprocess, tempfile
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "in.doc"); open(p, "wb").write(data)
        for cmd in (["soffice", "--headless", "--convert-to", "txt:Text", "--outdir", td, p], ["antiword", p], ["catdoc", p]):
            if shutil.which(cmd[0]):
                try:
                    r = subprocess.run(cmd, capture_output=True, timeout=60)
                    t = open(os.path.join(td, "in.txt"), encoding="utf-8", errors="ignore").read() if cmd[0] == "soffice" and os.path.exists(os.path.join(td, "in.txt")) else r.stdout.decode("utf-8", "ignore")
                    if len(t.strip()) > 20: return t
                except Exception: pass
    runs = [x.decode("latin-1") for x in re.findall(rb"[\x20-\x7e\t\r\n]{6,}", data)] + [x.decode("utf-16le", "ignore") for x in re.findall(rb"(?:[\x20-\x7e\t\r\n]\x00){6,}", data)]
    return "\n".join(r.replace("\r", "\n") for r in runs)

def load(name, data):
    ext = kind_of(name.lower().rsplit(".", 1)[-1], data)
    d = {"img": None, "text": "", "meta": {}, "fmt": None, "ocr": None, "ocr_conf": None}
    confs, parts = [], []

    def run_ocr(im):
        t, c, e = ocr(im)
        if e is None: d["ocr_missing"] = True
        else:
            d["ocr"] = e
            if c is not None and t.strip(): confs.append(c)
        return t
    try:
        if ext in ("txt", "md", "csv"):
            parts.append(decode_text(data))
        elif ext == "docx":
            parts.append(docx_text(data))
            if len(parts[0].strip()) < 30:  # scanned pages pasted into Word
                z = zipfile.ZipFile(io.BytesIO(data))
                for n in sorted(z.namelist()):
                    if n.startswith("word/media/") and n.lower().endswith(EXTS_IMG):
                        im = Image.open(io.BytesIO(z.read(n))); im.load()
                        if d["img"] is None: d["img"] = im
                        parts.append(run_ocr(im))
        elif ext == "doc": parts.append(doc_text(data))
        elif ext == "rtf": parts.append(rtf_text(data))
        elif ext in ("odt", "ott"): parts.append(odt_text(data))
        elif ext in ("xlsx", "xlsm"): parts.append(xlsx_text(data))
        elif ext in ("html", "htm"): parts.append(html_text(data))
        elif ext == "pdf":
            if fitz:
                doc = fitz.open(stream=data, filetype="pdf"); d["meta"] = {k: v for k, v in (doc.metadata or {}).items() if v}
                d["img"] = Image.open(io.BytesIO(doc[0].get_pixmap(dpi=110).tobytes("png")))
                for i, pg in enumerate(doc):
                    t = pg.get_text()
                    if len(t.strip()) < 30 and i < 6:  # scanned page: render it and OCR it
                        t = run_ocr(Image.open(io.BytesIO(pg.get_pixmap(dpi=200).tobytes("png"))))
                    parts.append(t)
            elif PdfReader:
                r = PdfReader(io.BytesIO(data)); d["meta"] = {k.strip("/"): str(v) for k, v in (r.metadata or {}).items()}
                for i, pg in enumerate(r.pages):
                    t = pg.extract_text() or ""
                    if i == 0 or len(t.strip()) < 30:
                        try: imgs = [x.image for x in pg.images]
                        except Exception: imgs = []
                        if imgs and d["img"] is None and len(t.strip()) < 30: d["img"] = imgs[0]
                        if len(t.strip()) < 30 and i < 6: t = "\n".join(run_ocr(im) for im in imgs[:3])
                    parts.append(t)
            else:
                d["error"] = "No PDF reader installed (pip install pymupdf)"
        elif ext in EXTS_IMG or ext == "img":
            im = Image.open(io.BytesIO(data)); im.load()
            d["img"], d["fmt"] = im, im.format
            d["meta"] = {str(k): str(v)[:200] for k, v in im.info.items() if isinstance(v, (str, int, float))}
            ex = im.getexif()
            for tag, key in ((305, "Software"), (306, "DateTime"), (271, "Make"), (272, "Model")):
                if ex.get(tag): d["meta"][key] = str(ex[tag])
            parts.append(run_ocr(im))
        else:  # unknown type: accept it if it is readable text
            t = decode_text(data)
            if t and sum(ch.isprintable() or ch in "\r\n\t" for ch in t[:4000]) / len(t[:4000]) > 0.95: parts.append(t)
            else: d["error"] = f"Unsupported file type .{ext}"
    except Exception as e:
        d["error"] = f"Unreadable or corrupt file: {e}"
    t = "\n".join(parts).replace("：", ":")
    t = re.sub(r"^([^:\n\t]{2,40})\t+([^\t\n][^\n]*)$", r"\1: \2", t, flags=re.M)  # table rows: "Label<tab>value" becomes "Label: value"
    d["text"] = re.sub(r"[ \t]+", " ", t)
    if confs: d["ocr_conf"] = sum(confs) / len(confs)
    return d


KEY_ISS = re.compile(r"date\s+of\s+issue|issue\s+date|issued(?:\s+on)?|dated|w\.?e\.?f\.?", re.I)
KEY_EXP = re.compile(r"valid\s+(?:till|until|upto|up\s+to|through)|expir\w*|validity|\b(?:till|until)\b", re.I)
REF_CODE = re.compile(r"\b([A-Z]{2,6}(?:[/\-][A-Z0-9.]{1,14}){2,})\b")
AUTH_WORDS = re.compile(r"government of|department of|directorate|council|board|registrar|ministry|commission|municipal|corporation|notary|authority|university|bureau", re.I)
TO_PAT = re.compile(r"(?:this is to certify that|certified that|certify that|in favou?r of|granted to|awarded to|presented to|issued in the name of|m/s\.?)\s+([^\n,;:]{3,70})", re.I)
INST_WORDS = re.compile(r"\b(?:college|institute|university|polytechnic|school of|institution|academy)\b", re.I)

def extract_fields(text, inst=""):
    out = {}
    for k, p in PAT.items():
        m = re.search(p, text or "", re.I | re.M)
        out[k] = m.group(1).strip().strip(".,;") if m else ""
    # fallbacks for free-form documents that have no "Label: value" lines
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if not out["issue_date"]:
        for l in lines:
            if KEY_ISS.search(l) and not re.search(r"expir|valid", l, re.I) and DRX.findall(l): out["issue_date"] = DRX.findall(l)[0]; break
    if not out["expiry_date"]:
        for l in lines:
            if KEY_EXP.search(l) and DRX.findall(l): out["expiry_date"] = DRX.findall(l)[-1]; break
    if not out["ref_no"]:
        m = REF_CODE.search(text or ""); out["ref_no"] = m.group(1) if m else ""
    if not out["issuing_authority"]:
        out["issuing_authority"] = next((l for l in lines[:8] if len(l) <= 90 and AUTH_WORDS.search(l) and not re.search(r"issued to|name of", l, re.I)), "")
    if not out["issued_to"]:
        m = TO_PAT.search(text or ""); out["issued_to"] = m.group(1).strip().strip(".,;") if m else ""
    if not out["institution_name"]:
        if inst and norm(inst) in norm(text): out["institution_name"] = inst
        else: out["institution_name"] = next((l for l in lines if len(l) <= 100 and INST_WORDS.search(l) and not re.search(r"name of", l, re.I)), "")
    return out


# ---------- 2. image preprocessing and quality ----------
def gray(img):
    g = img.convert("L"); g.thumbnail((1000, 1000)); return np.asarray(g, dtype=np.float32)

def sharpness(g):
    l = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    h, w = (l.shape[0] // 64) * 64, (l.shape[1] // 64) * 64
    if not h or not w: return float(l.var())
    return float(np.percentile(l[:h, :w].reshape(h // 64, 64, w // 64, 64).var(axis=(1, 3)), 95))

def burn_score(img):
    s = img.convert("RGB"); s.thumbnail((400, 400)); a = np.asarray(s, dtype=np.float32); lum = a.mean(2)
    ch, cw = lum.shape[0] // 8, lum.shape[1] // 8
    dark = float((lum[:ch * 8, :cw * 8].reshape(8, ch, 8, cw).mean(axis=(1, 3)) < 70).mean())
    brown = float(((a[..., 0] > a[..., 1] + 8) & (a[..., 1] > a[..., 2] + 4) & (lum < 110)).mean())
    return dark, brown

def ela_ratio(img):
    rgb = img.convert("RGB"); buf = io.BytesIO(); rgb.save(buf, "JPEG", quality=90); buf.seek(0)
    d = np.asarray(ImageChops.difference(rgb, Image.open(buf)).convert("L"), dtype=np.float32)
    b = 32; v = [d[i:i + b, j:j + b].mean() for i in range(0, d.shape[0] - b, b) for j in range(0, d.shape[1] - b, b)]
    v = [x for x in v if x > 0.3]
    return float(np.percentile(v, 99) / (np.median(v) + 1e-6)) if len(v) > 20 else 0.0

def edge_ink(img):
    # content touching the image edge suggests a cut, cropped or torn document (or a dark scanner border)
    g = gray(img); h, w = g.shape; b = max(3, int(0.008 * min(h, w)))
    if np.median(g) < 140: return None, 0.0  # dark photo: covered by the damage check
    best = (None, 0.0)
    for side, band, ax in (("left", g[:, :b], 1), ("right", g[:, -b:], 1), ("top", g[:b, :], 0), ("bottom", g[-b:, :], 0)):
        ink = (band < 100).any(axis=ax); runs = int((ink[1:] & ~ink[:-1]).sum() + ink[0]); frac = float(ink.mean())
        score = max(frac, 0.1 if runs >= 3 else 0.0)
        if score > best[1]: best = (side, score)
    return best

def dhash(img):
    a = np.asarray(img.convert("L").resize((9, 8)), dtype=np.int16)
    return int("".join("1" if x else "0" for x in (a[:, 1:] > a[:, :-1]).flatten()), 2)


# ---------- 3. reference (our own records standing in for the AICTE / issuer database) ----------
def verify(ref_db, spec, fl, today):
    if not ref_db:
        return {"status": "source unavailable", "mismatches": []}, F("low", "SOURCE_UNAVAILABLE", "Reference database is empty; add records in the Reference tab")
    cand = [r for r in ref_db if r.get("doc_type") == spec["id"]]
    k = norm(fl.get("ref_no"))
    rec = next((r for r in cand if k and norm(r.get("ref_no")) == k), None)
    if not rec and cand:
        rec = max(cand, key=lambda r: sim(r.get("institution_name"), fl.get("institution_name")))
        if sim(rec.get("institution_name"), fl.get("institution_name")) < 0.6: rec = None
    if not rec:
        return {"status": "manual review required", "mismatches": []}, F("medium", "NO_REFERENCE_MATCH", "No matching record found in reference data; confirm with the issuing authority")
    mm, bad = [], {}
    for f in ("institution_name", "issuing_authority", "issued_to"):
        if rec.get(f) and not (same_name(fl.get(f), rec[f]) if f == "institution_name" else sim(fl.get(f), rec[f]) >= 0.85): mm.append(f"{f}: document '{fl.get(f) or '-'}' vs record '{rec[f]}'"); bad[f] = rec[f]
    for f in ("issue_date", "expiry_date"):
        if rec.get(f) and pdate(fl.get(f)) != pdate(rec[f]): mm.append(f"{f}: document '{fl.get(f) or '-'}' vs record '{rec[f]}'"); bad[f] = rec[f]
    if rec.get("ref_no") and norm(fl.get("ref_no")) != norm(rec["ref_no"]): mm.append(f"ref_no: document '{fl.get('ref_no') or '-'}' vs record '{rec['ref_no']}'"); bad["ref_no"] = rec["ref_no"]
    if mm: return {"status": "mismatch detected", "record_id": rec.get("id"), "mismatches": mm, "bad_fields": bad}, F("high", "REFERENCE_MISMATCH", "Document details differ from the reference record", "; ".join(mm))
    exp = pdate(rec.get("expiry_date"))
    if exp and exp < today: return {"status": "expired", "record_id": rec.get("id"), "mismatches": []}, F("info", "REFERENCE_EXPIRED", "Matches the reference record, which is itself expired")
    return {"status": "verified", "record_id": rec.get("id"), "mismatches": []}, None


# ---------- 4. per-document analysis ----------
DEFAULT_REQ = ["institution_name", "issuing_authority", "issued_to", "issue_date"]

def mark(r, k, status, detail=""):
    # record a problem against a field in the required-field check table
    for row in r["field_checks"]:
        if row["field"] == k:
            if row["status"] == "ok": row["status"], row["detail"] = status, detail
            elif detail and detail not in row["detail"]: row["detail"] = (row["detail"] + "; " + detail).strip("; ")
            return
    r["field_checks"].append({"field": k, "value": r["fields"].get(k, ""), "status": status, "detail": detail})


def analyze(name, data, spec, ref_db, today, inst=""):
    d = load(name, data); img, text, meta = d["img"], d["text"], d["meta"]; conf = d["ocr_conf"]
    fs = []; r = {"doc_id": spec["id"], "doc_name": spec["name"], "file": name, "sha256": hashlib.sha256(data).hexdigest(), "findings": fs,
                  "ocr": {"engine": d["ocr"], "confidence": None if conf is None else round(conf, 1)}, "text": text[:3000], "field_checks": []}
    if d.get("error"): fs.append(F("high", "UNREADABLE", d["error"]))

    if img is not None:  # quality, damage, tamper
        w, h = img.size; sh = sharpness(gray(img)); r["quality"] = {"resolution": f"{w}x{h}", "sharpness": round(sh, 1)}
        if sh < 80: fs.append(F("medium", "BLURRY", "Image is blurry or low contrast", f"sharpness {sh:.1f} (threshold 80)"))
        if min(w, h) < 600: fs.append(F("low", "LOW_RESOLUTION", "Resolution too low for reliable checks", f"{w}x{h}"))
        dark, brown = burn_score(img)
        if dark > 0.12 or brown > 0.06: fs.append(F("medium", "POSSIBLE_DAMAGE", "Possible burn, scorch, stain or heavy shadow", f"dark area {dark:.0%}, brown tint {brown:.0%}"))
        side, frac = edge_ink(img)
        if frac >= 0.08: fs.append(F("medium", "CUT_OR_CROPPED", "Part of the document may be cut off: content touches the edge of the image", f"{side} edge"))
        if d["fmt"] == "JPEG":
            e = ela_ratio(img)
            if e > 6: fs.append(F("medium", "ELA_ANOMALY", "Uneven compression levels, possible local edit", f"ELA peak ratio {e:.1f} (threshold 6)"))
        r["_h"] = dhash(img)

    ms = " ".join(f"{k}={v}" for k, v in meta.items()).lower()
    ai = [x for x in AI_SW if x in ms]
    if ai: fs.append(F("high", "AI_GENERATED_MARKER", "Metadata contains AI-generation markers", ", ".join(ai)))
    ed = [x for x in EDIT_SW if x in ms]
    if ed: fs.append(F("medium", "EDITING_SOFTWARE", "File was produced or edited with editing software", ", ".join(ed)))
    c = str(meta.get("creationDate") or meta.get("CreationDate") or ""); m = str(meta.get("modDate") or meta.get("ModDate") or "")
    if c and m and c[:16] != m[:16]: fs.append(F("low", "MODIFIED_AFTER_CREATION", "Modified after creation", f"created {c}, modified {m}"))

    has_text = len(text.strip()) >= 40
    if d.get("ocr_missing"): fs.append(F("medium", "NO_OCR_ENGINE", "This file needs OCR but no OCR engine is installed", "Install Tesseract with pytesseract, or run: pip install rapidocr-onnxruntime"))
    elif not has_text: fs.append(F("medium", "NO_TEXT", "Little or no text could be extracted from this file"))
    if conf is not None and conf < 60: fs.append(F("medium", "LOW_OCR_CONFIDENCE", "OCR confidence is low, so extracted values may be misread. Check them against the file", f"mean confidence {conf:.0f}%"))
    if SUSPECT.search(text): fs.append(F("medium", "SUSPICIOUS_TEXT", "Placeholder or invalid-document wording found", SUSPECT.search(text).group()))
    kw = [x.strip().lower() for x in (spec.get("keywords") or "").split(",") if x.strip()]
    if kw and has_text and not any(x in text.lower() for x in kw):
        fs.append(F("medium", "WRONG_DOCUMENT_TYPE", f"Text does not look like a '{spec['name']}'", "expected one of: " + ", ".join(kw)))

    # required-field check, driven by the field list the officials set for this document
    fl = extract_fields(text, inst); r["fields"] = fl; r["_t"] = norm(text)[:3000]
    need = [k for k in (spec.get("required_fields") or DEFAULT_REQ) if k in PAT]
    if "institution_name" not in need: need.insert(0, "institution_name")  # the name on every document is always matched
    if spec.get("has_expiry") and "expiry_date" not in need: need.append("expiry_date")
    for k in need:
        r["field_checks"].append({"field": k, "value": fl[k], "status": "ok" if fl[k] else "missing",
                                  "detail": "" if fl[k] else ("Not found in the document" if has_text else "No text could be extracted")})
    for c in spec.get("custom_fields") or []:  # extra fields added by officials, read from "Field name: value" lines
        lab = (c.get("label") or "").strip()
        if not lab or lab in fl: continue
        m = re.search(r"\s+".join(map(re.escape, lab.split())) + r"\s*[:;\-–|]\s*(.+)", text, re.I | re.M)
        v = m.group(1).strip().strip(".,;") if m else ""; fl[lab] = v; need.append(lab)
        r["field_checks"].append({"field": lab, "value": v, "status": "ok" if v else "missing", "detail": "" if v else ("Not found in the document" if has_text else "No text could be extracted")})
        pat = (c.get("pattern") or "").strip()
        if v and pat:
            try: good = re.fullmatch(pat, v)
            except re.error: good = True
            if not good: fs.append(F("medium", "INVALID_FIELD", f"'{lab}' has an unexpected format", f"{v} vs /{pat}/")); mark(r, lab, "invalid", "Does not match the expected format")
    miss = [k for k in need if not fl[k]]
    if miss and has_text: fs.append(F("medium", "MISSING_FIELDS", "Required fields not found", ", ".join(miss)))
    for k in ("issue_date", "expiry_date"):
        if fl[k] and not pdate(fl[k]):
            fs.append(F("medium", "BAD_DATE", f"Unreadable {k.replace('_', ' ')}", fl[k])); mark(r, k, "invalid", "Not a valid date")
    iss, exp = pdate(fl["issue_date"]), pdate(fl["expiry_date"])
    if iss and iss > today: fs.append(F("high", "FUTURE_ISSUE_DATE", "Issue date is in the future", str(iss))); mark(r, "issue_date", "invalid", "Date is in the future")
    if iss and exp and exp < iss: fs.append(F("high", "DATE_ORDER", "Expiry date is before issue date", f"{iss} to {exp}")); mark(r, "expiry_date", "invalid", "Expiry is before the issue date")
    if exp and exp < today: fs.append(F("high", "EXPIRED", "Document has expired", f"expired on {exp}")); mark(r, "expiry_date", "expired", f"Expired on {exp}")
    elif exp and (exp - today).days <= 30: fs.append(F("low", "EXPIRING_SOON", "Expires within 30 days", str(exp)))
    if spec.get("ref_pattern") and fl["ref_no"]:
        try: ok = re.fullmatch(spec["ref_pattern"], fl["ref_no"])
        except re.error: ok = True
        if not ok: fs.append(F("medium", "BAD_REF_FORMAT", "Reference number does not match the expected format", f"{fl['ref_no']} vs /{spec['ref_pattern']}/")); mark(r, "ref_no", "invalid", "Does not match the expected format")

    r["reference"], rf = verify(ref_db, spec, fl, today)
    if rf: fs.append(rf)
    for k, rv in r["reference"].get("bad_fields", {}).items(): mark(r, k, "mismatch", f"Original record has '{rv}'")
    return r


def finish(r):
    r["risk"] = min(100, sum(W[f["severity"]] for f in r["findings"]))
    sev = {f["severity"] for f in r["findings"]}
    r["verdict"] = "FLAGGED" if "high" in sev or r["risk"] >= 50 else "REVIEW" if sev - {"info"} else "VERIFIED"
    r.pop("_h", None); r.pop("_t", None)


# ---------- 5. whole-application run with cross-document checks ----------
def run(docs, files, inst, ref_db, seen, today=None):
    today = today or dt.date.today(); res = []
    for spec in docs:
        f = files.get(spec["id"])
        if f: res.append(analyze(f[0], f[1], spec, ref_db, today, inst))
        elif spec.get("required", True):
            res.append({"doc_id": spec["id"], "doc_name": spec["name"], "file": None, "fields": {}, "findings": [F("high", "MISSING_DOC", "Required document was not uploaded")]})
        else:
            res.append({"doc_id": spec["id"], "doc_name": spec["name"], "file": None, "fields": {}, "findings": [F("info", "NOT_SUBMITTED", "Optional document not uploaded")]})
    up = [r for r in res if r.get("file")]
    base = inst or next((r["fields"]["institution_name"] for r in up if r["fields"].get("institution_name")), "")
    for r in up:
        n = r["fields"].get("institution_name")
        if base and n and not same_name(n, base): r["findings"].append(F("high", "INSTITUTION_MISMATCH", "Institution name differs from the application", f"'{n}' vs '{base}'")); mark(r, "institution_name", "mismatch", f"Application says '{base}'")
        p = seen.get(r["sha256"])
        if p: r["findings"].append(F("medium" if norm(p["inst"]) != norm(base) else "info", "PREVIOUSLY_SEEN", "Identical file was submitted before", f"earlier institution '{p['inst']}' on {p['on']}"))
        seen[r["sha256"]] = {"inst": base, "doc": r["doc_id"], "on": today.isoformat()}
    for i, a in enumerate(up):
        for b in up[i + 1:]:
            why = None
            if a["sha256"] == b["sha256"]: why = ("high", "identical file")
            elif "_h" in a and "_h" in b and bin(a["_h"] ^ b["_h"]).count("1") <= 4: why = ("medium", "visually near-identical image")
            elif len(a.get("_t", "")) > 80 and difflib.SequenceMatcher(None, a["_t"], b["_t"]).quick_ratio() > 0.92 and difflib.SequenceMatcher(None, a["_t"], b["_t"]).ratio() > 0.92: why = ("medium", "near-identical text")
            if why:
                a["findings"].append(F(why[0], "DUPLICATE_DOCUMENT", f"Same content as '{b['doc_name']}'", why[1]))
                b["findings"].append(F(why[0], "DUPLICATE_DOCUMENT", f"Same content as '{a['doc_name']}'", why[1]))
    for r in res:
        r["sha256"] = r.get("sha256", "")[:16]; finish(r)
        if not r["file"]: r["verdict"] = "MISSING" if r["findings"][0]["code"] == "MISSING_DOC" else "OPTIONAL"; r["risk"] = 100 if r["verdict"] == "MISSING" else 0
    summary = {}
    for r in res: summary[r["verdict"]] = summary.get(r["verdict"], 0) + 1
    return {"documents": res, "summary": summary, "institution_used": base}


# ---------- 6. automatic decision by the AI model ----------
INCONCLUSIVE = {"NO_REFERENCE_MATCH", "SOURCE_UNAVAILABLE", "NO_OCR_ENGINE"}  # not the institution's fault: an official confirms these

def ai_gate(out):
    # An application passes only if no document has a high or medium problem (low-severity notes are passed to the officials).
    reasons = []
    for r in out["documents"]:
        bad = [f for f in r["findings"] if f["severity"] in ("high", "medium") and f["code"] not in INCONCLUSIVE]
        if bad: reasons.append(f"{r['doc_name']}: " + "; ".join(f["message"] + (f" ({f['evidence']})" if f["evidence"] else "") for f in bad))
    return not reasons, reasons
