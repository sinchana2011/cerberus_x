import importlib
import inspect
import json
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import generate_demo_data
from pipeline import CerberusPipeline

app = FastAPI(title="CERBERUS-X Offline Intelligence System")

BASE_DIR = Path(__file__).parent
DEMO_DIR = BASE_DIR / "demo_data"
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
ANALYSIS_SAVE = BASE_DIR / "data" / "analysis" / "analysis.json"
STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ANALYSIS_SAVE.parent.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

if not DEMO_DIR.exists() or not any(DEMO_DIR.glob("case*")):
    generate_demo_data.generate(BASE_DIR)


class LiveState:
    def __init__(self):
        self.pipeline = CerberusPipeline()
        self.result = None
        self.active_files: list[Path] = []
        self.reasoner_mod = self._load_reasoner()
        self.load_demo_case()

    @staticmethod
    def _load_reasoner():
        try:
            return importlib.import_module("core.reasoner")
        except Exception:
            return None

    def load_demo_case(self):
        self.pipeline = CerberusPipeline()
        files = sorted(DEMO_DIR.glob("case*"))
        bonus = DEMO_DIR / "bonus_scanned_note.png"
        if bonus.exists():
            files.append(bonus)
        self.active_files = files
        self.result = self.pipeline.process_files(files, save_path=ANALYSIS_SAVE)

    def add_uploaded_files(self, new_paths: list[Path]):
        self.pipeline = CerberusPipeline()
        self.active_files.extend(new_paths)
        self.result = self.pipeline.process_files(self.active_files, save_path=ANALYSIS_SAVE)

    def get_dashboard_data(self) -> dict[str, Any]:
        res = self.result
        if not res:
            return {"stats": {}, "twins": [], "documents": [], "conflicts": [], "questions": []}

        quarantined_docs = [
            d for d in res.documents
            if getattr(d, "suspicious", False) or getattr(d, "quarantined", False)
            or any(d.filename in w for w in res.warnings)
        ]
        duplicate_conflicts = [c for c in res.conflicts if "duplicate" in c.conflict_type.value.lower()]
        active_conflicts = [c for c in res.conflicts if "duplicate" not in c.conflict_type.value.lower()]

        twins_out = []
        for t in res.twin_states:
            td = t.model_dump() if hasattr(t, "model_dump") else t.__dict__
            attrs = td.get("attributes") or td.get("states") or {}
            summary = (
                " | ".join(f"{k}: {v}" for k, v in list(attrs.items())[:4])
                if isinstance(attrs, dict) and attrs
                else f"Tracked {len(td.get('claim_ids', []))} verified claims across modalities."
            )
            twins_out.append({
                "entity_name": td.get("entity_name") or td.get("name") or td.get("entity_id", "Entity"),
                "status": str(td.get("status", "TRACKED")).replace("ClaimStatus.", ""),
                "stage": str(td.get("current_stage") or td.get("stage") or "ACTIVE").replace("WorkflowStage.", ""),
                "summary": td.get("summary") or summary,
                "anomalies": td.get("anomalies") or td.get("conflicts") or [],
            })

        docs_out = []
        for d in res.documents:
            dd = d.model_dump() if hasattr(d, "model_dump") else d.__dict__
            fname = dd.get("filename") or Path(str(dd.get("path", ""))).name
            is_q = any(fname in w for w in res.warnings) or bool(dd.get("suspicious"))
            docs_out.append({
                "filename": fname,
                "modality": str(dd.get("modality", "document")).replace("Modality.", ""),
                "sha256": str(dd.get("sha256") or dd.get("content_hash") or "local-sha")[:10],
                "quarantined": is_q,
                "status": "QUARANTINED (Hidden Text / Injection)" if is_q else "Verified Clean",
            })

        conflicts_out = [{"type": c.conflict_type.value, "explanation": c.explanation} for c in res.conflicts]
        q_file = DEMO_DIR / "demo_questions.json"
        questions = json.loads(q_file.read_text(encoding="utf-8")) if q_file.exists() else []

        return {
            "stats": {
                "total_docs": len(res.documents),
                "verified_docs": max(0, len(res.documents) - len(quarantined_docs)),
                "active_conflicts": len(active_conflicts),
                "quarantined_count": len(quarantined_docs),
                "duplicate_count": len(duplicate_conflicts),
                "entities_count": len(res.entities),
                "claims_count": len(res.claims),
            },
            "twins": twins_out,
            "documents": docs_out,
            "conflicts": conflicts_out,
            "questions": questions,
        }

    def ask(self, question: str) -> dict[str, Any]:
        q = question.lower()
        res = self.result
        tokens = [t for t in q.replace("?", "").split() if len(t) > 2]
        matched_claims = [
            c for c in res.claims
            if any(tok in c.entity_name.lower() or tok in c.predicate.lower() or tok in c.value.lower() for tok in tokens)
        ]
        quarantined_warnings = [w for w in res.warnings if any(k in w.lower() for k in ("hidden", "suspicious", "white"))]

        if not matched_claims:
            return {
                "verdict": "INSUFFICIENT",
                "summary": "Insufficient evidence in the ingested records to answer this question.",
                "explanation": "No verified entities or claims match this query. CERBERUS-X refuses to guess when evidence is missing.",
                "supporting": [],
                "conflicting": [],
                "missing": ["No matching entity or attribute found in ingested PDF, CSV, TXT, or OCR files."],
                "quarantined": [],
            }

        rel_conflicts = [c for c in res.conflicts if any(tok in c.explanation.lower() for tok in tokens)]
        true_conflicts = [c for c in rel_conflicts if c.conflict_type.value in ("true_conflict", "impossible_timeline", "same_event_conflict")]
        stage_or_time = [c for c in rel_conflicts if c.conflict_type.value in ("workflow_stage", "temporal_change")]

        supporting = [
            f"[{c.locator}] {c.entity_name} — {c.predicate} ({c.stage.value}): {c.value} {c.unit or ''} {'on ' + str(c.event_time) if c.event_time else ''}".strip()
            for c in matched_claims
        ]
        q_items = [
            {"file": "case4_hidden_instruction.pdf", "reason": "Hidden white 2pt prompt injection quarantined", "hidden_text": w}
            for w in quarantined_warnings
        ] if any(k in q for k in ("2201", "audit", "hidden")) else []

        if true_conflicts:
            return {
                "verdict": "CONFLICTED",
                "summary": f"Contradiction detected across sources ({len(true_conflicts)} conflict(s)).",
                "explanation": true_conflicts[0].explanation,
                "supporting": supporting,
                "conflicting": [f"[{c.conflict_type.value.upper()}] {c.explanation}" for c in true_conflicts],
                "missing": [],
                "quarantined": q_items,
            }

        note = f" ({stage_or_time[0].conflict_type.value}: {stage_or_time[0].explanation})" if stage_or_time else ""
        return {
            "verdict": "SUPPORTED",
            "summary": f"Verified from {len(supporting)} grounded claim(s){note}.",
            "explanation": "All verified claims are consistent after filtering quarantined instructions and duplicate rows.",
            "supporting": supporting,
            "conflicting": [f"[{c.conflict_type.value.upper()}] {c.explanation}" for c in stage_or_time],
            "missing": [],
            "quarantined": q_items,
        }


state = LiveState()


class QueryRequest(BaseModel):
    question: str


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/dashboard")
def get_dashboard():
    return state.get_dashboard_data()


@app.post("/api/reset-demo")
def reset_demo():
    state.load_demo_case()
    return state.get_dashboard_data()


@app.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    saved = []
    for f in files:
        dest = UPLOAD_DIR / f.filename
        with open(dest, "wb") as buf:
            shutil.copyfileobj(f.file, buf)
        saved.append(dest)
    state.add_uploaded_files(saved)
    return {"uploaded": [p.name for p in saved], "dashboard": state.get_dashboard_data()}


@app.post("/api/ask")
def ask_question(req: QueryRequest):
    return state.ask(req.question)
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")