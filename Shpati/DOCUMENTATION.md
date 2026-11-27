# Shpati — Creation Documentation

How Shpati was built: what came from **Lerdi**, what came from **TrustLab**, what was improved, and how the product evolved into its current OCR-first form.

---

## 1. Why Shpati exists

Two existing projects solved related problems differently:

| Project | Path | Strength | Gap |
|---------|------|----------|-----|
| **Lerdi** (LabScan) | `Desktop/Repos/Lerdi` | Durable report library, reliable RapidOCR, polished React UI | Shallower clinical safety / review gating |
| **TrustLab** | `Desktop/Repos/TrustLab-main_Behare` | Multi-stage clinical pipeline, validation tiers, human review | Stateless uploads, weaker product shell |

**Shpati** was created to unify them into one local lab-report digitizer:

- Lerdi’s **product shell** (storage, OCR reliability, UI, Vite proxy)
- TrustLab’s **clinical safety engine** (staged pipeline, acceptance tiers, review API)

Over successive iterations, Shpati was also simplified toward an **OCR-first viewer** so every detected text line is visible and trustworthy before clinical interpretation is re-enabled.

---

## 2. Source systems in detail

### 2.1 Lerdi (LabScan)

**Purpose:** Local-first OCR → LOINC → FHIR digitizer with a multi-page React app.

**Stack:** Python ≥3.12, FastAPI, RapidOCR, OpenCV · React 19, Vite 6, Tailwind 4  
**Ports:** backend `8000`, frontend `3000`

**Architecture highlights:**

- No database — files under `uploaded_reports/` and `outputs/<report_id>/`
- `ReportStore` lists and loads reports by slugified ID
- RapidOCR run across an OpenCV **variant matrix** (original / deskew / denoise / threshold); pick best by line count + confidence
- ~4 pipeline stages: OCR → parse → normalize → FHIR
- Vite proxies `/api` and `/media` to the backend (no CORS pain in local dev)
- Rich UI: Dashboard, Upload, Review tabs (Vision / Mapping / FHIR / JSON)

### 2.2 TrustLab

**Purpose:** Trust-aware clinical digitizer that surfaces uncertainty instead of hiding it.

**Stack:** FastAPI, OpenCV, RapidOCR (originally PaddleOCR), pdf2image · React 18, Vite  
**Ports (local):** backend often `8001` (to avoid Lerdi), frontend `5173`

**Architecture highlights:**

- Stateless process-per-upload (no durable report library)
- ~9–10 single-responsibility stages: ingest → preprocess → OCR → layout → parse → extract → map → standardize → validate → FHIR
- Three-tier outcomes: **`accepted` / `needs_review` / `rejected`**
- Human review API: create session → apply approve/edit/reject → finalize FHIR
- Conservative FHIR (accepted rows only by default)
- PDF support via `pdf2image`
- Explicit `rejected_rows` and validation flags for auditability

---

## 3. What was combined into Shpati

### 3.1 From Lerdi (product shell)

| Capability | Where in Shpati |
|------------|-----------------|
| Folder-per-report storage | `storage/uploaded_reports/`, `storage/outputs/{report_id}/` |
| `ReportStore` pattern | `backend/src/core/report_store.py` |
| RapidOCR + variant matrix | `backend/src/pipeline/s2_preprocess.py`, `s3_ocr.py` |
| Vite `/api` + `/media` proxy | `frontend/vite.config.ts` |
| Multi-route React app | Dashboard, Upload, All Reports, Inspector |
| Overlay / digital / original canvas | `DigitalReportCanvas.tsx` |
| OCR observation list + thumbnails | `OcrObservationsList.tsx`, `OcrLineThumbnail.tsx` |
| Packaged Python project | `pyproject.toml`, `shpati-api` entrypoint |
| LabScan-style status markers | `LabScanStatusMarker.tsx` (clinical UI leftover) |

### 3.2 From TrustLab (clinical safety engine)

| Capability | Where in Shpati |
|------------|-----------------|
| Staged pipeline modules `s1`–`s11` | `backend/src/pipeline/` |
| Layout zoning | `s4_layout.py` |
| Lab-row parser | `s5_parser.py` |
| Extraction glue | `s6_extraction.py` |
| LOINC mapping | `s7_mapper.py` + `data/loinc_catalog.json` |
| Unit standardization | `s8_standardizer.py` |
| 3-tier validation | `s9_validator.py` |
| FHIR export | `s10_fhir.py` |
| Clinical report filtering | `s11_clinical_report.py` |
| Human review service | `core/review_service.py` |
| PDF ingestion | `s2_preprocess.py` (`pdf2image`) |
| Interactive review workbench UI | `InteractiveWorkbench.tsx` (present; APIs not currently wired) |

### 3.3 Explicit non-adoptions

