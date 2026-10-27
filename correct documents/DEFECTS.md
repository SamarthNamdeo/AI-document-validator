# Defects planted in the incorrect files

Each incorrect file is the matching correct file with the changes below. 'Validator output' is what the prototype reported when run against the original records.

## 01_affidavit_incorrect.txt (Affidavit / Undertaking)

- **Reference No** changed: `AFF/BPL/2026/1187` to `AFF/BPL/2027/0001`
- **Name of Signatory** changed: `Dr. Rakesh Mehta, Director` to `Mr. Suresh Gupta, Trustee`
- **Date of Issue** changed: `10/09/2026` to `15/03/2027`

Validator output: **FLAGGED**, source check: mismatch detected
- `FUTURE_ISSUE_DATE`: Issue date is in the future (2027-03-15)
- `REFERENCE_MISMATCH`: Document details differ from the reference record (issued_to: document 'Mr. Suresh Gupta, Trustee' vs record 'Dr. Rakesh Mehta, Director'; issue_date: document '15/03/2027' vs record '10/09/2026'; ref_no: document 'AFF/BPL/2027/0001' vs record 'AFF/BPL/2026/1187')

## 02_nba_certificate_incorrect.txt (NBA / NAAC Accreditation Certificate)

- **Certificate No** changed: `NBA/2023/ACC/4471` to `NBA/2017/ACC/1203`
- **Date of Issue** changed: `01/07/2023` to `01/07/2017`
- **Valid up to** changed: `30/06/2029` to `30/06/2023`

Validator output: **FLAGGED**, source check: mismatch detected
- `EXPIRED`: Document has expired (expired on 2023-06-30)
- `REFERENCE_MISMATCH`: Document details differ from the reference record (issue_date: document '01/07/2017' vs record '01/07/2023'; expiry_date: document '30/06/2023' vs record '30/06/2029'; ref_no: document 'NBA/2017/ACC/1203' vs record 'NBA/2023/ACC/4471')

## 03_fire_safety_noc_incorrect.txt (Fire Safety NOC)

- **Certificate No** changed: `FS/BPL/2025/0823` to `FS/BPL/2025/8023`
- **Valid up to** changed: `14/05/2028` to `14/05/2024`

Validator output: **FLAGGED**, source check: mismatch detected
- `DATE_ORDER`: Expiry date is before issue date (2025-05-15 to 2024-05-14)
- `EXPIRED`: Document has expired (expired on 2024-05-14)
- `REFERENCE_MISMATCH`: Document details differ from the reference record (expiry_date: document '14/05/2024' vs record '14/05/2028'; ref_no: document 'FS/BPL/2025/8023' vs record 'FS/BPL/2025/0823')

## 04_trust_registration_certificate_incorrect.txt (Society / Trust Registration Certificate)

- **Registration No** changed: `TR/BPL/1994/2210` to `TR/MUM/1994/9981`
- **Name of Institution** changed: `LNCT Group of Colleges, Bhopal` to `Lakshmi Narayan Public School, Bhopal`
- **Issued by** changed: `Registrar of Public Trusts, Bhopal` to `Registrar of Companies, Mumbai`

Validator output: **FLAGGED**, source check: manual review required
- `NO_REFERENCE_MATCH`: No matching record found in reference data; confirm with the issuing authority
- `INSTITUTION_MISMATCH`: Institution name differs from the application ('Lakshmi Narayan Public School, Bhopal' vs 'LNCT Group of Colleges, Bhopal')

## 05_state_government_certificate_incorrect.txt (State Government NOC / Essentiality Certificate)

- **Issued by** removed (was `Department of Technical Education, Government of Madhya Pradesh`)
- **Date of Issue** changed: `18/09/2026` to `[insert date]`
- **Body text** changed: `DRAFT. Subject to approval of the competent authority. The State Government has no objection to the continuation of technical programmes at the institution.`

Validator output: **FLAGGED**, source check: mismatch detected
- `SUSPICIOUS_TEXT`: Placeholder or invalid-document wording found ([insert)
- `MISSING_FIELDS`: Required fields not found (issuing_authority)
- `BAD_DATE`: Unreadable issue date ([insert date])
- `REFERENCE_MISMATCH`: Document details differ from the reference record (issuing_authority: document '-' vs record 'Department of Technical Education, Government of Madhya Pradesh'; issue_date: document '[insert date]' vs record '18/09/2026')

## 06_ter_payment_receipt_incorrect.txt (TER Payment Receipt)

- **Reference No** changed: `TER/2026-27/BPL/008845` to `TER/2026-27/BPL/008854`
- **Issued to** changed: `Dr. Rakesh Mehta, Director` to `Mr. Suresh Gupta, Trustee`
- **Date of Issue** changed: `05/10/2026` to `31/02/2026`

Validator output: **FLAGGED**, source check: mismatch detected
- `BAD_DATE`: Unreadable issue date (31/02/2026)
- `REFERENCE_MISMATCH`: Document details differ from the reference record (issued_to: document 'Mr. Suresh Gupta, Trustee' vs record 'Dr. Rakesh Mehta, Director'; issue_date: document '31/02/2026' vs record '05/10/2026'; ref_no: document 'TER/2026-27/BPL/008854' vs record 'TER/2026-27/BPL/008845')

## 07_previous_eoa_letter_incorrect.txt (Previous EoA Letter)

- **Issued by** changed: `All India Council for Technical Education, New Delhi` to `State Technical Board, Bhopal`
- **Date of Issue** changed: `20/05/2026` to `20/07/2024`
- **Valid up to** changed: `30/06/2027` to `30/06/2025`

Validator output: **FLAGGED**, source check: mismatch detected
- `EXPIRED`: Document has expired (expired on 2025-06-30)
- `REFERENCE_MISMATCH`: Document details differ from the reference record (issuing_authority: document 'State Technical Board, Bhopal' vs record 'All India Council for Technical Education, New Delhi'; issue_date: document '20/07/2024' vs record '20/05/2026'; expiry_date: document '30/06/2025' vs record '30/06/2027')

