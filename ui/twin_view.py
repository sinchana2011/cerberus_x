"""Digital twin visualisation for CERBERUS-X."""

import streamlit as st
import pandas as pd


def render_twin_summary(result):
    """Display digital twin summary."""

    st.subheader("Digital Twin Overview")

    states = result.twin_states

    if not states:
        st.info("No digital twin states available.")
        return

    st.metric("Total Recorded States", len(states))

    df = pd.DataFrame([
        {
            "Entity": state.entity_name,
            "Attribute": state.attribute,
            "Value": state.value,
            "Valid From": str(state.valid_from or "Unknown"),
            "Valid To": str(state.valid_to or "Current / Unknown"),
            "Status": str(state.status),
            "Reliability": state.reliability
        }
        for state in states
    ])

    st.dataframe(df, use_container_width=True)


def render_entity_history(result):
    """Display history for a selected entity."""

    st.subheader("Entity History")

    if not result.twin_states:
        st.info("No entity history available.")
        return

    entity_names = sorted({
        state.entity_name for state in result.twin_states
    })

    selected = st.selectbox(
        "Select an entity",
        entity_names
    )

    history = [
        state for state in result.twin_states
        if state.entity_name == selected
    ]

    history.sort(
        key=lambda state: state.valid_from or __import__("datetime").datetime.min
    )

    for state in history:
        with st.container(border=True):
            st.markdown(f"**Attribute:** {state.attribute}")
            st.markdown(f"**Value:** {state.value}")
            st.markdown(f"**Valid from:** {state.valid_from or 'Unknown'}")
            st.markdown(f"**Valid to:** {state.valid_to or 'Current / Unknown'}")
            st.markdown(f"**Status:** {state.status}")
            st.progress(float(state.reliability))


def render_digital_twin(result):
    """Render complete digital twin section."""

    render_twin_summary(result)

    st.divider()

    render_entity_history(result)