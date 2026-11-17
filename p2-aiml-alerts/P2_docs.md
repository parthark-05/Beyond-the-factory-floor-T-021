# P2 – Warning & Critical Alerts: Docs, Slide, Judge Q&A

## 1. File structure
```
beyond-the-factory-floor/          (your team repo)
├── requirements.txt               (add: streamlit pandas numpy plotly)
├── app.py                         (main Streamlit app – not touched)
└── p2_alerts/
    ├── __init__.py                (empty; lets the main app import the module)
    ├── alert_engine.py            (backend: validation, alerts, defect trend, anomaly detection)
    ├── alert_demo.py              (standalone Streamlit demo + render_alert_dashboard())
    └── sample_data.py             (simulated readings with injected faults)
```

## 5. Install (Git Bash)
```bash
cd beyond-the-factory-floor
python -m venv .venv
source .venv/Scripts/activate          # Windows Git Bash
pip install streamlit pandas numpy plotly
```

## 6. Run and test
```bash
cd p2_alerts
python alert_engine.py                 # backend self-check: prints counts + machine status
python sample_data.py                  # writes sample_machine_data.csv
streamlit run alert_demo.py            # opens http://localhost:8501
```
What you should see with the default seed (42): 17 machines, **4 CRITICAL** (Weld Robot 2 temperature/defects,
Paint Booth defects, Curing Oven downtime, Trim Line output), Gearbox Line **WARNING** (processing time rising),
5 INVALID + 3 WARNING sensor readings on Draw Press / Wheel Fit / Vision Check.
Use the sidebar "Replay" slider to watch Weld Robot 2 go NORMAL → WARNING → CRITICAL.
Upload your own CSV with the same column names to test teammate data.

Quick code test:
```python
from alert_engine import run_monitoring
from sample_data import generate_sample_data
r = run_monitoring(generate_sample_data())
print(r["summary"]); print(r["alerts"].head())
```

## 7. How the logic works
Order of processing: **validate sensors → judge each machine → defect trend → de-duplicate**.

1. **Sensor validation** (`validate_sensors`) – per reading, per machine:
   missing/non-numeric → INVALID; negative → INVALID; above a realistic maximum (e.g. 999 °C) → INVALID;
   defects > inspected → INVALID; jump > 35 % *and* > 15 °C vs previous valid value → WARNING;
   same temperature/processing time 4 times in a row → WARNING (frozen sensor); duplicate timestamp → WARNING.
   INVALID values are **removed (NaN)** so they never trigger a machine alert; instead a separate SENSOR alert is raised.
2. **Threshold rules** – temperature and downtime have WARNING/CRITICAL limits (per-machine overrides, e.g. Curing Oven 195/210 °C).
   Output and processing time are compared with the machine's own **baseline** (median of its first 10 valid readings):
   output ≤ 85 % → WARNING, ≤ 60 % → CRITICAL; processing time ≥ 115 % → WARNING, ≥ 140 % → CRITICAL.
   Buffer ≥ 80 % → WARNING, ≥ 95 % → CRITICAL (blocked downstream), ≤ 5 % → WARNING (starved).
3. **Rolling Z-score** – `z = (x − mean) / std` using the previous 24 readings (needs ≥ 12). |z| ≥ 4 in the "bad" direction → WARNING.
   Catches sudden unusual values that are still under the hard limits.
4. **Trend detection** – a least-squares line over the last 6 readings. If temperature/processing time rises
   (or output falls) ≥ 6 % across the window and ≥ 4 of 5 steps agree → WARNING ("drifting before it breaks").
5. **Defect rate** – `defect_rate = defect_count / total_inspected × 100`. "Recent" = pooled rate of last 3 readings,
   "previous" = pooled rate of the 6 before. ≥ 3 % → WARNING, ≥ 6 % → CRITICAL. A rise (≥ 1.5× and ≥ 0.5 pp) also raises a WARNING
   **only if a two-proportion z-test says it is bigger than random noise** (z ≥ 3).
6. **De-duplication** – alerts are created only when an issue is NEW or ESCALATED (WARNING → CRITICAL). An issue closes after
   2 normal readings. No peeking at future data: each reading is judged using only data up to that time.
Priority per parameter: threshold > Z-score > trend (one finding per parameter).

Honest note: with random noise a few stray WARNINGs can still appear (e.g. one z-score hit in 800 checks); they are
single, de-duplicated and explainable – raise the Z-score threshold in the sidebar to reduce them.

## 8. "AI Methods Used" slide content

**Title: Lightweight Explainable Anomaly Detection (no black box)**

- **Rule-based logic:** WARNING/CRITICAL thresholds, baseline-ratio rules, sensor validation, alert de-duplication.
- **Statistical anomaly detection:** rolling Z-score (distance from recent normal in standard deviations).
- **Statistical trend detection:** least-squares slope over a short window; two-proportion z-test for defect-rate rises.
- **Machine learning: not used.** No model is trained – we have no labelled failure data and everything is simulated.
- **Why these methods:** explainable (every alert states the reading, the rule, the threshold and an action), instant to run,
  no training data needed, robust enough for a 4-hour prototype.
- **How abnormal readings are found:** first validate the sensor, then compare each reading to limits, to the machine's own baseline,
  to its recent average (Z-score) and to its recent direction (trend).
- **How rising defects are found:** recent vs previous pooled defect rate + significance test + warning/critical limits.
- **WARNING vs CRITICAL:** WARNING = approaching limit / drifting / unusual. CRITICAL = hard limit crossed, large output loss, excessive downtime, dangerous defect rate.
- **Future with real factory data:** Isolation Forest / autoencoders for multivariate anomalies, per-machine learned thresholds,
  predictive maintenance (remaining useful life), CUSUM/EWMA control charts, alert-feedback loop from operators, real IoT (MQTT/OPC-UA) ingestion.

