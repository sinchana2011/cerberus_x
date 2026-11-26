# CERBERUS-X
<<<<<<< HEAD
### Multimodal Evidence Intelligence & Conflict-Aware Reasoning Platform

CERBERUS-X is an offline-first multimodal intelligence platform that ingests documents, spreadsheets, JSON datasets, and images, resolves entities across sources, builds an evidence knowledge graph, detects cross-modal contradictions and impossible timelines, tracks entity Digital Twins, and provides traceable question answering with optional local Ollama (`llama3.2:3b`) synthesis.
=======
### A Multimodal Evidence Intelligence & Conflict-Aware Reasoning System

CERBERUS-X is an offline intelligence system that analyses multiple forms of evidence and identifies contradictions between them.

It combines document extraction, entity resolution, knowledge graph construction, conflict detection and traceable question answering.

## Problem Statement

Traditional information extraction systems often treat each document independently. They may overlook contradictions between different sources, fail to identify the same entity across records, or accept manipulated content as trustworthy evidence.

CERBERUS-X addresses these challenges through multimodal evidence analysis and conflict-aware reasoning.

## Key Features

- Multimodal evidence ingestion
- PDF, CSV, TXT and image processing
- Suspicious and hidden content detection
- Entity resolution and alias matching
- Knowledge graph construction
- Contradiction and timeline detection
- Digital twin state tracking
- Evidence-based question answering
- Source citations and reliability information
- Forensic evidence inspection
- JSON analysis export
>>>>>>> 4682e39edabba11574378524c8a1f84a103cb8cf

## Architecture

```text
<<<<<<< HEAD
React + TypeScript + Vite Dashboard (Dark Navy Command Center)
   │  (Axios REST client -> http://127.0.0.1:8000)
   ▼
FastAPI Backend (backend/main.py, backend/service.py)
   ├── SQLite Persistence (backend/database.py -> data/cerberus.db)
   ├── Local Ollama Integration (core/llm.py -> llama3.2:3b, optional)
   └── Core Intelligence Pipeline (pipeline.py)
         ├── Multimodal Extractor (core/extractor.py: PyMuPDF, Pandas, Pillow, Tesseract)
         ├── Content Sanitizer (core/sanitizer.py: hidden text & prompt-injection isolation)
         ├── Entity Resolver (core/entity_resolver.py: RapidFuzz + identifier/type guards)
         ├── Claim Extractor (core/claim_extractor.py)
         ├── Evidence Graph (core/graph_engine.py: NetworkX MultiDiGraph)
         ├── Conflict-Aware Reasoner (core/reasoner.py: deterministic rules & QA)
         └── Digital Twin (core/digital_twin.py: chronological attribute trajectories)
```

## Key Capabilities

- **Multimodal Document Ingestion**: PDF (PyMuPDF), CSV & Excel `.xlsx`/`.xls` (Pandas + stdlib XML fallback), JSON, TXT/MD/LOG, and Images (Pillow + optional Tesseract OCR).
- **Forensic Sanitization**: Detects white-on-white/invisible PDF text, prompt-injection heuristics, and low OCR confidence. Suspicious claims are quarantined (`status=suspicious`) and never used as verified facts.
- **Entity Resolution**: RapidFuzz matching with identifier vetoes, type conflict guards, and person initial matching.
- **Cross-Modal Conflict Detection**: Distinguishes real contradictions (`true_conflict`, `same_event_conflict`, `impossible_timeline`) from normal progressions (`workflow_stage`, `temporal_change`, `compatible_different_time`, `duplicate`).
- **Evidence Knowledge Graph**: Interactive React Flow visualization over NetworkX nodes (`document`, `claim`, `entity`, `conflict`) and typed relationships.
- **Digital Twin Timeline**: Tracks current, historical superseded, disputed, and quarantined states per entity with source provenance.
- **Traceable QA & Local Ollama (`llama3.2:3b`)**: Deterministic evidence-grounded answers with citations and optional local Ollama narrative synthesis (gracefully falls back when Ollama is offline).
- **SQLite Analysis History**: Persistent storage of analyses, documents, entities, claims, conflicts, and twin states.

## Dependencies

