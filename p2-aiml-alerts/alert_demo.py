"""
alert_demo.py - Streamlit demo for P2: Warning & Critical Alerts

Run standalone :  streamlit run alert_demo.py
Embed in the main app:
    from p2_alerts.alert_demo import render_alert_dashboard
    render_alert_dashboard(df)        # df = teammate's machine readings DataFrame
"""
import copy

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:                                    # works as package import or from this folder
    from .alert_engine import (DEFAULT_CONFIG, SENSOR_PARAMS, LABELS, get_limits, run_monitoring)
    from .sample_data import generate_sample_data
except ImportError:
    from alert_engine import (DEFAULT_CONFIG, SENSOR_PARAMS, LABELS, get_limits, run_monitoring)
    from sample_data import generate_sample_data

ICON = {"NORMAL": "🟢", "WARNING": "🟡", "CRITICAL": "🔴"}
COLOR = {"NORMAL": "#2ecc71", "WARNING": "#f5b301", "CRITICAL": "#e74c3c",
         "VALID": "#2ecc71", "INVALID": "#e74c3c"}
RANK = {"CRITICAL": 0, "WARNING": 1, "NORMAL": 2}

CSS = """
<style>
.block-container {padding-top: 1.6rem;}
.hero {background: linear-gradient(90deg,#0f2027,#203a43,#2c5364); color: white;
       padding: 18px 24px; border-radius: 12px; margin-bottom: 14px;}
.hero h2 {margin: 0; font-size: 1.6rem;}
.hero p {margin: 4px 0 0 0; opacity: .85;}
div[data-testid="stMetric"] {background: rgba(128,128,128,.10); padding: 10px 14px; border-radius: 10px;}
</style>
"""


def _num(frame, cols, nd=1):
    frame = frame.copy()
    for c in cols:
        if c in frame.columns:
            frame[c] = frame[c].round(nd)
    return frame


