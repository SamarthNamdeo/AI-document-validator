const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const api = async (u, o) => { const r = await fetch(u, o); if (!r.ok) { let t = await r.text(); try { t = JSON.parse(t).detail || t } catch (e) {} throw new Error(t) } return r.json() };
const post = (u, b, m = 'POST') => api(u, {method: m, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(b)});
const vb = v => `<span class="v ${v}">${v}</span>`;
const counts = s => Object.entries(s).map(([k, v]) => `${vb(k)} ${v}`).join(' &nbsp; ');
const ACCEPT = '.pdf,.jpg,.jpeg,.png,.tif,.tiff,.bmp,.webp,.gif,.docx,.doc,.rtf,.odt,.xlsx,.csv,.html,.htm,.txt';
const FL = {institution_name: 'Institution name', issuing_authority: 'Issuing authority', issued_to: 'Issued to (person)', issue_date: 'Issue date', expiry_date: 'Expiry date', ref_no: 'Reference no.'};
const DEF = ['institution_name', 'issuing_authority', 'issued_to', 'issue_date'];

async function ocrStatus() {
  try {
    const o = (await api('/api/status')).ocr, e = o.tesseract ? 'Tesseract' : o.rapidocr ? 'RapidOCR' : null;
    if ($('#ocr')) $('#ocr').innerHTML = e ? `OCR engine ready: ${e}. PDFs, images and Word files are read automatically.` : '<span class="err">No OCR engine found.</span> Run <code>pip install -r requirements.txt</code> (or start.bat / start.sh), which installs RapidOCR, then restart the server. Text, Word and text-PDF files work meanwhile.';
  } catch (e) {}
}

// One card per document: verdict, required-field check, extracted fields, source check, findings, extracted text.
// aid adds a link to the uploaded file (officials page).
function docCard(d, aid, official) {
  const how = d.ocr && d.ocr.engine ? `OCR (${d.ocr.engine}${d.ocr.confidence != null ? ', confidence ' + d.ocr.confidence + '%' : ''})` : 'read from the file text';
  const off = official ? `<span class="v ${official}">${official === 'VERIFIED' ? 'Verified' : 'Rejected'} by officials</span>` : '';
  const fc = (d.field_checks || []).length ? `<table><tr><th>Required field</th><th>Value found</th><th>Check</th></tr>${d.field_checks.map(c => `<tr><td>${esc(FL[c.field] || c.field)}</td><td>${c.value ? esc(c.value) : '<i class="m">not found</i>'}</td>
    <td><b class="s-${c.status}">${c.status === 'ok' ? 'OK' : c.status}</b>${c.detail ? `<div class="m">${esc(c.detail)}</div>` : ''}</td></tr>`).join('')}</table>` : '';
  const body = d.file ? `<div class="m">${esc(d.file)}, sha256 ${d.sha256}${d.quality ? `, ${d.quality.resolution}, sharpness ${d.quality.sharpness}` : ''}. Text ${how}.
    ${aid ? ` &nbsp; <a href="/api/applications/${aid}/file/${d.doc_id}" target="_blank" rel="noopener">Open uploaded file</a>` : ''}</div>${fc}
    <table class="kv">${Object.entries(d.fields).map(([k, v]) => `<tr><td>${k.replace(/_/g, ' ')}</td><td>${v ? esc(v) : '<i class="m">not found</i>'}</td></tr>`).join('')}
    <tr><td>Source check</td><td><b>${esc(d.reference.status)}</b>${d.reference.mismatches.map(x => `<div class="m">${esc(x)}</div>`).join('')}</td></tr></table>` : '';
  return `<div class="card"><div class="row"><h3 style="margin:0">${esc(d.doc_name)}</h3>${vb(d.verdict)}${off}<span class="m">risk ${d.risk}/100</span></div>${body}
    <ul class="f">${d.findings.map(f => `<li class="${f.severity}"><b>${f.code}</b> · ${esc(f.message)}${f.evidence ? `<div class="m">${esc(f.evidence)}</div>` : ''}</li>`).join('')}${d.file && !d.findings.length ? '<li class="info">No anomalies found</li>' : ''}</ul>
    ${d.text ? `<details><summary>Extracted text</summary><pre>${esc(d.text)}</pre></details>` : ''}</div>`;
}

const fmtDT = s => s ? new Date(s).toLocaleString('en-IN', {day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true}) : '';
const VW = {VERIFIED: 'look fine', REVIEW: 'need review', FLAGGED: 'flagged', MISSING: 'missing', OPTIONAL: 'optional, not uploaded'};
const CODE_TEXT = {EXPIRED: 'Document has expired', MISSING_FIELDS: 'Required details missing', MISSING_DOC: 'Required document not uploaded', NOT_SUBMITTED: 'Optional document not uploaded',
  REFERENCE_MISMATCH: 'Details differ from the original record', NO_REFERENCE_MATCH: 'No original record found to compare with', SOURCE_UNAVAILABLE: 'No original records available yet',
  REFERENCE_EXPIRED: 'The original record itself has expired', INSTITUTION_MISMATCH: 'Institution name differs from the application', DUPLICATE_DOCUMENT: 'Same content as another uploaded document',
  PREVIOUSLY_SEEN: 'This file was submitted before', BAD_DATE: 'A date could not be read', FUTURE_ISSUE_DATE: 'Issue date is in the future', DATE_ORDER: 'Expiry date is before the issue date',
  EXPIRING_SOON: 'Expires within 30 days', BAD_REF_FORMAT: 'Reference number is in the wrong format', INVALID_FIELD: 'A field has an invalid value', WRONG_DOCUMENT_TYPE: 'Does not look like the right document',
  SUSPICIOUS_TEXT: 'Contains draft or placeholder wording', BLURRY: 'Image is blurry', CUT_OR_CROPPED: 'Part of the document appears cut off or cropped', LOW_RESOLUTION: 'Resolution is too low', POSSIBLE_DAMAGE: 'Possible burn, stain or damage',
  ELA_ANOMALY: 'Possible edit inside the image', AI_GENERATED_MARKER: 'File carries AI-generation markers', EDITING_SOFTWARE: 'Made or edited with editing software',
  MODIFIED_AFTER_CREATION: 'Changed after it was created', NO_TEXT: 'No readable text', NO_OCR_ENGINE: 'Scan could not be read (no OCR engine)', LOW_OCR_CONFIDENCE: 'Scan quality is low, text may be misread', UNREADABLE: 'File could not be opened'};
