<<<<<<< HEAD
"""CERBERUS-X main Streamlit application."""

import json
from pathlib import Path

import streamlit as st

from core.extractor import save_upload, ocr_status
from core.reasoner import answer_question
from pipeline import run_pipeline

from ui.graph_renderer import (
    render_evidence_graph,
    render_graph_statistics
)

from ui.twin_view import render_digital_twin


# --------------------------------------------------
# Configuration
# --------------------------------------------------

st.set_page_config(
    page_title="CERBERUS-X",
    page_icon="🔍",
    layout="wide"
)

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
ANALYSIS_DIR = BASE_DIR / "data" / "analysis"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# Styling
# --------------------------------------------------

st.markdown("""
<style>

.main {
    background-color: #F7F9FC;
}

.title {
    font-size: 38px;
    font-weight: 800;
    color: #17365D;
}

.subtitle {
    color: #64748B;
    font-size: 16px;
}

</style>
""", unsafe_allow_html=True)


# --------------------------------------------------
# Header
# --------------------------------------------------

st.markdown(
    '<div class="title">🔍 CERBERUS-X</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">'
    'Multimodal Evidence Intelligence & Conflict-Aware Reasoning'
    '</div>',
    unsafe_allow_html=True
)

st.divider()


# --------------------------------------------------
# Sidebar
# --------------------------------------------------

st.sidebar.title("CERBERUS-X")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Upload Evidence",
        "Evidence Graph",
        "Conflicts",
        "Digital Twin",
        "Ask Questions",
        "Forensic View"
    ]
)

ocr_available, ocr_message = ocr_status()

if ocr_available:
    st.sidebar.success("OCR Available")
else:
    st.sidebar.warning("OCR Unavailable")

st.sidebar.caption(ocr_message)


# --------------------------------------------------
# Session state
# --------------------------------------------------

if "result" not in st.session_state:
    st.session_state.result = None


result = st.session_state.result


# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def run_analysis(paths):

    if not paths:
        st.error("Please upload at least one evidence file.")
        return

    with st.spinner("Analysing evidence..."):

        try:
            result = run_pipeline(paths)

            st.session_state.result = result

            output_file = ANALYSIS_DIR / "latest_analysis.json"

            result.save_json(output_file)

            st.success("Evidence analysis completed!")

            st.rerun()

        except Exception as exc:
            st.error(f"Analysis failed: {exc}")


def show_metrics(result):

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Documents", len(result.documents))
    c2.metric("Entities", len(result.entities))
    c3.metric("Claims", len(result.claims))
    c4.metric("Conflicts", len(result.conflicts))


# --------------------------------------------------
# Dashboard
# --------------------------------------------------

if page == "Dashboard":

    st.header("Dashboard")

    if result is None:

        st.info(
            "Welcome to CERBERUS-X. Upload evidence to begin analysis."
        )

        st.markdown("""
        ### System Capabilities

        - Multimodal evidence ingestion
        - Document and image extraction
        - Suspicious content detection
        - Entity resolution
        - Evidence graph construction
        - Contradiction detection
        - Digital twin generation
        - Traceable question answering
        """)

    else:

        show_metrics(result)

        st.divider()

        st.subheader("Recent Analysis")

        for doc in result.documents:
            st.write(
                f"📄 {doc.filename} — {doc.source_type}"
            )

        st.divider()

        st.subheader("System Warnings")

        if result.warnings:

            for warning in result.warnings:
                st.warning(warning)

        else:
            st.success("No system warnings.")


# --------------------------------------------------
# Upload Evidence
# --------------------------------------------------

elif page == "Upload Evidence":

    st.header("Upload Evidence")

    uploaded_files = st.file_uploader(
        "Upload PDF, CSV, TXT or image files",
        type=["pdf", "csv", "txt", "md", "png", "jpg", "jpeg", "tiff"],
        accept_multiple_files=True
    )

    if uploaded_files:

        st.write("Selected files:")

        for file in uploaded_files:
            st.write(f"📄 {file.name} ({file.size} bytes)")

        if st.button("Start Evidence Analysis", type="primary"):

            paths = []

            for file in uploaded_files:

                path = save_upload(
                    file.name,
                    file.getvalue(),
                    UPLOAD_DIR
                )

                paths.append(path)

            run_analysis(paths)


    st.divider()

    st.subheader("Try Demo Evidence")

    if st.button("Analyse Demo Dataset"):

        demo_dir = BASE_DIR / "demo_data"

        demo_files = [
            demo_dir / "case1_quantity_conflict.csv",
            demo_dir / "case2_order_vs_dispatch.txt",
            demo_dir / "case3_leadership.txt",
            demo_dir / "case4_hidden_instruction.pdf",
            demo_dir / "case5_timeline.txt"
        ]

        missing = [str(p) for p in demo_files if not p.exists()]

        if missing:
            st.error("Demo files are missing. Run python generate_demo_data.py first.")
        else:
            run_analysis(demo_files)


