# CERBERUS-X
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

## Architecture

```text
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