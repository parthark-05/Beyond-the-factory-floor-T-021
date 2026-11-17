"""
root_cause_demo.py - Streamlit demo for the P4 Root Cause Analysis module.
Run from the repo root:   streamlit run root_cause_demo.py
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend.root_cause_engine import (
    ALL_MACHINES,
    FLAG_THRESHOLD,
    NODE_POSITIONS,
    SIMULATED_DATA_NOTICE,
    analyze_factory,
    get_downstream_impact,
    get_sample_defects,
    get_sample_readings,
    link_defects_to_machines,
    summarize_defect_links,
)

st.set_page_config(page_title="Root Cause Analysis", layout="wide")
st.title("Root Cause Analysis")


# ---------------------------------------------------------------------
# Helper: draw the factory flow with the root cause + affected machines
# ---------------------------------------------------------------------
def build_flow_figure(graph, ranking, impact):
    root = impact["machine"] if impact else None
    affected = set(impact["downstream"]) if impact else set()
    parallel = set(impact["parallel_unaffected"]) if impact else set()
    path_edges = set(zip(impact["disruption_path"], impact["disruption_path"][1:])) if impact else set()
    info = ranking.set_index("machine")

    fig = go.Figure()

    # Arrows for every production dependency (red if on the disruption path)
    for u, v in graph.edges:
        x0, y0 = NODE_POSITIONS[u]
        x1, y1 = NODE_POSITIONS[v]
        on_path = (u, v) in path_edges
        fig.add_annotation(
            x=x1 - 0.12, y=y1, ax=x0 + 0.12, ay=y0,
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=2, arrowwidth=2 if on_path else 1,
            arrowcolor="#d62728" if on_path else "#aaaaaa",
        )

    # One marker per machine
    xs, ys, colors, labels, hovers = [], [], [], [], []
    for m in graph.nodes:
        x, y = NODE_POSITIONS[m]
        if m == root:
            color = "#d62728"       # root cause = red
        elif m in affected:
            color = "#ff9f1c"       # downstream affected = orange
        elif m in parallel:
            color = "#2ca02c"       # parallel stream, not directly affected = green
        else:
            color = "#b0b0b0"       # upstream / unrelated = grey
        score = info.loc[m, "risk_score"] if m in info.index else float("nan")
        xs.append(x); ys.append(y); colors.append(color); labels.append(m)
        hovers.append(f"{m}<br>Risk score: {score}")
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers+text", text=labels, textposition="top center",
        textfont=dict(size=10), hovertext=hovers, hoverinfo="text",
        marker=dict(size=26, color=colors, line=dict(width=1, color="#333333")),
    ))
    fig.update_layout(
        height=420, showlegend=False, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(visible=False, range=[-0.8, 13.8]),
        yaxis=dict(visible=False, range=[-0.8, 2.9]),
    )
    return fig


# ---------------------------------------------------------------------
# Sidebar: choose data + operator confirmation
# ---------------------------------------------------------------------
st.sidebar.header("Data")
source = st.sidebar.radio(
    "Readings source",
    ["Simulated: Weld Robot 2 failure", "Simulated: healthy factory", "Upload CSV"],
)

readings = None
if source == "Upload CSV":
    uploaded = st.sidebar.file_uploader("Readings CSV", type="csv")
    if uploaded is not None:
        try:
            readings = pd.read_csv(uploaded)
        except Exception as error:  # bad file -> show message, don't crash
            st.sidebar.error(f"Could not read CSV: {error}")
    st.sidebar.download_button(
        "Download sample CSV format",
        get_sample_readings().to_csv(index=False),
        file_name="sample_readings.csv",
    )
elif source == "Simulated: healthy factory":
    readings = get_sample_readings("healthy")
else:
    readings = get_sample_readings("weld_failure")

if readings is None:
    st.info("Upload a readings CSV in the sidebar to begin.")
    st.stop()

if source == "Upload CSV":
    st.caption("Analysing your uploaded readings. Scores show where to look first - they do not prove a cause.")
else:
    st.caption(SIMULATED_DATA_NOTICE)

st.sidebar.header("Operator confirmation")
st.sidebar.caption("Only an explicit confirmation (or a verified fault in the data) makes a cause CONFIRMED.")
confirmed_machines = st.sidebar.multiselect("Machines confirmed faulty by an operator", ALL_MACHINES)
confirm_note = st.sidebar.text_input("Operator note (optional)")
confirmations = {m: confirm_note for m in confirmed_machines}

# ---------------------------------------------------------------------
# Run the backend (ranking uses readings only; defects are linked in tab 2)
# ---------------------------------------------------------------------
result = analyze_factory(readings, operator_confirmations=confirmations)
ranking = result["ranking"]
graph = result["graph"]

if ranking.empty:
    st.error("No usable readings found.")
    for message in result["warnings"]:
        st.write("-", message)
    st.stop()

if result["warnings"]:
    with st.expander(f"Data quality notes ({len(result['warnings'])})"):
        for message in result["warnings"]:
            st.write("-", message)

tab_ranking, tab_defects, tab_impact = st.tabs(
    ["Root cause ranking", "Defect-to-machine linking", "Downstream impact"]
)

# ---------------------------------------------------------------------
# Tab 1: ranking, tags, reasons, advice
# ---------------------------------------------------------------------
with tab_ranking:
    top = ranking.iloc[0]
    if result["top_cause"] is None:
        st.success(f"No machine is above the suspect threshold ({FLAG_THRESHOLD}/100). "
                   f"Highest risk: {top['machine']} ({top['risk_score']}).")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Top suspect", result["top_cause"])
        top_row = ranking[ranking["machine"] == result["top_cause"]].iloc[0]
        c2.metric("Risk score (0-100)", top_row["risk_score"])
        c3.metric("Tag", top_row["label"])

    table = ranking.copy()
    table["tag"] = table["label"].map({"CONFIRMED": "CONFIRMED", "INFERRED": "INFERRED"})
    st.dataframe(
        table[["rank", "machine", "area", "risk_score", "risk_level", "tag", "reasons"]],
        column_config={
            "risk_score": st.column_config.ProgressColumn("Risk score", min_value=0, max_value=100, format="%.1f"),
            "reasons": st.column_config.TextColumn("Why it was flagged", width="large"),
        },
        hide_index=True,
    )

    st.subheader("Details for flagged machines")
    flagged = ranking[ranking["flagged"]]
    if flagged.empty:
        st.write("Nothing flagged.")
    for _, row in flagged.iterrows():
        title = f"#{row['rank']} {row['machine']} - risk {row['risk_score']} - {row['label']}"
        with st.expander(title, expanded=(row["rank"] == 1)):
            st.markdown(f"**Tag reason:** {row['label_reason']}")
            st.markdown("**Why it was flagged:**")
            for reason in row["reason_list"]:
                st.write("-", reason)
            st.markdown("**Recommended actions:**")
            for tip in row["advice_list"]:
                st.write("-", tip)
            st.caption(
                "Score breakdown (points): "
                f"temperature {row['pts_temperature']}, processing time {row['pts_processing_time']}, "
                f"output {row['pts_output']}, downtime {row['pts_downtime']}, "
                f"buffer {row['pts_buffer']}, defects {row['pts_defects']}"
            )

# ---------------------------------------------------------------------
# Tab 2: defect-to-machine linking (operator can verify a machine)
# ---------------------------------------------------------------------
with tab_defects:
    st.write("Defects found at inspection. Pick a machine in **verified_machine** to record an "
             "operator verification - that overrides the automatic guess.")
    if "defects_table" not in st.session_state:
        st.session_state["defects_table"] = get_sample_defects()
    edited = st.data_editor(
        st.session_state["defects_table"],
        column_config={
            "verified_machine": st.column_config.SelectboxColumn(
                "verified_machine", options=[""] + ALL_MACHINES),
        },
        num_rows="dynamic",
        hide_index=True,
        key="defect_editor",
    )
    links = link_defects_to_machines(edited, ranking)
    st.subheader("Likely responsible machines")
    st.dataframe(
        links[["car_id", "defect_type", "likely_machine", "probability", "status", "candidates", "explanation"]],
        hide_index=True,
    )
    st.subheader("Defects per machine")
    summary = summarize_defect_links(links)
    if summary.empty:
        st.write("No defects linked yet.")
    else:
        st.dataframe(summary, hide_index=True)
        st.bar_chart(summary.set_index("machine")["linked_defects"])
    st.caption("Links are likelihoods based on defect type and machine risk, not proof of cause.")

# ---------------------------------------------------------------------
# Tab 3: downstream impact (NetworkX)
# ---------------------------------------------------------------------
with tab_impact:
    machines_sorted = list(ranking["machine"])
    default_index = machines_sorted.index(result["top_cause"]) if result["top_cause"] in machines_sorted else 0
    chosen = st.selectbox("Root cause to analyse", machines_sorted, index=default_index)
    impact = get_downstream_impact(chosen, graph)

    st.markdown("**Disruption path:** " + " -> ".join(impact["disruption_path"]))
    st.info(impact["note"])
    st.plotly_chart(build_flow_figure(graph, ranking, impact))
    st.caption("Red = selected root cause, orange = downstream affected, green = parallel stream "
               "(running independently until Marriage), grey = upstream/unrelated.")

    if impact["downstream"]:
        affected = ranking.set_index("machine").loc[
            impact["downstream"], ["output_per_hour", "buffer_qty", "risk_score", "label"]
        ].reset_index()
        affected.insert(1, "steps_from_cause", affected["machine"].map(impact["hops"]))
        st.markdown("**Downstream machines affected:**")
        st.dataframe(affected, hide_index=True)