| Not taken | Why |
|-----------|-----|
| TrustLab’s **stateless-only** uploads | Replaced by Lerdi-style durable `ReportStore` |
| TrustLab’s **direct API base URL / port 5173** | Replaced by Vite proxy; frontend on **3001** |
| TrustLab’s **PaddleOCR-as-default** | RapidOCR path (more reliable on macOS) |
| Lerdi’s **export-all-mapped FHIR** | Prefer TrustLab’s accepted-only / review-gated model when clinical path is active |
| Running both products on port **3000** | Shpati frontend uses **3001** so Lerdi can stay on 3000 |

---

## 4. What Shpati improved (beyond either parent)

These were built specifically for Shpati, not copied as-is.

### 4.1 Unified product identity

- Single installable package (`shpati`) with one backend + one frontend
- Shared storage root under `Shpati/storage/`
- Consistent naming: report IDs, artifact files, API under `/api`

### 4.2 Digital report reproduction (`s6b`)

New stage that neither parent exposed the same way:

- Saves page dimensions + every OCR line with bounding boxes
- Powers the **Text only** canvas that visually reconstructs the scan from OCR text alone
- Artifact: `digital_report.json`

### 4.3 OCR-first report inspector

The Report view was redesigned so users see **everything OCR detected**, not only parser-accepted lab rows:

- Positioned digital canvas (overlay / text only / original)
- Full OCR line list with confidence
- Plain-text dump of all lines
- Raw JSON tab for `ocr.json` and `digital_report.json`

This fixed a major usability issue: clinical filtering had been hiding most of what OCR actually caught.

### 4.4 Parser robustness (when clinical path is enabled)

In `s5_parser.py`, dual-range lines like:

```text
PUS CELLS-URINE 2-4 /HPF 0-5
```

were previously misread (e.g. value becoming `-4`). Shpati added dual-range parsing and unit tests in `backend/tests/test_parser_ranges.py`.

### 4.5 Clinical report layer (`s11`)

When the full pipeline was active, Shpati added:

- Admin/hospital/doctor noise filtering
- High / low / normal interpretation inference
- LabScan-style square status markers in the UI
- `ocr_source_text` provenance on clinical rows

### 4.6 Auth + ownership scaffolding

File-backed auth (not present in either parent in this form):

- `users.json` / `sessions.json` / `report_ownership.json`
- PBKDF2 password hashing, bearer sessions (72h TTL)
- Demo user seeded on startup: **`demo` / `demo123`**
- Frontend login panel + token injection for uploads/deletes

> Note: ownership helpers exist; upload/delete endpoints are not fully ownership-gated in the current simplified routes. Auth is primarily enforced in the UI for upload UX.

### 4.7 Report deletion

- `DELETE /api/reports/{id}` removes source file + output folder
- Dashboard delete button with confirmation prompt

### 4.8 Port coexistence

| App | Frontend | Backend |
|-----|----------|---------|
| Lerdi | 3000 | 8000 |
| Shpati | **3001** | 8000* |
| TrustLab (typical local) | 5173 | 8001 |

\*If Lerdi and Shpati backends both need to run, only one can bind 8000 at a time.

### 4.9 Test suite for clinical leftovers

Even after OCR-only simplification, tests remain for:

- Validation tiers (`test_pipeline.py`)
- Parser ranges (`test_parser_ranges.py`)
- Clinical report filtering (`test_clinical_report.py`)

---

## 5. Evolution timeline (how the product changed)

### Phase A — Full unified digitizer

Goal: combine Lerdi shell + TrustLab 10-stage clinical pipeline.

Active path then included:

```
ingest → preprocess → OCR → layout → parse → extract
→ map → standardize → validate → clinical report → FHIR
```

UI had Clinical Report, Source & OCR, Technical Data, and review workbench concepts.

### Phase B — Clinical UX refinements

- Clinical report filtered to lab results only
- LabScan square markers for high/low/normal
- OCR selection / manual edit experiments (later reverted)
- Auth + delete features added

### Phase C — OCR-first simplification (current)

User feedback: OCR text-only already showed the right content; the “report” should include **everything** OCR detected.

Resulting active runtime:

```
ingest → preprocess → RapidOCR (best variant) → digital_report.json
```

**Still in the repo but not run by `PipelineManager` today:**

`s4`–`s11`, `ReviewService`, `ClinicalReportView`, `InteractiveWorkbench`, LOINC catalog usage in live processing.

This keeps the clinical engine available to re-wire without rewriting it.

---

## 6. Current architecture (as of this documentation)

### 6.1 Runtime flow

```
Browser (http://127.0.0.1:3001)
    │  Vite proxy /api + /media
    ▼
FastAPI (http://127.0.0.1:8000)
    │
    ├─ POST /api/reports/upload
    │     → save file to storage/uploaded_reports/
    │     → PipelineManager.process()
    │           → s2 preprocess / PDF→image
    │           → s3 RapidOCR variant matrix
    │           → s6b digital_report.json
    │           → ocr.json
    │
    ├─ GET /api/reports/{id}
    │     → summary + ocr + digital_report + image URL
    │
    └─ DELETE /api/reports/{id}
          → remove upload + outputs folder
```

