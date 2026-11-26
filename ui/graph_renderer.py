"""Evidence graph visualisation for CERBERUS-X."""

import json
import streamlit as st


def _escape(value):
    """Escape text for Graphviz DOT."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def build_graph_dot(result):
    """Build a Graphviz DOT graph from an AnalysisResult."""

    lines = [
        "digraph CERBERUS {",
        'graph [rankdir=LR, bgcolor="white", nodesep=0.5];',
        'node [fontname="Arial", style="filled", shape="box"];',
        'edge [fontname="Arial", fontsize=9];'
    ]

    # Document nodes
    for doc in result.documents:
        doc_id = _escape(doc.id)
        filename = _escape(doc.filename)

        lines.append(
            f'"{doc_id}" [label="Document\\n{filename}", '
            'fillcolor="#DCEBFF", color="#3973AC"];'
        )

    # Entity nodes
    for entity in result.entities:
        entity_id = _escape(entity.id)
        name = _escape(entity.canonical_name)

        lines.append(
            f'"{entity_id}" [label="Entity\\n{name}", '
            'fillcolor="#DFF5E1", color="#32834A"];'
        )

    # Claim nodes and document/entity relationships
    for claim in result.claims:
        claim_id = _escape(claim.id)
        label = _escape(f"{claim.predicate}: {claim.value}")

        if claim.suspicious:
            color = "#FFD6D6"
        elif str(claim.status).lower().endswith("disputed"):
            color = "#FFE6B3"
        else:
            color = "#E9E4FF"

        lines.append(
            f'"{claim_id}" [label="{label}", '
            f'fillcolor="{color}", color="#666666"];'
        )

        lines.append(f'"{_escape(claim.source_id)}" -> "{claim_id}";')

        if getattr(claim, "entity_id", None):
            lines.append(
                f'"{claim_id}" -> "{_escape(claim.entity_id)}";'
            )

    # Conflict relationships
    for conflict in result.conflicts:
        for claim_id in conflict.claim_ids:
            lines.append(
                f'"{_escape(claim_id)}" -> '
                f'"conflict_{_escape(conflict.id)}" '
                '[color="#D62728", style="dashed"];'
            )

        conflict_label = _escape(conflict.conflict_type.value)

        lines.append(
            f'"conflict_{_escape(conflict.id)}" '
            f'[label="Conflict\\n{conflict_label}", '
            'shape="diamond", fillcolor="#FFD6D6"];'
        )

    lines.append("}")

    return "\n".join(lines)


def render_evidence_graph(result):
    """Render evidence graph in Streamlit."""

    st.subheader("Evidence Graph")

    if not result.documents:
        st.info("No evidence documents available.")
        return

    dot = build_graph_dot(result)

    try:
        st.graphviz_chart(dot)
    except Exception as exc:
        st.warning(f"Graph visualisation unavailable: {exc}")

        st.write("Showing graph relationships instead:")

        rows = []

        for claim in result.claims:
            rows.append({
                "Document": claim.source_id,
                "Entity": claim.entity_name,
                "Attribute": claim.predicate,
                "Value": claim.value
            })

        if rows:
            st.dataframe(rows, use_container_width=True)


def render_graph_statistics(result):
    """Show graph statistics."""

    st.subheader("Graph Statistics")

    c1, c2, c3 = st.columns(3)

    c1.metric("Documents", len(result.documents))
    c2.metric("Entities", len(result.entities))
    c3.metric("Claims", len(result.claims))