- **Backend**: Python 3.11+, FastAPI, Uvicorn, Pydantic, NetworkX, Pandas, PyMuPDF, Pillow, RapidFuzz, httpx, Pytest, Pytesseract (optional Tesseract binary).
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, React Router, Recharts, `@xyflow/react`, Axios, Lucide React.
- **Local AI (Optional)**: Ollama running on `http://127.0.0.1:11434` with `llama3.2:3b`.

## REST API Endpoints

- `GET /api/health` — Backend, SQLite, OCR, Ollama (`llama3.2:3b`), and supported format status
- `POST /api/upload` — Multipart multimodal evidence upload & full analysis run
- `POST /api/demo` — Run the built-in 5-case demo bundle into SQLite
- `GET /api/analyses` — List SQLite analysis history and aggregate counts
- `GET /api/analysis/{analysis_id}` — Full analysis detail (documents, entities, claims, conflicts, twin states)
- `DELETE /api/analysis/{analysis_id}` — Delete a persisted analysis from SQLite
- `GET /api/analysis/{analysis_id}/graph` — React Flow graph nodes, edges, and statistics
- `GET /api/analysis/{analysis_id}/conflicts` — Filterable conflicts (`conflict_type`, `severity`, `only_real_problems`)
- `GET /api/analysis/{analysis_id}/digital-twin` — Entity state histories and current attributes
- `POST /api/analysis/{analysis_id}/ask` — Evidence-grounded QA (`question`, `use_llm`)
- `POST /api/analysis/{analysis_id}/brief` — Executive intelligence briefing (Ollama + deterministic fallback)
- `GET /api/analysis/{analysis_id}/forensics` — Security flags, reliability scores, and raw extracted text

## Running Locally (Windows PowerShell)

### 1. Backend Setup & Tests
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python generate_demo_data.py
python -m pytest -p no:cacheprovider -q
```

### 2. Start FastAPI Backend
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Start React Frontend
```powershell
cd frontend
npm install
npm run dev
```
Open `http://127.0.0.1:5173`.

### 4. Production Frontend Build
```powershell
cd frontend
npm run build
```

### 5. Optional Local Ollama Setup
```powershell
ollama pull llama3.2:3b
ollama serve
```
If Ollama is offline, CERBERUS-X continues operating deterministically with zero interruption.
=======
Evidence Upload
      |
      v
Document Extractor
      |
      v
Content Sanitizer
      |
      v
Entity Resolver
      |
      v
Claim Extraction
      |
      v
Evidence Graph
      |
      v
Conflict-Aware Reasoner
      |
      v
Digital Twin
      |
      v
Streamlit Dashboard
```

## Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python |
| Frontend | Streamlit |
| Graph Processing | NetworkX |
| Data Validation | Pydantic |
| PDF Extraction | PyMuPDF |
| Tabular Processing | Pandas |
| Image Processing | Pillow |
| OCR | Tesseract |
| Testing | Pytest |

## Running the Project

```powershell
pip install -r requirements.txt
python generate_demo_data.py
python -m pytest -q
streamlit run app.py
```

## Project Structure

```text
cerberus_x/
│
├── app.py
├── pipeline.py
├── generate_demo_data.py
├── requirements.txt
├── README.md
│
├── core/
│   ├── schemas.py
│   ├── extractor.py
│   ├── sanitizer.py
│   ├── entity_resolver.py
│   ├── graph_engine.py
│   ├── reasoner.py
│   └── digital_twin.py
│
├── ui/
│   ├── graph_renderer.py
│   └── twin_view.py
│
├── tests/
│
├── data/
│   ├── uploads/
│   └── analysis/
│
├── demo_data/
├── demo_ground_truth/
│
└── docs/
    └── SETUP.md
```

## Security Design

CERBERUS-X treats all uploaded content as untrusted evidence.

Hidden text and suspicious instructions are flagged and preserved for investigation. They are not treated as trusted system instructions or verified facts.

## Current Scope

This is an offline MVP. Its extraction and reasoning components use local processing and rule-based methods. Detection quality must be evaluated against the separate demo ground truth before making claims about accuracy or reliability.
>>>>>>> 4682e39edabba11574378524c8a1f84a103cb8cf