def render_alert_dashboard(df, config=None, key_prefix="p2"):
    """Draw the whole alert dashboard for a DataFrame of machine readings."""
    res = run_monitoring(df, config)
    cfg = config or DEFAULT_CONFIG
    s, status, alerts, active = res["summary"], res["status"], res["alerts"], res["active_alerts"]
    clean, report, defects = res["clean_data"], res["sensor_report"], res["defects"]
    if status.empty:
        st.warning("No data to analyse.")
        return res
    if res["missing_columns"]:
        st.info("Columns missing or empty in the input (checks skipped): "
                + ", ".join(res["missing_columns"]))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Machines monitored", s["machines"])
    c2.metric("🔴 Critical now", s["machines_critical"])
    c3.metric("🟡 Warning now", s["machines_warning"])
    c4.metric("Alerts raised (W / C)", f"{s['history_warning']} / {s['history_critical']}")
    c5.metric("Invalid sensor readings", s["sensor_invalid"])

    tabs = st.tabs(["🏭 Machine Status", "🛠 Recommended Actions", "📜 Alert History",
                    "📡 Sensor Validation", "📈 Defect Trend", "🔍 Abnormal Readings", "🧠 AI Methods"])

    # ---- 1. Machine status ------------------------------------------------
    with tabs[0]:
        show = status.copy()
        show["Status"] = show["status"].map(lambda x: f"{ICON[x]} {x}")
        show["_r"] = show["status"].map(RANK)
        show = show.sort_values(["_r", "stage"], kind="mergesort")
        show = _num(show, ["temperature", "processing_time", "output_per_hour",
                           "downtime_minutes", "buffer_quantity", "defect_rate_pct"])
        table = show[["Status", "machine_name", "stage", "issue_type", "top_issue", "active_issues",
                      "temperature", "processing_time", "output_per_hour", "downtime_minutes",
                      "buffer_quantity", "defect_rate_pct", "sensor_status"]]
        table.columns = ["Status", "Machine", "Stage", "Issue type", "Main issue", "Open issues",
                         "Temp °C", "Proc. time s", "Output/h", "Downtime min", "Buffer",
                         "Defect %", "Sensor"]
        st.dataframe(table, hide_index=True)
        left, right = st.columns(2)
        counts = status["status"].value_counts().reindex(["NORMAL", "WARNING", "CRITICAL"], fill_value=0)
        fig = px.bar(x=counts.index, y=counts.values, color=counts.index, color_discrete_map=COLOR,
                     labels={"x": "Status", "y": "Machines"}, title="Machines by current status")
        fig.update_layout(showlegend=False, height=320)
        left.plotly_chart(fig, key=f"{key_prefix}_status_bar")
        if len(alerts):
            per = alerts.groupby(["stage", "severity"]).size().reset_index(name="alerts")
            fig = px.bar(per, x="stage", y="alerts", color="severity", color_discrete_map=COLOR,
                         title="Alerts raised by production stage")
            fig.update_layout(height=320)
            right.plotly_chart(fig, key=f"{key_prefix}_stage_bar")

    # ---- 2. Recommended actions -------------------------------------------
    with tabs[1]:
        if active.empty:
            st.success("No open alerts - every machine is operating normally.")
        else:
            st.caption("Open alerts at the latest reading, most severe first.")
            ordered = active.assign(_r=active["severity"].map(RANK)).sort_values("_r", kind="mergesort")
            for _, a in ordered.iterrows():
                body = (f"**{a['machine_name']}** ({a['stage']}) · {a['category'].title()} · "
                        f"`{a['parameter']}`\n\n{a['message']}\n\n"
                        f"- **Current reading:** {a['current_reading']}\n"
                        f"- **Violated condition:** {a['threshold']}\n"
                        f"- **Recommended action:** {a['recommended_action']}")
                if a["sensor_note"]:
                    body += f"\n- ⚠️ {a['sensor_note']}"
                (st.error if a["severity"] == "CRITICAL" else st.warning)(body, icon="🔴" if a["severity"] == "CRITICAL" else "🟡")

    # ---- 3. Alert history --------------------------------------------------
    with tabs[2]:
        if alerts.empty:
            st.info("No alerts have been generated yet.")
        else:
            f1, f2, f3 = st.columns(3)
            sev = f1.multiselect("Severity", ["CRITICAL", "WARNING"], default=["CRITICAL", "WARNING"],
                                 key=f"{key_prefix}_h_sev")
            cat = f2.multiselect("Category", sorted(alerts["category"].unique()),
                                 default=sorted(alerts["category"].unique()), key=f"{key_prefix}_h_cat")
            mach = f3.multiselect("Machine", sorted(alerts["machine_name"].unique()), key=f"{key_prefix}_h_mach")
            view = alerts[alerts["severity"].isin(sev) & alerts["category"].isin(cat)]
            if mach:
                view = view[view["machine_name"].isin(mach)]
            view = view.iloc[::-1]       # newest first
            st.caption(f"{len(view)} alert(s). Repeated alerts for the same ongoing issue are suppressed.")
            st.dataframe(view[["alert_id", "timestamp", "machine_name", "stage", "severity", "category",
                               "parameter", "message", "current_reading", "threshold",
                               "recommended_action", "detection_method", "event"]], hide_index=True)
            st.download_button("⬇ Download alerts (CSV)", view.to_csv(index=False).encode("utf-8"),
                               "alerts.csv", "text/csv", key=f"{key_prefix}_dl")

    # ---- 4. Sensor validation ---------------------------------------------
    with tabs[3]:
        a, b, c = st.columns(3)
        a.metric("🟢 VALID readings", s["sensor_valid"])
        b.metric("🟡 WARNING readings", s["sensor_warning"])
        c.metric("🔴 INVALID readings", s["sensor_invalid"])
        st.caption("INVALID = missing/negative/impossible value (treated as a sensor fault, ignored by the machine "
                   "alert rules). WARNING = sudden jump or frozen value (kept, but flagged to verify).")
        flagged = report[report["sensor_status"] != "VALID"]
        if flagged.empty:
            st.success("All sensor readings passed validation.")
        else:
            by = flagged.groupby(["machine_name", "sensor_status"]).size().reset_index(name="readings")
            fig = px.bar(by, x="machine_name", y="readings", color="sensor_status",
                         color_discrete_map=COLOR, title="Flagged readings per machine")
            fig.update_layout(height=320)
            st.plotly_chart(fig, key=f"{key_prefix}_sensor_bar")
            st.dataframe(flagged.iloc[::-1][["timestamp", "machine_name", "sensor_status",
                                             "flagged_parameters", "reason"]], hide_index=True)

    # ---- 5. Defect trend ---------------------------------------------------
    with tabs[4]:
        if defects.empty:
            st.info("defect_count and total_inspected are needed for defect analysis.")
        else:
            latest = (defects.sort_values("timestamp").groupby("machine_name").tail(1)
                      .sort_values("recent_rate_pct", ascending=False))
            default = list(latest.head(3)["machine_name"])
            pick = st.multiselect("Machines to plot", list(latest["machine_name"]), default=default,
                                  key=f"{key_prefix}_d_pick")
            if pick:
                plot = defects[defects["machine_name"].isin(pick)]
                fig = px.line(plot, x="timestamp", y="recent_rate_pct", color="machine_name", markers=True,
                              labels={"recent_rate_pct": "Defect rate % (last 3 readings)", "timestamp": ""},
                              title="Defect rate over time")
                d = cfg["defect"]
                fig.add_hline(y=d["warning_pct"], line_dash="dash", line_color=COLOR["WARNING"],
                              annotation_text="Warning limit")
                fig.add_hline(y=d["critical_pct"], line_dash="dash", line_color=COLOR["CRITICAL"],
                              annotation_text="Critical limit")
                fig.update_layout(height=420)
                st.plotly_chart(fig, key=f"{key_prefix}_defect_line")
            tbl = latest[["machine_name", "stage", "recent_rate_pct", "previous_rate_pct", "trend",
                          "severity", "reason"]]
            tbl.columns = ["Machine", "Stage", "Recent %", "Previous %", "Trend", "Severity", "Why flagged"]
            st.dataframe(tbl, hide_index=True)

    # ---- 6. Abnormal readings ---------------------------------------------
    with tabs[5]:
        machine_alerts = alerts[alerts["category"] == "MACHINE"] if len(alerts) else alerts
        if len(machine_alerts):
            per = machine_alerts.groupby(["machine_name", "parameter"]).size().reset_index(name="abnormal")
            fig = px.bar(per, x="machine_name", y="abnormal", color="parameter",
                         title="Abnormal readings per machine (machine-condition alerts)")
            fig.update_layout(height=340)
            st.plotly_chart(fig, key=f"{key_prefix}_abn_bar")
        else:
            st.info("No abnormal machine readings detected.")
        m1, m2 = st.columns(2)
        machine = m1.selectbox("Machine", list(status["machine_name"]), key=f"{key_prefix}_r_m")
        params = [p for p in SENSOR_PARAMS if clean[p].notna().any()]
        param = m2.selectbox("Parameter", params, key=f"{key_prefix}_r_p",
                             format_func=lambda p: f"{LABELS[p][0]} ({LABELS[p][1]})")
        series = clean[clean["machine_name"] == machine][["timestamp", param, "sensor_status"]]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=series["timestamp"], y=series[param], mode="lines+markers",
                                 name=LABELS[param][0], connectgaps=False))
        if param in ("temperature", "downtime_minutes"):
            lim = get_limits(cfg, machine, param)
            fig.add_hline(y=lim["warning"], line_dash="dash", line_color=COLOR["WARNING"], annotation_text="Warning")
            fig.add_hline(y=lim["critical"], line_dash="dash", line_color=COLOR["CRITICAL"], annotation_text="Critical")
        if len(alerts):
            marks = alerts[(alerts["machine_name"] == machine) & (alerts["parameter"] == param)]
            marks = marks.merge(series[["timestamp", param]], on="timestamp", how="left")
            for sev_name, grp in marks.groupby("severity"):
                fig.add_trace(go.Scatter(x=grp["timestamp"], y=grp[param], mode="markers",
                                         name=f"{sev_name} alert", marker=dict(size=14, symbol="x",
                                         color=COLOR[sev_name], line=dict(width=2))))
        bad = series[series["sensor_status"] == "INVALID"]
        if len(bad):
            fig.add_trace(go.Scatter(x=bad["timestamp"], y=[series[param].min()] * len(bad), mode="markers",
                                     name="Invalid sensor reading (removed)",
                                     marker=dict(size=10, symbol="diamond-open", color=COLOR["INVALID"])))
        fig.update_layout(title=f"{machine} - {LABELS[param][0]}", height=420)
        st.plotly_chart(fig, key=f"{key_prefix}_read_line")
        mine = alerts[alerts["machine_name"] == machine] if len(alerts) else alerts
        if len(mine):
            st.dataframe(mine.iloc[::-1][["timestamp", "severity", "parameter", "message",
                                          "current_reading", "threshold", "recommended_action"]],
                         hide_index=True)

    # ---- 7. AI methods ------------------------------------------------------
    with tabs[6]:
        st.markdown("""
**What runs inside this module (no trained ML model):**

| Layer | Technique | Type |
|---|---|---|
| Hard limits | Temperature / downtime thresholds | Rule-based |
| Relative limits | Output / processing time vs. the machine's own baseline (median of first 10 readings) | Rule-based |
| Anomaly detection | Rolling **Z-score**: `z = (x - mean) / std` over the last 24 readings, flag if \\|z\\| ≥ 4 | Statistical |
| Trend detection | Least-squares line over the last 6 readings (`numpy.polyfit`) | Statistical |
| Defect trend | Recent vs. previous pooled defect rate + **two-proportion z-test** | Statistical |
| Sensor validation | Missing / negative / range / jump / frozen-value checks | Rule-based |
| De-duplication | Alert only when an issue is new or gets worse | Rule-based |

Sensor faults are handled **before** machine alerts, so a broken sensor is reported as a sensor problem
and not as a machine failure. All data here is **simulated**.
""")
    return res