## 9. Judges' technical questions (with answers)

1. **Is this really AI or just rule-based automation?**
   Mostly rule-based plus statistical anomaly detection (Z-score, trend fitting, significance test). It is not machine learning – nothing is trained. We chose explainable statistics because we have no labelled failure data; the design is ready to add an ML model later.
2. **How do you decide Warning vs Critical?**
   Warning = approaching a limit, a steady drift, or a statistically unusual value. Critical = a hard limit crossed (e.g. temperature ≥ 90 °C), output ≤ 60 % of baseline, downtime ≥ 25 min, defect rate ≥ 6 %. All limits live in `DEFAULT_CONFIG` and are adjustable.
3. **How do you detect abnormal sensor readings?**
   Validation rules: missing, negative, outside a realistic range, defects > inspected, sudden jump vs previous valid value, frozen value repeated 4 times, duplicate timestamps. Statistical anomalies (Z-score) are checked only on readings that pass validation.
4. **How do you avoid false positives?**
   Sensor faults are removed before machine rules; per-machine baselines and limit overrides; Z-score threshold 4 with a minimum of 12 history points and a std floor; trend needs 4 of 5 steps in the same direction; defect rises need a z-test; alerts are de-duplicated and need 2 normal readings to clear.
5. **How do you identify a rising defect rate?**
   Compute rate = defects / inspected × 100, pool the last 3 readings (recent) and the 6 before (previous). Rising if recent ≥ 1.5× previous, up ≥ 0.5 percentage points and the two-proportion z-test ≥ 3. Limits 3 % / 6 % give WARNING / CRITICAL.
6. **What happens if a sensor sends incorrect data?**
   The reading is marked INVALID or WARNING with a reason, an invalid value is set to NaN and ignored by machine rules, and a separate SENSOR alert tells operators to check the sensor. So a broken sensor is not reported as a machine failure.
7. **How would this work with real IoT sensors?**
   Sensors publish via MQTT/OPC-UA to a gateway/database; we read batches or a stream into the same DataFrame columns and call `run_monitoring`. Thresholds would be calibrated from real data and timestamps would drive staleness checks. (Today it is simulated – no real sensors are connected.)
8. **Why a Z-score?**
   It is simple, needs no training, adapts to each machine's own normal level and noise, and is easy to explain: "this reading is 4 standard deviations from the recent average". It is a standard first method in statistical process control.
9. **Limitations of the Z-score?**
   Assumes roughly normal data, uses one variable at a time, and adapts to slow drifts (the rolling window slowly "accepts" the drift) – that is why we add a trend check and absolute limits.
10. **How would you scale to hundreds of machines?**
    The logic is per machine, so it parallelises (group by machine, run in workers). Use a stream processor (Kafka + incremental rolling statistics) instead of re-scanning DataFrames, store config per machine type, and keep only a rolling window in memory.
11. **How could ML improve the system?**
    With labelled history: Isolation Forest or autoencoders for multi-sensor anomalies, a classifier/regressor for failure prediction and remaining useful life, learned per-machine thresholds, and operator feedback ("false alarm") to retrain.
12. **Why not train a model now?**
    No real labelled data, simulated data would just teach a model our own rules, 4 hours is too short, and judges can't verify a black box. Rule + statistics is honest and explainable.
13. **How do you avoid alert spam?**
    One alert per new issue; a repeat only if it escalates. An issue must stay normal for 2 readings to close, so a flickering value does not create new alerts.
14. **How do you connect machines to each other (cascade effects)?**
    This module flags each machine; the buffer rule (e.g. Body Conveyor filling after Weld Robot 2 slows) shows the knock-on effect, and the NetworkX dependency graph (teammate module) can use our alert statuses to trace the bottleneck.
15. **How do you handle missing columns or bad data types?**
    `prepare_dataframe` adds absent columns as NaN, converts text to numbers with `errors="coerce"`, synthesises timestamps if needed, and the UI lists columns that were skipped. It never crashes on bad values.

## 10. Integrating into the main Streamlit app
1. Copy the `p2_alerts/` folder into the repo (it includes the empty `__init__.py`). Add `streamlit pandas numpy plotly` to `requirements.txt` if missing.
2. In the main app (a page or tab), where `df` is your teammate's DataFrame:
```python
from p2_alerts.alert_demo import render_alert_dashboard

with tab_alerts:                       # or a page function
    render_alert_dashboard(df, key_prefix="p2")
```
   `render_alert_dashboard` does **not** call `st.set_page_config`, so it will not clash with the main app.
3. To use only the backend (e.g. to colour nodes in the NetworkX graph):
```python
from p2_alerts.alert_engine import run_monitoring
result = run_monitoring(df)
status = dict(zip(result["status"]["machine_name"], result["status"]["status"]))   # {"Weld Robot 2": "CRITICAL", ...}
```
4. Machine names must match across modules. Names used here: Blank Press, Draw Press, Weld Robot 1-3, Body Conveyor, Paint Booth,
   Curing Oven, Paint Conveyor, Engine Line, Gearbox Line, Engine Test, Marriage, Trim Line, Wheel Fit, Vision Check, End-of-Line Inspection.
   If the team uses a single name "Conveyor", it still works (stage "Body Shop / Paint Shop"); otherwise edit `MACHINE_STAGE` in `alert_engine.py`.
5. Git:
```bash
git checkout -b p2-alerts
git add p2_alerts requirements.txt
git commit -m "Add P2 alert engine and demo"
git push -u origin p2-alerts
```
