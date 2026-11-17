import sys
import time
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# =========================================================
# IMPORT TEAM MODULES
# =========================================================

ROOT = Path(__file__).resolve().parent

for folder in [
    "p1-backend-data",
    "p2-aiml-alerts",
    "p3-backend-factory-map",
    "p4-backend-cause-finder",
]:
    sys.path.insert(0, str(ROOT / folder))

from simulator import FactorySimulator
from alert_engine import run_monitoring
from factory_map import FactoryMap
from backend.root_cause_engine import analyze_factory, get_sample_readings
from database.db_manager import FactoryDB


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Factory Intelligence",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# SESSION STATE
# =========================================================

# Initialize persistent SQLite storage.
if "factory_db" not in st.session_state:
    st.session_state.factory_db = FactoryDB()

# Initialize the simulator and continue VIN numbering from the database.
if "simulator" not in st.session_state:
    st.session_state.simulator = FactorySimulator()
    st.session_state.simulator.car_counter = (
        st.session_state.factory_db.get_latest_car_number()
    )

if "snapshot" not in st.session_state:
    st.session_state.snapshot = st.session_state.simulator.step()

# Save the first snapshot once per Streamlit session.
# This also handles an existing session that already has a snapshot.
if "initial_snapshot_saved" not in st.session_state:
    st.session_state.factory_db.save_simulation_tick(
        st.session_state.snapshot
    )
    st.session_state.initial_snapshot_saved = True

if "cycle" not in st.session_state:
    st.session_state.cycle = 1

if "scenario" not in st.session_state:
    st.session_state.scenario = "none"

if "history" not in st.session_state:
    st.session_state.history = []

if "factory_map" not in st.session_state:
    st.session_state.factory_map = FactoryMap()


# =========================================================
# DESIGN
# =========================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --glass: rgba(255,255,255,.055);
    --border: rgba(255,255,255,.10);
    --blue: #69baff;
    --cyan: #55e5ef;
    --text: #edf4ff;
    --muted: #91a3bd;
}

.stApp {
    background:
        radial-gradient(ellipse at 15% 5%, rgba(40,110,190,.19), transparent 42%),
        radial-gradient(ellipse at 90% 25%, rgba(104,75,190,.13), transparent 40%),
        linear-gradient(145deg,#080d19,#10182a 55%,#080d19);
    color: var(--text);
    font-family: Inter, sans-serif;
}

.block-container {
    max-width: 1600px;
    padding: 2rem 2.5rem 3rem;
}

[data-testid="stSidebar"] {
    background: rgba(10,18,34,.92);
    border-right: 1px solid var(--border);
}

[data-testid="stSidebar"] .block-container {
    padding: 1.5rem 1rem;
}

h1, h2, h3 {
    font-weight: 700 !important;
    letter-spacing: -.6px;
}

p, label {
    color: var(--muted);
}

[data-testid="stMetric"] {
    background: rgba(255,255,255,.055);
    border: 1px solid rgba(255,255,255,.11);
    border-radius: 20px;
    padding: 20px;
    transition: transform .25s ease;
}

[data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    border-color: rgba(105,186,255,.45);
}

.stButton > button {
    border-radius: 13px;
    border: 1px solid rgba(150,205,255,.25);
    background: linear-gradient(135deg,#347fd0,#485fc4);
    color: white;
    font-weight: 650;
    transition: all .25s ease;
}

.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(50,140,255,.2);
}

.stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,.035);
    border: 1px solid var(--border);
    border-radius: 15px;
    padding: 5px;
    gap: 5px;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 11px;
    padding: 10px 14px;
    font-weight: 600;
}

.stTabs [aria-selected="true"] {
    background: rgba(100,175,255,.17) !important;
    color: white !important;
}

[data-testid="stPlotlyChart"],
[data-testid="stDataFrame"] {
    border: 1px solid var(--border);
    border-radius: 18px;
    overflow: hidden;
}

