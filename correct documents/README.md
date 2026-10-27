# LNCT Group of Colleges, Bhopal: test documents

Synthetic documents for the AICTE document validator prototype (application type: Extension of Approval (EoA)).
`correct/` holds one valid document per type; `incorrect/` holds a flawed version of each. All are plain `.txt` files, so no OCR is needed.

## How to test
1. Institution page: choose "Extension of Approval (EoA)", enter institution name `LNCT Group of Colleges, Bhopal`.
2. Load the originals first, otherwise correct files show "manual review required". Either:
   - Officials page, Original documents tab: for each file in `original_documents/`, set institution to `LNCT Group of Colleges, Bhopal`, pick the document type below, choose the file (its fields fill in automatically), then Save; or
   - merge `reference_records_LNCT.json` into `aicte-doc-validator/data/reference.json`.

   | Original file | Document type to select |
   |---|---|
| 01_affidavit_original.txt | Affidavit / Undertaking |
| 02_nba_certificate_original.txt | NBA / NAAC Accreditation Certificate |
| 03_fire_safety_noc_original.txt | Fire Safety NOC |
| 04_trust_registration_certificate_original.txt | Society / Trust Registration Certificate |
| 05_state_government_certificate_original.txt | State Government NOC / Essentiality Certificate |
| 06_ter_payment_receipt_original.txt | TER Payment Receipt |
| 07_previous_eoa_letter_original.txt | Previous EoA Letter |

3. Upload the 7 files from `correct/` in checklist order, then verify: all should be VERIFIED.
4. Repeat with `incorrect/`: each should be FLAGGED or REVIEW with the findings below (on the officials page, use "Re-check against records" after adding originals).

The exact changes made in each incorrect file are listed in `DEFECTS.md`.

## Expected result for the incorrect set
| File | Verdict | Findings raised |
|---|---|---|
| 01_affidavit_incorrect.txt | FLAGGED | FUTURE_ISSUE_DATE, REFERENCE_MISMATCH |
| 02_nba_certificate_incorrect.txt | FLAGGED | EXPIRED, REFERENCE_MISMATCH |
| 03_fire_safety_noc_incorrect.txt | FLAGGED | DATE_ORDER, EXPIRED, REFERENCE_MISMATCH |
| 04_trust_registration_certificate_incorrect.txt | FLAGGED | NO_REFERENCE_MATCH, INSTITUTION_MISMATCH |
| 05_state_government_certificate_incorrect.txt | FLAGGED | SUSPICIOUS_TEXT, MISSING_FIELDS, BAD_DATE, REFERENCE_MISMATCH |
| 06_ter_payment_receipt_incorrect.txt | FLAGGED | BAD_DATE, REFERENCE_MISMATCH |
| 07_previous_eoa_letter_incorrect.txt | FLAGGED | EXPIRED, REFERENCE_MISMATCH |

## Notes
- Dates are set so the correct files are valid on 24 Oct 2026. The EoA letter expires 30/06/2027; edit dates if you test later.
- Duplicate check: upload one file in two slots. Blur, burn and edit/AI-metadata checks apply to images and PDFs (take a photo or export a PDF of any file).
- Authority names are used only to look realistic; nothing here is a real certificate.

## Other formats and image defects (`other_formats/`)
Fire Safety NOC in many forms. Correct versions come out VERIFIED: `.docx`, `.pdf`, `.png`, `_scanned.pdf`, `.rtf`, `.odt`, `.xlsx`, `.html`. Incorrect versions (`..._incorrect.docx/.pdf/.png/_scanned.pdf`) are rejected with the same findings as the `.txt` pair.
Image defects, all made from the correct PNG (use them in the Fire Safety NOC slot; the AI check rejects the application):
| File | Defect | Finding |
|---|---|---|
| `..._correct_blurry.png` | blurred scan | BLURRY, LOW_OCR_CONFIDENCE and unreadable fields |
| `..._correct_burned.png` | dark burn marks | POSSIBLE_DAMAGE, CUT_OR_CROPPED |
| `..._correct_cut.png` | right part of the page cut off | CUT_OR_CROPPED |
| `..._correct_edited_photoshop.jpg` | saved by Adobe Photoshop | EDITING_SOFTWARE |
| `..._correct_ai_generated.png` | Midjourney marker in the file | AI_GENERATED_MARKER |
Wrong document: upload `correct/06_ter_payment_receipt_correct.txt` in the Fire Safety NOC slot (with the rest of the correct set) to see WRONG_DOCUMENT_TYPE.
Name check: change the institution name you type (for example to "LNCT Group of Colleges, Indore") to see every document flagged for a different institution name.