### 6.2 Active frontend routes

| Route | Page |
|-------|------|
| `/` | Dashboard — counts + recent reports |
| `/upload` | Batch upload |
| `/audit` | All reports list |
| `/reports/:id` | OCR Report view + Raw JSON |

### 6.3 Storage layout

```
storage/
├── uploaded_reports/          # original scans
├── outputs/{report_id}/
│   ├── ocr.json               # OCR lines + best variant
│   └── digital_report.json    # page size + positioned lines
├── reviews/                   # reserved for review sessions
├── users.json
├── sessions.json
└── report_ownership.json
```

### 6.4 Leftover (not wired) but intentional

| Module | Status |
|--------|--------|
| `s4`–`s11` pipeline stages | Present; not called by active manager |
| `core/review_service.py` | Present; no `/api/review/*` routes |
| `ClinicalReportView.tsx` | Orphan UI |
| `InteractiveWorkbench.tsx` | Orphan UI (expects review APIs) |
| LOINC catalog | Present for future mapping |

---

## 7. Design principles that guided the merge

1. **Local-first** — no required cloud DB; everything under `storage/`
2. **Show the OCR truth** — never hide detected text behind premature filtering in the primary report view
3. **Clinical safety is staged** — TrustLab’s tiers and review exist for when interpretation is re-enabled
4. **Deterministic IDs** — slugified report folders you can inspect on disk
5. **Dev ergonomics** — Vite proxy, demo login, coexist with Lerdi ports where possible
6. **Keep unused stages, don’t delete history** — clinical modules remain for the next reactivation

---

## 8. How to run Shpati

### Backend (port 8000)

```bash
cd Shpati
source .venv/bin/activate   # or: python3.12 -m venv .venv && source .venv/bin/activate && pip install -e .
PYTHONPATH=backend/src uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
# or: shpati-api
```

### Frontend (port 3001)

```bash
cd Shpati/frontend
npm install
npm run dev
```

Open **http://127.0.0.1:3001**

Demo login: **`demo` / `demo123`**

### Tests

```bash
cd Shpati
source .venv/bin/activate
pytest backend/tests -q
```

---

## 9. Mapping table — parent → Shpati file

| Concept | Parent | Shpati location |
|---------|--------|-----------------|
| Report library | Lerdi `ReportStore` | `backend/src/core/report_store.py` |
| OCR variants | Lerdi OCR pipeline | `pipeline/s2_preprocess.py`, `s3_ocr.py` |
| Vite proxy | Lerdi frontend | `frontend/vite.config.ts` |
| Multi-stage stages | TrustLab pipeline | `pipeline/s1` … `s11` |
| Validation tiers | TrustLab validator | `pipeline/s9_validator.py` |
| Review sessions | TrustLab review API | `core/review_service.py` |
| FHIR bundle | TrustLab / Lerdi | `pipeline/s10_fhir.py` |
| Digital layout view | Shpati original | `pipeline/s6b_digital_report.py`, `DigitalReportCanvas.tsx` |
| Auth | Shpati original | `core/auth_service.py`, `shared/auth.tsx` |
| Full OCR report UI | Shpati original | `OcrReportView.tsx`, `InspectorPage.tsx` |

---

## 10. Honest current state

**What Shpati is today:** a reliable local OCR digitizer and visual report inspector, built on Lerdi’s storage/OCR/UI patterns, with TrustLab’s clinical pipeline kept in-tree for reactivation.

**What it is not (yet) in the live path:** a fully wired clinical LOINC/FHIR/review product. Those pieces were implemented during the merge and then de-emphasized so the OCR layer could be validated end-to-end with full text visibility.

**Recommended next step if clinical digitization returns:**

1. Re-enable `s4`–`s11` inside `PipelineManager`
2. Restore `/api/review/*` routes
3. Keep the OCR Report tab as the ground-truth view; add Clinical as a second filtered view
4. Enforce auth + ownership on upload/delete server-side

---

## 11. Parent repos (for reference)

| Repo | Absolute path |
|------|----------------|
| Lerdi | `/Users/shpatdobraj/Desktop/Repos/Lerdi` |
| TrustLab | `/Users/shpatdobraj/Desktop/Repos/TrustLab-main_Behare` |
| Shpati | `/Users/shpatdobraj/Desktop/Repos/Shpati` |

---

*This document describes the intentional engineering history of Shpati: a merge of Lerdi’s product shell and TrustLab’s clinical safety model, plus Shpati-specific OCR reproduction, auth, deletion, parser fixes, and an OCR-first inspector.*