hr {
    border-color: rgba(255,255,255,.10);
}

@media(max-width:768px) {
    .block-container { padding: 1rem; }
}

/* Hide Streamlit top toolbar */
[data-testid="stHeader"], [data-testid="stToolbar"] { display: none !important; }
.block-container { padding-top: 1rem !important; }
</style>
""", unsafe_allow_html=True)


# =========================================================
# LIVE DATA
# =========================================================

snapshot = st.session_state.snapshot
machines = snapshot["machines"]
buffers = snapshot["buffers"]

machine_df = pd.DataFrame(machines)
buffer_df = pd.DataFrame(buffers)


# =========================================================
# P3 FACTORY MAP INTEGRATION
# =========================================================

def update_factory_map(live_snapshot):
    """
    Transfer P1 simulator readings into P3's factory-map engine.

    P1 and P3 use the same machine IDs, but their stage layouts
    and machine descriptions are not identical.

    This integration maps telemetry by machine ID and calibrates
    P3 nominal cycle times using P1 target cycle times.
    """

    factory_map = st.session_state.factory_map

    for machine in live_snapshot["machines"]:

        machine_id = machine["id"]

        if machine_id not in factory_map.machines:
            continue

        target_cycle = float(machine["target_cycle"])
        actual_cycle = float(machine["cycle_time"])

        # Calibrate P3's nominal cycle to P1's target cycle.
        factory_map.machines[machine_id].nominal_cycle_s = target_cycle

        ratio = actual_cycle / max(target_cycle, 1)

        if machine["sensor_health"] != "OK":
            health = 25
            status = "degraded"

        elif ratio >= 1.40:
            health = 35
            status = "degraded"

        elif ratio >= 1.15:
            health = max(45, 100 - ((ratio - 1) * 100))
            status = "degraded"

        else:
            health = max(75, 100 - ((ratio - 1) * 100))
            status = "running"

        factory_map.update_machine(
            machine_id,
            cycle_time_s=actual_cycle,
            status=status,
            health=health,
        )

    # Convert P1 buffer IDs to P3 buffer IDs.
    buffer_mapping = {
        "BUF-1": "B1",
        "BUF-2": "B2",
        "BUF-3": "B3",
        "BUF-4": "B4",
        "BUF-5": "B5",
    }

    buffer_levels = {}

    for buffer in live_snapshot["buffers"]:
        p3_id = buffer_mapping.get(buffer["id"])

        if p3_id:
            buffer_levels[p3_id] = float(buffer["fill_percent"])

    factory_map.update_buffers(buffer_levels)

    return factory_map.snapshot()


# Synchronize P3 with the current P1 snapshot.
try:
    p3_snapshot = update_factory_map(snapshot)
    p3_error = None
except Exception as e:
    p3_snapshot = None
    p3_error = str(e)


# =========================================================
# HELPERS
# =========================================================

def machine_status(machine):

    if machine["sensor_health"] != "OK":
        return "WARNING"

    if machine["pass_fail"] == "FAIL":
        return "CRITICAL"

    if machine["cycle_time"] > machine["target_cycle"] * 1.15:
        return "WARNING"

    return "NORMAL"


def status_color(status):

    return {
        "NORMAL": "#22c55e",
        "WARNING": "#f59e0b",
        "CRITICAL": "#ef4444",
    }.get(status, "#64748b")


def get_monitoring_dataframe():

    rows = []

    for machine in machines:
        rows.append({
            "machine_name": machine["name"],
            "stage": machine["stage"],
            "temperature": machine["temp"],
            "processing_time": machine["cycle_time"],
            "output_per_hour": round(
                3600 / max(machine["cycle_time"], 1), 2
            ),
            "downtime_minutes": 0,
            "buffer_quantity": 0,
            "defect_count": (
                1 if machine["pass_fail"] == "FAIL" else 0
            ),
            "total_inspected": 1,
            "timestamp": snapshot["timestamp"],
        })

    return pd.DataFrame(rows)


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.markdown(
        '<div style="font-size:21px;font-weight:800;'
        'letter-spacing:-.7px;white-space:nowrap;">'
        '🏭 FACTORY INTELLIGENCE</div>',
        unsafe_allow_html=True,
    )

    st.caption("INDUSTRIAL CONTROL CENTRE")
    st.markdown("---")

    st.markdown("### SIMULATION CONTROL")

    scenario_options = {
        "Normal production": "none",
        "Welding failure": "welding_fault",
        "Sensor malfunction": "bad_sensor",
    }

    selected_scenario = st.selectbox(
        "Simulation scenario",
        list(scenario_options.keys()),
        index=list(scenario_options.values()).index(
            st.session_state.scenario
        ),
    )

    if st.button("▶ RUN PRODUCTION CYCLE", use_container_width=True):

        new_mode = scenario_options[selected_scenario]

        st.session_state.simulator.inject_fault(new_mode)
        st.session_state.scenario = new_mode

        # Keep VINs unique even if another session has saved newer records.
        st.session_state.simulator.car_counter = max(
            st.session_state.simulator.car_counter,
            st.session_state.factory_db.get_latest_car_number(),
        )

        new_snapshot = st.session_state.simulator.step()

        # Persist all machine readings and the completed vehicle.
        st.session_state.factory_db.save_simulation_tick(new_snapshot)

        st.session_state.snapshot = new_snapshot
        st.session_state.cycle += 1

        st.session_state.history.extend(new_snapshot["machines"])

        st.rerun()

    if st.button("↻ RESET SIMULATION", use_container_width=True):

        st.session_state.simulator = FactorySimulator()

        # Continue VIN numbering; resetting the simulation must not reset history.
        st.session_state.simulator.car_counter = (
            st.session_state.factory_db.get_latest_car_number()
        )

        st.session_state.snapshot = st.session_state.simulator.step()

        # Persist the first snapshot of the reset simulation.
        st.session_state.factory_db.save_simulation_tick(
            st.session_state.snapshot
        )

        st.session_state.factory_map = FactoryMap()

        st.session_state.cycle = 1
        st.session_state.scenario = "none"
        st.session_state.history = []

        st.rerun()

    st.markdown("---")
    st.markdown("### SYSTEM STATUS")

    st.success("SIMULATOR ONLINE")

    if p3_error:
        st.error("Factory map engine error")
    else:
        st.success("FACTORY MAP ENGINE ONLINE")

    st.info("SIMULATED DATA SOURCE")

    st.caption(f"Production cycle: {st.session_state.cycle}")
    st.caption(f"Scenario: {snapshot['fault_mode']}")

    st.markdown("---")
    st.caption("Beyond the Factory Floor")
    st.caption("Prototype using simulated production data")


# =========================================================
# HEADER
# =========================================================

st.markdown("# 🏭 FACTORY INTELLIGENCE")

st.caption(
    "Integrated Factory Monitoring • Production Flow • "
    "Predictive Analysis • Quality Control"
)

st.markdown("---")

statuses = [machine_status(m) for m in machines]

critical_count = statuses.count("CRITICAL")
warning_count = statuses.count("WARNING")
healthy_count = statuses.count("NORMAL")

k1, k2, k3, k4 = st.columns(4)

k1.metric("Machines monitored", len(machines))
k2.metric("Healthy machines", healthy_count)
k3.metric("Warnings / Critical", warning_count + critical_count)
k4.metric("Latest vehicle", snapshot["latest_car"]["status"])

st.caption(
    f"Production cycle: {st.session_state.cycle}  |  "
    f"Timestamp: {snapshot['timestamp']}  |  "
    f"Scenario: {snapshot['fault_mode']}"
)

st.markdown("---")


# =========================================================
# TABS
# =========================================================

tabs = st.tabs([
    "⌂ COMMAND CENTRE",
    "⚙ MACHINE MONITORING",
    "⇄ FACTORY FLOW",
    "⚠ ALERT CENTRE",
    "🧠 ROOT CAUSE",
    "📉 BOTTLENECKS",
    "✓ QUALITY CONTROL",
])


# =========================================================
# TAB 1: COMMAND CENTRE
# =========================================================

with tabs[0]:

    st.subheader("Production Line Performance")

    left, right = st.columns([1.6, 1])

    with left:

        fig = px.bar(
            machine_df,
            x="name",
            y="cycle_time",
            color="stage",
            title="Machine cycle time",
            labels={
                "name": "Machine",
                "cycle_time": "Cycle time (seconds)",
            },
            hover_data=["target_cycle", "temp", "vibration"],
        )

        fig.update_layout(
            template="plotly_dark",
            height=400,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_tickangle=-35,
            margin=dict(t=50, b=80),
        )

        st.plotly_chart(fig, width="stretch")

    with right:

        health_fig = go.Figure(go.Pie(
            labels=["Healthy", "Warning", "Critical"],
            values=[
                healthy_count,
                warning_count,
                critical_count,
            ],
            hole=.72,
            marker=dict(
                colors=["#22c55e", "#f59e0b", "#ef4444"]
            ),
        ))

        health_fig.update_layout(
            title="Factory health",
            template="plotly_dark",
            height=400,
            paper_bgcolor="rgba(0,0,0,0)",
        )

        st.plotly_chart(health_fig, width="stretch")

    st.subheader("Production Buffer Levels")

    fig = px.bar(
        buffer_df,
        x="id",
        y="fill_percent",
        color="fill_percent",
        color_continuous_scale=[
            "#22c55e",
            "#f59e0b",
            "#ef4444",
        ],
        title="Inter-stage buffer utilisation",
    )

    fig.update_layout(
        template="plotly_dark",
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )

    st.plotly_chart(fig, width="stretch")


# =========================================================
# TAB 2: MACHINE MONITORING
# =========================================================

with tabs[1]:

    st.subheader("Live Machine Monitoring")

    st.dataframe(
        machine_df,
        width="stretch",
        hide_index=True,
    )

    st.markdown("### Machine telemetry")

    selected = st.selectbox(
        "Select machine",
        [m["name"] for m in machines],
    )

    machine = next(
        item for item in machines
        if item["name"] == selected
    )

    a, b, c, d = st.columns(4)

    a.metric("Cycle time", f"{machine['cycle_time']} s")
    b.metric("Target cycle", f"{machine['target_cycle']} s")
    c.metric("Temperature", f"{machine['temp']} °C")
    d.metric("Vibration", machine["vibration"])

    status = machine_status(machine)

    if status == "CRITICAL":
        st.error("Critical machine condition detected.")

    elif status == "WARNING":
        st.warning("Machine requires attention.")

    else:
        st.success("Machine operating normally.")

    st.markdown("### Cycle time comparison")

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=machine_df["name"],
        y=machine_df["cycle_time"],
        name="Actual cycle",
        marker_color="#60a5fa",
    ))

    fig.add_trace(go.Scatter(
        x=machine_df["name"],
        y=machine_df["target_cycle"],
        name="Target cycle",
        mode="lines+markers",
        line=dict(color="#f59e0b", dash="dash"),
    ))

    fig.update_layout(
        template="plotly_dark",
        height=400,
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis_tickangle=-35,
    )

    st.plotly_chart(fig, width="stretch")


# =========================================================
# TAB 3: INTERACTIVE FACTORY FLOWCHART
# =========================================================

with tabs[2]:

    st.subheader("Interactive Production Flow")

    st.caption(
        "Hover over a machine to inspect its readings. "
        "Use the stage filter to highlight a production area."
    )

    stages = [
        "Stamping",
        "Body Welding",
        "Paint Shop",
        "Powertrain Assembly",
        "Final QA",
    ]

    stage_colors = {
        "Stamping": "#60a5fa",
        "Body Welding": "#22d3ee",
        "Paint Shop": "#a78bfa",
        "Powertrain Assembly": "#f59e0b",
        "Final QA": "#34d399",
    }

    stage_positions = {
        stage: i * 3.4
        for i, stage in enumerate(stages)
    }

    stage_filter = st.selectbox(
        "Highlight production stage",
        ["All stages"] + stages,
    )

    selected_machine = st.selectbox(
        "Inspect machine",
        ["None"] + [m["name"] for m in machines],
        key="flow_machine",
    )

    fig = go.Figure()

    for stage in stages:

        group = [
            m for m in machines
            if m["stage"] == stage
        ]

        x = stage_positions[stage]
        count = len(group)

        fig.add_shape(
            type="rect",
            x0=x - 1.1,
            x1=x + 1.1,
            y0=-0.7,
            y1=count * 1.05 + 0.6,
            line=dict(
                color=stage_colors[stage],
                width=1.5,
            ),
            fillcolor="rgba(255,255,255,0.035)",
            layer="below",
        )

        fig.add_annotation(
            x=x,
            y=count * 1.05 + 0.25,
            text=f"<b>{stage}</b>",
            showarrow=False,
            font=dict(
                size=13,
                color=stage_colors[stage],
            ),
        )

        for j, machine in enumerate(group):

            y = count * 0.95 - j * 0.95

            status = machine_status(machine)
            color = status_color(status)

            highlighted = (
                stage_filter == "All stages"
                or stage_filter == stage
            )

            opacity = 1 if highlighted else 0.18

            is_selected = machine["name"] == selected_machine

            fig.add_trace(go.Scatter(
                x=[x],
                y=[y],
                mode="markers+text",
                text=[machine["name"]],
                textposition="bottom center",
                textfont=dict(
                    size=10,
                    color="#edf4ff",
                ),
                marker=dict(
                    size=34 if is_selected else 25,
                    color=color,
                    opacity=opacity,
                    symbol="circle",
                    line=dict(
                        color="#ffffff",
                        width=2,
                    ),
                ),
                name=machine["name"],
                showlegend=False,
                hovertemplate=(
                    f"<b>{machine['name']}</b><br>"
                    f"Stage: {stage}<br>"
                    f"Status: {status}<br>"
                    f"Cycle: {machine['cycle_time']} s<br>"
                    f"Temperature: {machine['temp']} °C<br>"
                    f"Vibration: {machine['vibration']}<br>"
                    f"Sensor: {machine['sensor_health']}<br>"
                    f"Quality: {machine['pass_fail']}"
                    "<extra></extra>"
                ),
            ))

    for i in range(len(stages) - 1):

        x1 = stage_positions[stages[i]] + 1.15
        x2 = stage_positions[stages[i + 1]] - 1.15

        fig.add_annotation(
            x=x2,
            y=0.2,
            ax=x1,
            ay=0.2,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            text="",
            showarrow=True,
            arrowhead=3,
            arrowsize=1.4,
            arrowwidth=2,
            arrowcolor="#55e5ef",
        )

        fig.add_annotation(
            x=(x1 + x2) / 2,
            y=-0.35,
            text=f"BUFFER {i+1}",
            showarrow=False,
            font=dict(
                size=9,
                color="#91a3bd",
            ),
        )

    fig.update_layout(
        template="plotly_dark",
        height=620,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=40, b=30),
        showlegend=False,
        hoverlabel=dict(
            bgcolor="#17243a",
            font_size=12,
        ),
        xaxis=dict(
            visible=False,
            range=[-1.8, 15.5],
        ),
        yaxis=dict(
            visible=False,
            range=[-1.0, 5.5],
        ),
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config={
            "scrollZoom": True,
            "displayModeBar": True,
            "displaylogo": False,
        },
    )

    if selected_machine != "None":

        selected = next(
            m for m in machines
            if m["name"] == selected_machine
        )

        st.markdown("---")
        st.markdown("### Selected Machine Details")

        a, b, c, d = st.columns(4)

        a.metric("Machine ID", selected["id"])
        b.metric("Temperature", f"{selected['temp']} °C")
        c.metric("Cycle time", f"{selected['cycle_time']} s")
        d.metric("Vibration", selected["vibration"])

        st.write("Production stage:", selected["stage"])
        st.write("Sensor condition:", selected["sensor_health"])
        st.write("Quality result:", selected["pass_fail"])

    st.markdown("---")
    st.caption("🟢 Healthy    🟠 Warning    🔴 Critical")


# =========================================================
# TAB 4: ALERT CENTRE
# =========================================================

with tabs[3]:

    st.subheader("Alert and Warning Centre")

    monitoring_df = get_monitoring_dataframe()

    try:

        monitoring = run_monitoring(monitoring_df)
        summary = monitoring["summary"]

        st.markdown("### Monitoring engine summary")

        a, b, c = st.columns(3)

        a.metric(
            "Critical machines",
            summary["machines_critical"],
        )

        b.metric(
            "Warning machines",
            summary["machines_warning"],
        )

        c.metric(
            "Normal machines",
            summary["machines_normal"],
        )

        st.markdown("### Detected alerts")

        if not monitoring["active_alerts"].empty:

            st.dataframe(
                monitoring["active_alerts"],
                width="stretch",
                hide_index=True,
            )

        else:
            st.success(
                "No active alerts from the monitoring engine."
            )

        st.markdown("### Sensor validation")

        st.dataframe(
            monitoring["sensor_report"],
            width="stretch",
            hide_index=True,
        )

    except Exception as e:
        st.error(f"Monitoring engine error: {e}")


# =========================================================
# TAB 5: ROOT CAUSE ANALYSIS
# =========================================================

with tabs[4]:

    st.subheader("Root Cause Analysis")

    st.caption(
        "Rule-based and statistical analysis of simulated readings."
    )

    scenario = st.selectbox(
        "Analysis scenario",
        ["weld_failure", "healthy"],
        format_func=lambda x: (
            "Welding failure"
            if x == "weld_failure"
            else "Healthy production"
        ),
    )

    if st.button("RUN ROOT CAUSE ANALYSIS"):

        try:

            result = analyze_factory(
                get_sample_readings(mode=scenario)
            )

            ranking = result["ranking"]

            st.markdown("### Most likely root cause")

            if result["top_cause"]:
                st.error(
                    f"Likely cause: {result['top_cause']}"
                )
            else:
                st.success(
                    "No major root cause identified."
                )

            st.markdown("### Machine risk ranking")

            st.dataframe(
                ranking,
                width="stretch",
                hide_index=True,
            )

            fig = px.bar(
                ranking.head(10),
                x="machine",
                y="risk_score",
                color="risk_level",
                title="Machine risk score",
                hover_data=["reasons"],
            )

            fig.update_layout(
                template="plotly_dark",
                height=380,
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis_tickangle=-30,
            )

            st.plotly_chart(fig, width="stretch")

        except Exception as e:
            st.error(f"Root cause analysis error: {e}")


# =========================================================
# TAB 6: P3 BOTTLENECK DETECTION
# =========================================================

with tabs[5]:

    st.subheader("Production Bottleneck Detection")

    st.caption(
        "Powered by P3 FactoryMap: machine capacity, buffer "
        "utilisation, bottleneck scoring and cascade simulation."
    )

    if p3_error:

        st.error(f"Factory map engine error: {p3_error}")

    else:

        bottleneck = p3_snapshot["bottleneck"]
        p3_summary = p3_snapshot["summary"]

        # -------------------------------------------------
        # THROUGHPUT SUMMARY
        # -------------------------------------------------

        st.markdown("### Production throughput")

        a, b, c, d = st.columns(4)

        a.metric(
            "Current throughput",
            f"{p3_summary['current_throughput_cars_per_min']} cars/min",
        )

        b.metric(
            "Steady-state throughput",
            f"{p3_summary['steady_state_throughput_cars_per_min']} cars/min",
        )

        c.metric(
            "Demand achieved",
            f"{p3_summary['steady_state_pct_of_demand']}%",
        )

        d.metric(
            "Projected hourly loss",
            f"{p3_summary['projected_loss_cars_per_hour']} cars",
        )

        st.markdown("---")

        # -------------------------------------------------
        # PRIMARY BOTTLENECK
        # -------------------------------------------------

        st.markdown("### Detected bottleneck")

        if bottleneck:

            machine_id = bottleneck.get("machine_id", "Unknown")
            machine_name = bottleneck.get("machine_name", machine_id)
            score = bottleneck.get("score")

            st.error(
                f"Primary bottleneck detected: {machine_name} ({machine_id})"
            )

            a, b, c = st.columns(3)

            a.metric("Machine", machine_name)

            if score is not None:
                b.metric("Bottleneck score", f"{score:.3f}")
            else:
                b.metric("Bottleneck score", "Available in engine")

            b_value = bottleneck.get("cycle_ratio")

            if b_value is not None:
                c.metric("Cycle ratio", f"{b_value:.2f}x")
            else:
                c.metric("Detection", "P3 engine")

            with st.expander("Bottleneck details"):
                st.json(bottleneck)

        else:

            st.success(
                "No significant bottleneck detected by the P3 engine."
            )

        # -------------------------------------------------
        # MACHINE CAPACITY AND HEALTH
        # -------------------------------------------------

        st.markdown("---")
        st.markdown("### Factory machine status")

        p3_nodes = pd.DataFrame(p3_snapshot["nodes"])

        if not p3_nodes.empty:

            display_columns = [
                "id",
                "name",
                "stage_name",
                "health",
                "status",
                "flow_state",
                "cycle_time_s",
                "rate_cars_per_min",
                "impact_role",
            ]

            st.dataframe(
                p3_nodes[display_columns],
                width="stretch",
                hide_index=True,
            )

            fig = px.bar(
                p3_nodes,
                x="name",
                y="cycle_ratio",
                color="impact_role",
                title="Machine cycle ratio",
                hover_data=[
                    "health",
                    "status",
                    "stage_name",
                ],
            )

            fig.add_hline(
                y=1,
                line_dash="dash",
                line_color="#f59e0b",
                annotation_text="Target cycle",
            )

            fig.update_layout(
                template="plotly_dark",
                height=380,
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis_tickangle=-35,
            )

            st.plotly_chart(fig, width="stretch")

        # -------------------------------------------------
        # BUFFER ANALYSIS
        # -------------------------------------------------

        st.markdown("---")
        st.markdown("### Buffer utilisation and predictions")

        p3_buffers = pd.DataFrame(p3_snapshot["buffers"])

        if not p3_buffers.empty:

            st.dataframe(
                p3_buffers,
                width="stretch",
                hide_index=True,
            )

            fig = px.bar(
                p3_buffers,
                x="id",
                y="level_pct",
                color="status",
                title="P3 buffer fill levels",
                hover_data=[
                    "name",
                    "trend",
                    "minutes_to_full",
                    "minutes_to_empty",
                ],
            )

            fig.add_hline(
                y=80,
                line_dash="dash",
                line_color="#f59e0b",
                annotation_text="High utilisation",
            )

            fig.update_layout(
                template="plotly_dark",
                height=330,
                paper_bgcolor="rgba(0,0,0,0)",
            )

            st.plotly_chart(fig, width="stretch")

        # -------------------------------------------------
        # CASCADE PROPAGATION
        # -------------------------------------------------

        st.markdown("---")
        st.markdown("### Predicted production disruption")

        timeline = p3_snapshot["cascade_timeline"]

        a, b, c = st.columns(3)

        a.metric(
            "Upstream machines affected",
            p3_summary["upstream_machines_affected"],
        )

        b.metric(
            "Downstream machines affected",
            p3_summary["downstream_machines_affected"],
        )

        first_impact = p3_summary["first_impact_minutes"]

        c.metric(
            "First predicted impact",
            (
                f"{first_impact} min"
                if first_impact is not None
                else "No predicted impact"
            ),
        )

        if timeline:

            timeline_df = pd.DataFrame(timeline)

            st.markdown("#### Cascade timeline")

            st.dataframe(
                timeline_df,
                width="stretch",
                hide_index=True,
            )

            fig = px.bar(
                timeline_df,
                x="machine_name",
                y="minutes_until_impact",
                color="impact_type",
                title="Predicted time until production impact",
                hover_data=[
                    "reason",
                    "trigger_buffer",
                    "cause_machine",
                    "severity",
                ],
            )

            fig.update_layout(
                template="plotly_dark",
                height=380,
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis_tickangle=-35,
            )

            st.plotly_chart(fig, width="stretch")

        else:

            st.success(
                "No upstream blocking or downstream starvation "
                "is currently predicted by the P3 simulation."
            )

        # -------------------------------------------------
        # TRANSPARENCY
        # -------------------------------------------------

        with st.expander("About this bottleneck analysis"):

            st.write(
                "The P3 engine calculates production capacity using "
                "machine cycle times and buffer levels. It identifies "
                "the limiting machine, estimates throughput, and "
                "simulates upstream blocking and downstream starvation."
            )

            st.warning(
                "P1 and P3 have different stage definitions. "
                "Machine telemetry is mapped by machine ID, and P3 "
                "nominal cycle times are calibrated to P1 targets. "
                "P3's six-stage topology remains an approximation "
                "of the P1 production layout."
            )

            st.caption(
                "All values are generated from simulated production data. "
                "Predictions are model outputs, not real factory measurements."
            )


# =========================================================
# TAB 7: PRODUCT QUALITY CONTROL
# =========================================================

with tabs[6]:

    st.subheader("Product Quality Control")

    cars = snapshot["recent_cars"]

    if cars:

        cars_df = pd.DataFrame(cars)

        total = len(cars_df)
        passed = (cars_df["status"] == "PASS").sum()
        failed = (cars_df["status"] == "FAIL").sum()

        a, b, c = st.columns(3)

        a.metric("Vehicles inspected", total)
        b.metric("Passed", passed)
        c.metric("Failed", failed)

        st.markdown("### Recent vehicle inspection results")

        st.dataframe(
            cars_df[
                ["car_id", "tick", "timestamp", "status"]
            ],
            width="stretch",
            hide_index=True,
        )

        st.markdown("### Defect details")

        defects = []

        for car in cars:

            for defect in car.get("failed_at", []):

                defects.append({
                    "Vehicle": car["car_id"],
                    "Machine": defect["machine_name"],
                    "Stage": defect["stage"],
                    "Reason": defect["reason"],
                })

        if defects:

            st.dataframe(
                pd.DataFrame(defects),
                width="stretch",
                hide_index=True,
            )

        else:

            st.success(
                "No product defects detected in recent vehicles."
            )

        quality_fig = go.Figure(go.Pie(
            labels=["Passed", "Failed"],
            values=[passed, failed],
            hole=.65,
            marker=dict(
                colors=["#22c55e", "#ef4444"]
            ),
        ))

        quality_fig.update_layout(
            title="Vehicle quality distribution",
            template="plotly_dark",
            height=350,
            paper_bgcolor="rgba(0,0,0,0)",
        )

        st.plotly_chart(
            quality_fig,
            width="stretch",
        )

    else:

        st.info("Waiting for vehicle inspection data.")


# =========================================================
# FOOTER
# =========================================================

st.markdown("---")

st.caption(
    "FACTORY INTELLIGENCE | Beyond the Factory Floor | "
    "Prototype using simulated production data"
)