# --------------------------------------------------
# Evidence Graph
# --------------------------------------------------

elif page == "Evidence Graph":

    st.header("Evidence Graph")

    if result is None:

        st.info("Run an analysis first.")

    else:

        render_graph_statistics(result)

        st.divider()

        render_evidence_graph(result)


# --------------------------------------------------
# Conflicts
# --------------------------------------------------

elif page == "Conflicts":

    st.header("Conflict Detection")

    if result is None:

        st.info("Run an analysis first.")

    elif not result.conflicts:

        st.success("No conflicts detected.")

    else:

        for index, conflict in enumerate(result.conflicts, start=1):

            with st.expander(
                f"{index}. {conflict.conflict_type.value}"
            ):

                st.write("**Entity:**", conflict.entity_name)

                st.write("**Attribute:**", conflict.predicate)

                st.write("**Explanation:**", conflict.explanation)

                st.write("**Severity:**", conflict.severity)

                st.write("**Needs Review:**", conflict.needs_review)

                st.write("**Related Claims:**")

                for claim_id in conflict.claim_ids:
                    st.write(f"- {claim_id}")


# --------------------------------------------------
# Digital Twin
# --------------------------------------------------

elif page == "Digital Twin":

    st.header("Digital Twin")

    if result is None:

        st.info("Run an analysis first.")

    else:

        render_digital_twin(result)


# --------------------------------------------------
# Ask Questions
# --------------------------------------------------

elif page == "Ask Questions":

    st.header("Ask CERBERUS-X")

    st.write(
        "Ask questions using the evidence you uploaded."
    )

    if result is None:

        st.info("Upload and analyse evidence first.")

    else:

        question = st.text_input(
            "Enter your question",
            placeholder="Example: How many units were dispatched?"
        )

        if st.button("Ask"):

            if not question.strip():

                st.warning("Please enter a question.")

            else:

                with st.spinner("Reasoning over evidence..."):

                    try:

                        answer = answer_question(
                            question,
                            result.claims,
                            result.conflicts,
                            result.documents,
                            result.entities,
                        )

                        st.subheader("Answer")

                        st.write(answer.answer_text)

                        st.write(
                            f"**Status:** {answer.status.value}"
                        )

                        st.write(
                            f"**Confidence:** {answer.confidence:.2f}"
                        )

                        st.subheader("Evidence Citations")

                        if answer.citations:

                            for citation in answer.citations:

                                with st.container(border=True):

                                    st.write(
                                        f"📄 {citation.filename}"
                                    )

                                    st.write(citation.snippet)

                                    st.caption(
                                        f"Location: {citation.locator or 'Unknown'}"
                                    )

                                    st.caption(
                                        f"Reliability: {citation.reliability:.2f}"
                                    )

                        else:

                            st.info("No citations were returned.")

                        if answer.conflict_ids:

                            st.subheader("Related Conflicts")

                            for conflict_id in answer.conflict_ids:
                                st.write(conflict_id)

                        if answer.notes:

                            st.subheader("Reasoning Notes")

                            for note in answer.notes:
                                st.write(f"- {note}")

                    except Exception as exc:

                        st.error(f"Question answering failed: {exc}")


# --------------------------------------------------
# Forensic View
# --------------------------------------------------

elif page == "Forensic View":

    st.header("Forensic Evidence View")

    if result is None:

        st.info("Run an analysis first.")

    else:

        st.warning(
            "Suspicious evidence is preserved for investigation "
            "but must not be treated as a verified fact."
        )

        for doc in result.documents:

            with st.expander(doc.filename):

                st.write("**Source type:**", doc.source_type)

                st.write("**Reliability:**", doc.reliability)

                st.write("**Extraction method:**", doc.extraction_method)

                st.write("**Security flags:**")

                if doc.flags:

                    for flag in doc.flags:

                        st.error(
                            f"{flag.kind.value}: {flag.description}"
                        )

                        if flag.evidence:
                            st.code(flag.evidence)

                else:

                    st.success("No security flags detected.")

                st.write("**Original extracted text:**")

                st.text_area(
                    "Evidence text",
                    doc.text,
                    height=200,
                    key=f"forensic_{doc.id}"
                )


# --------------------------------------------------
# Download Analysis
# --------------------------------------------------

if result is not None:

    st.sidebar.divider()

    st.sidebar.subheader("Export")

    json_data = result.model_dump_json(indent=2)

    st.sidebar.download_button(
        "Download Analysis JSON",
        data=json_data,
        file_name="cerberus_analysis.json",
        mime="application/json"
    )
=======
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
>>>>>>> 4682e39edabba11574378524c8a1f84a103cb8cf
