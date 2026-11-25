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

                        answer = answer_question(question, result)

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