# AICTE document validator (SIH 2026 prototype)

## Run
Windows: double-click `start.bat`. Mac/Linux: `./start.sh`. Both create a virtual environment, install everything (including the OCR engine) and start the server.
Or by hand:
    pip install -r requirements.txt
    uvicorn main:app --reload
Pages: http://localhost:8000 (institution), http://localhost:8000/track.html (track an application), http://localhost:8000/officials.html (AICTE officials), http://localhost:8000/docs (API docs).

## Two pages
- Institution page: choose application type, upload the listed documents, verify. Each submission is stored as an application.
- Officials page: list of applied institutions; select one to see its name and uploaded documents, findings and source checks (with a link to each uploaded file).
  "Original documents" tab: upload an original AICTE-issued document for an institution, check the fields read from it, save. Then press
  "Re-check against records" on an application to compare its documents with the new originals. The Checklists tab edits the document list; the Audit trail tab shows every action.
- At the bottom of each application, officials can mark all uploaded documents as verified, or reject them with an optional reason. The decision is shown on the documents and in the applications list, and recorded in the audit trail.
- There is no login in this prototype; role-based access would protect the officials page in production.

## Try it
As an institution, choose "Extension of Approval (EoA)", enter the institution name "Sunrise Institute of Technology, Indore", upload `samples/fire_noc_ok.txt`
(verified against the seeded reference record) or `samples/fire_noc_expired.txt` (expired, and its numbers and dates differ from the reference record). Real PDFs/JPG/PNG work too;
scans and photos need an OCR engine (see above).

## Text extraction (OCR)
| File | How text is read |
|---|---|
| PDF with a text layer | read directly (PyMuPDF, or pypdf if PyMuPDF is missing) |
| Scanned PDF | pages rendered and OCR'd (PyMuPDF), or embedded page images OCR'd (pypdf) |
| JPG, PNG, TIFF, BMP, WEBP | OCR after preprocessing (orientation fix, grayscale, contrast, resize, sharpen) |
| DOCX | paragraphs and tables parsed (two-column table rows become "label: value"); scanned pages inside Word are OCR'd |
| TXT | read directly |
Old `.doc` files must be saved as `.docx` or PDF. OCR engine: RapidOCR is installed by `requirements.txt` (pip only, models included, no separate program). Tesseract is used first when present (auto-detected, including the default Windows folder). Both pages show which engine is active; if it says none was found, run the install command again and restart the server.
Every result shows the extracted text, the OCR engine and its mean confidence; low confidence raises `LOW_OCR_CONFIDENCE`.

### Any document type
Files are recognised by their contents, not just the extension. Readable: PDF (text or scanned), images (JPG, PNG, TIFF, BMP, WEBP, GIF), Word (.docx; .doc through LibreOffice or antiword when installed, otherwise a best-effort text pull),
RTF, ODT, Excel (.xlsx), HTML, CSV and plain text, including UTF-16 text. Sideways or upside-down scans are rotated automatically. Fields are read from "Label: value" lines, table rows and, when those are absent,
from ordinary sentences (for example "dated 18/09/2026", "valid up to 30 June 2029", "This is to certify that ...", codes such as DTE/MP/EC/2026/0539, an issuing office in the first lines).
Free-form extraction is a convenience: officials should still check the extracted values shown on each card.

## Required-field validation
Officials choose, per document, which fields must be present and valid (Officials page, Checklists tab): institution name, issuing authority, issued to,
issue date, expiry date, reference no. Each uploaded document gets a field-by-field table: OK, missing, invalid (unreadable date, future date, expiry before issue,
bad reference format), expired, or mismatch (differs from the application or the original record). The same tab holds keywords that detect the wrong document in a slot.

## Submission flow: AI check first, officials second
1. The institution enters its name (required) and uploads every required document. The Verify button stays off until both are done; the page says what is still missing, and the server enforces the same rules.
2. The application is saved and the AI model checks every document in the background: institution name on each document against the name entered, edited (editing software, compression anomalies), AI-generated
   (metadata markers), burned or stained, cut or cropped, blurry, wrong document in the slot, expiry, required fields, duplicates, and comparison with the original records.
3. Any high or medium problem means the model rejects the application itself. It never reaches the officials; the institution sees the reasons on the page and on the Track page. Documents that cannot be compared
   because no original record is on file (or no OCR engine is installed) are not counted against the institution: they go to the officials marked "manual review required". Low-severity notes (for example "expires within 30 days") also go to the officials.
4. If every document passes, the application appears on the Officials page as "pending verification". Officials verify or reject it (with an optional reason).
Track page statuses: Application submitted, AI verification (in progress, passed or rejected by the AI model), Pending verification (with the officials), then Verified and accepted or Rejected.
The institution name matches a document when the texts are near-identical or one is a long part of the other ("LNCT Group of Colleges" matches "LNCT Group of Colleges, Bhopal"; "...Indore" does not).

## Flow
upload -> extraction (PDF text / OCR) -> preprocessing (grayscale, resize, normalised text) -> checks -> reference comparison -> verdict per document.

## Checks
Blur, low resolution, burn/stain/shadow heuristic, JPEG error-level analysis, editing-software and AI-generator metadata, modified-after-creation,
placeholder wording, missing fields, unreadable/future/out-of-order dates, expiry, reference-number format, institution consistency,
duplicates (SHA-256, perceptual hash, text similarity, previous submissions), comparison with reference records.

## APIs
GET/PUT /api/checklists, GET/POST/DELETE /api/reference, POST /api/validate (multipart: application_type, institution_name, f__<doc_id>), GET /api/audit.

## Limits
All results are advisory indicators for AICTE officials, not proof of forgery. AI-image detection here is metadata/heuristic based; a trained
classifier would plug into `analyze()`. Real issuer verification (APIs, QR, digital signatures) would replace `verify()`.
Delete `data/seen.json` to reset the previously-seen-file memory.

## Officials' decision
At the bottom of an application on the Officials page: "Mark all documents as verified", or "Reject documents" with an optional reason typed beside it. Documents then carry an
official badge, the application list shows the decision, and each action is written to the audit trail. A warning appears before verifying an application that still has flagged,
review or missing documents. The decision stays when an application is re-checked; it can be changed by deciding again.

## Track your application (institution)
`/track.html`: the institution enters its Application ID (shown after submitting; also remembered in this browser) and sees the current status (Under verification, Verified and accepted,
or Rejected with the reason typed by the official), the date and time of application, the date and time of verification or rejection, and the documents it uploaded, each with an Open link.
There is no login in this prototype: the Application ID acts as the key. A real deployment would require the institution to sign in.

## Checklists: extra fields
In the Checklists tab each document opens as a card. Besides the six standard fields, officials can add any number of additional fields (a name such as "Approved intake" and an optional allowed
format as a regular expression). The checker looks for a line written as `Field name: value`, reports it as OK, missing or invalid in the field-by-field table, and shows it on the institution's slot list.
Additional fields are checked for presence and format; they are not compared with the original record.

## Audit trail
The Audit trail tab lists actions in plain language with date and time, filters (applications, decisions, original records, checklist changes) and search by institution, application ID or document.
Submissions and re-checks expand into a document-by-document table with the problems found.