def main():
    st.set_page_config(page_title="Factory Alert Monitor", page_icon="🏭", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="hero"><h2>🏭 Beyond the Factory Floor - Alert Monitor</h2>'
                '<p>P2: Warning & Critical alerts · sensor validation · rising defect detection '
                '(simulated data)</p></div>', unsafe_allow_html=True)

    st.sidebar.header("Data")
    source = st.sidebar.radio("Source", ["Simulated factory data", "Upload CSV"])
    if source == "Simulated factory data":
        hours = st.sidebar.slider("Hours of history", 30, 96, 48)
        seed = st.sidebar.number_input("Random seed", 0, 9999, 42)
        df = generate_sample_data(hours=hours, seed=int(seed), end_time="2026-11-17 07:00")
    else:
        up = st.sidebar.file_uploader("CSV with the machine columns", type="csv")
        if up is None:
            st.info("Upload a CSV with columns: machine_name, temperature, processing_time, output_per_hour, "
                    "downtime_minutes, buffer_quantity, defect_count, total_inspected, timestamp.")
            st.stop()
        df = pd.read_csv(up)

    if "timestamp" in df.columns:
        df = df.assign(timestamp=pd.to_datetime(df["timestamp"], errors="coerce")).sort_values(
            "timestamp", kind="mergesort")
    max_n = int(df.groupby("machine_name").size().max()) if "machine_name" in df.columns and len(df) else len(df)
    if max_n > 12:
        step = st.sidebar.slider("Replay: readings per machine", 12, max_n, max_n,
                                 help="Drag left to replay the factory at an earlier time.")
        df = df.groupby("machine_name", sort=False).head(step) if "machine_name" in df.columns else df.head(step)

    st.sidebar.header("Thresholds")
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    z = st.sidebar.slider("Z-score threshold", 2.0, 6.0, float(cfg["zscore"]["threshold"]), 0.5)
    dw = st.sidebar.number_input("Defect WARNING %", 0.5, 20.0, float(cfg["defect"]["warning_pct"]), 0.5)
    dc = st.sidebar.number_input("Defect CRITICAL %", 1.0, 50.0, float(cfg["defect"]["critical_pct"]), 0.5)
    tw = st.sidebar.number_input("Default temperature WARNING °C", 20.0, 300.0,
                                 float(cfg["limits"]["temperature"]["warning"]), 1.0)
    tc = st.sidebar.number_input("Default temperature CRITICAL °C", 30.0, 400.0,
                                 float(cfg["limits"]["temperature"]["critical"]), 1.0)
    cfg["zscore"]["threshold"] = z
    cfg["defect"].update(warning_pct=dw, critical_pct=max(dc, dw))
    cfg["limits"]["temperature"].update(warning=tw, critical=max(tc, tw))
    st.sidebar.caption("Curing Oven, Engine Test and Paint Booth keep their own temperature limits.")

    render_alert_dashboard(df, cfg)


if __name__ == "__main__":
    main()
