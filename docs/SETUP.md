# CERBERUS-X — Setup Guide

## 1. Project Overview

CERBERUS-X is an offline multimodal evidence intelligence system.

It processes documents, images, CSV files and text records to identify entities, extract claims, detect contradictions and generate traceable answers.

## 2. Technology Stack

- Python 3.11
- Streamlit
- NetworkX
- Pydantic
- PyMuPDF
- Pandas
- Pillow
- Tesseract OCR (optional)
- Pytest

## 3. Installation

Open PowerShell in the project directory.

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

## 4. Generate Demo Data

```powershell
python generate_demo_data.py
```

This creates the demo evidence files and separate ground-truth data.

The pipeline must never use the ground-truth files during normal analysis.

## 5. Run Tests

```powershell
python -m pytest -q
```

## 6. Start the Application

```powershell
streamlit run app.py
```

Streamlit will display a local application address in the terminal. Open that address in your browser.

## 7. Main Features

1. Evidence upload
2. Multimodal extraction
3. Suspicious content detection
4. Entity resolution
5. Evidence graph visualisation
6. Conflict detection
7. Digital twin generation
8. Question answering
9. Forensic evidence inspection
10. JSON export

## 8. Optional OCR Installation

OCR requires the Tesseract executable in addition to the Python package.

Install Tesseract separately and make sure it is available in PATH.

If necessary, configure the executable path through the TESSERACT_CMD environment variable.

The application can still run without Tesseract, but scanned-image text extraction will be unavailable.

## 9. Data Storage

- `data/uploads/` — uploaded evidence
- `data/analysis/` — generated analysis JSON
- `demo_data/` — sample evidence
- `demo_ground_truth/` — expected results used for evaluation

## 10. Important Security Principle

Evidence is treated as untrusted data.

Suspicious content is preserved for forensic review but must never be followed as an instruction or treated as a verified fact.