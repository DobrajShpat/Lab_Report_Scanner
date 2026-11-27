# Shpati — Unified Lab Report Digitizer

Shpati combines the best engineering patterns from **Lerdi** (deterministic file storage, RapidOCR variant matrix, Vite API proxy) and **TrustLab** (staged clinical pipeline, 3-tier validation, human review).

For the full creation story — what came from each repo, what was improved, and how the product evolved — see **[DOCUMENTATION.md](./DOCUMENTATION.md)**.

## Current focus

**OCR-first:** upload a lab report → RapidOCR extracts every text segment → inspect the full digital reconstruction (canvas + OCR text list + plain text).

Clinical stages (`s4`–`s11`, review, FHIR) remain in the codebase for reactivation; they are not on the live processing path today.

## Architecture

```
Shpati/
├── backend/          FastAPI + OCR pipeline
├── frontend/         React 19 + Vite 6 + Tailwind 4
├── storage/          Local-first report folders by ID
└── DOCUMENTATION.md  Full creation & merge history
```

| Layer | Source inspiration |
|-------|-------------------|
| `ReportStore` | Lerdi — one folder per report ID |
| OCR variant matrix | Lerdi — RapidOCR across OpenCV variants |
| Pipeline stages `s1`–`s11` | TrustLab — single-responsibility stages |
| Validation / review / FHIR | TrustLab (present; not live-wired) |
| Digital report + OCR inspector | Shpati original |
| Dev proxy | Lerdi — `/api` and `/media` via Vite |

## Quick start

### Backend (port 8000)

```bash
cd Shpati
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
shpati-api
```

### Frontend (port 3001)

```bash
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:3001**

Demo login: **demo** / **demo123**

## API highlights

- `GET /api/health` — service status
- `GET /api/reports` — list reports + OCR counts
- `POST /api/reports/upload` — ingest + run OCR pipeline
- `GET /api/reports/{id}` — OCR + digital report payloads
- `DELETE /api/reports/{id}` — remove report
- `POST /api/auth/login` — session token (demo/demo123)

## Storage layout

```
storage/uploaded_reports/     # source files
storage/outputs/{report_id}/  # ocr.json, digital_report.json
```

## Tests

```bash
source .venv/bin/activate
pytest backend/tests -q
```
