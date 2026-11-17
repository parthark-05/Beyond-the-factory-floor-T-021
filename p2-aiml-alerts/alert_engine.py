"""
alert_engine.py  -  P2 (AI/ML Developer): Warning & Critical alert engine
=========================================================================
Project : Beyond the Factory Floor (simulated automobile factory)

What this module does
  1. validate_sensors()      -> VALID / WARNING / INVALID status for every reading
  2. generate_alerts()       -> NORMAL / WARNING / CRITICAL alerts (de-duplicated)
  3. detect_defect_trends()  -> defect rate over time + rising-trend detection
  4. run_monitoring()        -> runs everything and returns one dictionary

Methods used (all lightweight, NO trained ML model):
  - Threshold rules          (rule-based)
  - Baseline-ratio rules     (rule-based, baseline = median of first readings)
  - Rolling Z-score          (statistical anomaly detection)
  - Linear-slope trend       (statistical trend detection, numpy.polyfit)
  - Two-proportion z-test    (is a defect-rate rise bigger than random noise?)
  - Sensor validation rules  (range / missing / jump / frozen-value checks)

Only needs: pandas, numpy.
Input: a pandas DataFrame with (any subset of) the columns
  machine_name, temperature, processing_time, output_per_hour,
  downtime_minutes, buffer_quantity, defect_count, total_inspected, timestamp
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
SEVERITY_RANK = {"NORMAL": 0, "WARNING": 1, "CRITICAL": 2}
SENSOR_PARAMS = ["temperature", "processing_time", "output_per_hour",
                 "downtime_minutes", "buffer_quantity"]
COUNT_PARAMS = ["defect_count", "total_inspected"]
ALL_COLUMNS = ["machine_name", *SENSOR_PARAMS, *COUNT_PARAMS, "timestamp"]

MACHINE_STAGE = {
    "Blank Press": "Stamping", "Draw Press": "Stamping",
    "Weld Robot 1": "Body Shop", "Weld Robot 2": "Body Shop",
    "Weld Robot 3": "Body Shop", "Body Conveyor": "Body Shop",
    "Paint Booth": "Paint Shop", "Curing Oven": "Paint Shop",
    "Paint Conveyor": "Paint Shop",
    "Conveyor": "Body Shop / Paint Shop",          # in case teammate uses one name
    "Engine Line": "Powertrain", "Gearbox Line": "Powertrain",
    "Engine Test": "Powertrain",
    "Marriage": "Vehicle Assembly", "Trim Line": "Vehicle Assembly",
    "Wheel Fit": "Vehicle Assembly",
    "Vision Check": "Inspection", "End-of-Line Inspection": "Inspection",
}

LABELS = {  # parameter -> (display name, unit)
    "temperature": ("Temperature", "°C"),
    "processing_time": ("Processing time", "s"),
    "output_per_hour": ("Output", "units/h"),
    "downtime_minutes": ("Downtime", "min"),
    "buffer_quantity": ("Buffer level", "units"),
    "defect_rate": ("Defect rate", "%"),
}

ACTIONS = {
    "temperature": {
        "CRITICAL": "Stop or throttle the machine now, check cooling and lubrication, and call maintenance before restarting.",
        "WARNING": "Check cooling, lubrication and load; schedule an inspection this shift."},
    "processing_time": {
        "CRITICAL": "Inspect for jams, tool wear or material problems; the slow cycle is throttling the line. Call maintenance.",
        "WARNING": "Check tooling and material feed and compare the cycle time with the standard."},
    "output_per_hour": {
        "CRITICAL": "Output has collapsed: check for stoppages, starvation or blockage, and inform the shift supervisor.",
        "WARNING": "Check upstream supply and downstream blockage; watch this machine closely."},
    "downtime_minutes": {
        "CRITICAL": "Excessive downtime: dispatch maintenance, find the root cause and plan a recovery.",
        "WARNING": "Review recent stoppages and check for recurring minor faults."},
    "buffer_quantity": {
        "CRITICAL": "Buffer almost full or empty: check the next/previous station for a bottleneck.",
        "WARNING": "Buffer level is drifting: check the neighbouring stations for slowdowns."},
    "defect_rate": {
        "CRITICAL": "Quarantine recent parts, stop the line if needed, and run a quality/root-cause check on this stage.",
        "WARNING": "Increase sampling inspection and check tooling, settings and material batch."},
    "sensor": {
        "WARNING": "Inspect or recalibrate the sensor and wiring. Confirm the value manually before acting on the machine."},
}

DEFAULT_CONFIG = {
    # absolute limits (can be overridden per machine below)
    "limits": {
        "temperature": {"warning": 75.0, "critical": 90.0},
        "downtime_minutes": {"warning": 10.0, "critical": 25.0},
    },
    # per machine overrides (machines that run hotter/cooler than normal)
    "machine_overrides": {
        "Curing Oven": {"temperature": {"warning": 195.0, "critical": 210.0}},
        "Engine Test": {"temperature": {"warning": 100.0, "critical": 115.0}},
        "Paint Booth": {"temperature": {"warning": 32.0, "critical": 38.0}},
    },
    # ratio to the machine's own baseline
    "relative": {
        "processing_time": {"warning": 1.15, "critical": 1.40},   # higher is worse
        "output_per_hour": {"warning": 0.85, "critical": 0.60},   # lower is worse
    },
    "buffer": {"capacity": 100.0, "high_warning": 0.80,
               "high_critical": 0.95, "low_warning": 0.05},
    # optional fixed baselines: {"Weld Robot 1": {"output_per_hour": 120}}
    "baselines": {},
    "baseline_readings": 10,        # baseline = median of the first N valid readings
    "baseline_min_readings": 5,     # no relative rules before this many readings
    "zscore": {
        "threshold": 4.0, "window": 24, "min_points": 12,
        "params": {"temperature": "high", "processing_time": "high",
                   "output_per_hour": "low", "buffer_quantity": "both"},
    },
    "trend": {
        "window": 6, "min_relative_change": 0.06, "min_steps_in_direction": 4,
        "params": {"temperature": "high", "processing_time": "high",
                   "output_per_hour": "low"},
    },
    "defect": {
        "warning_pct": 3.0, "critical_pct": 6.0, "early_warning_pct": 1.5,
        "recent_window": 3, "previous_window": 6, "min_sample": 50,
        "min_increase_pp": 0.5, "rise_ratio": 1.5, "rise_z": 3.0,
    },
    "validation": {
        "max_values": {"temperature": 400, "processing_time": 3600,
                       "output_per_hour": 5000, "downtime_minutes": 60,
                       "buffer_quantity": 1000, "defect_count": 100000,
                       "total_inspected": 100000},
        "jump": {"temperature": {"pct": 0.35, "min_abs": 15},
                 "processing_time": {"pct": 0.50, "min_abs": 5},
                 "output_per_hour": {"pct": 0.60, "min_abs": 20},
                 "buffer_quantity": {"pct": 0.60, "min_abs": 20}},
        "stale_count": 4,
        "stale_params": ["temperature", "processing_time"],
    },
    "alerts": {"clear_after": 2},   # quiet readings before an issue is considered resolved
}

ALERT_COLUMNS = ["alert_id", "timestamp", "machine_name", "stage", "severity",
                 "category", "parameter", "message", "current_reading",
                 "threshold", "recommended_action", "detection_method",
                 "event", "sensor_note"]


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _merge(config=None):
    """Deep-merge a user config into DEFAULT_CONFIG (returns a new dict)."""
    def update(base, new):
        for k, v in new.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                update(base[k], v)
            else:
                base[k] = v
        return base
    return update(copy.deepcopy(DEFAULT_CONFIG), config or {})


def get_limits(cfg, machine, param):
    """Warning/critical limit for a parameter, with per-machine overrides."""
    over = cfg.get("machine_overrides", {}).get(machine, {}).get(param)
    return over if over else cfg["limits"][param]


def recommended_action(param, severity):
    acts = ACTIONS.get(param, {})
    return acts.get(severity) or acts.get("WARNING") or "Inspect the machine and verify the readings."


def get_stage(machine, group=None):
    if group is not None and "stage" in group.columns and group["stage"].notna().any():
        return str(group["stage"].dropna().iloc[0])
    lower = {k.lower(): v for k, v in MACHINE_STAGE.items()}
    return lower.get(str(machine).lower(), "Unknown")


def _finding(param, severity, message, reading, threshold, method):
    return {"parameter": param, "severity": severity, "message": message,
            "current_reading": reading, "threshold": threshold,
            "method": method, "sensor_note": ""}


def _fmt(v, param):
    return f"{v:.1f} {LABELS[param][1]}"


def prepare_dataframe(df):
    """Make the input safe: add missing columns, convert to numbers, parse
    timestamps, sort each machine by time. Never raises on bad values."""
    if df is None or len(df) == 0:
        empty = pd.DataFrame(columns=ALL_COLUMNS)
        empty["timestamp"] = pd.to_datetime(empty["timestamp"])
        return empty
    data = df.copy()
    data.columns = [str(c).strip().lower() for c in data.columns]
    if "machine_name" not in data.columns:
        data["machine_name"] = "Unknown Machine"
    data["machine_name"] = (data["machine_name"].fillna("Unknown Machine")
                            .astype(str).str.strip())
    for col in SENSOR_PARAMS + COUNT_PARAMS:
        data[col] = pd.to_numeric(data[col], errors="coerce") if col in data.columns else np.nan
    if "timestamp" in data.columns:
        ts = pd.to_datetime(data["timestamp"], errors="coerce")
    else:
        ts = pd.Series(pd.NaT, index=data.index)
    if ts.isna().all():  # no usable timestamps -> assume one reading per hour
        ts = (pd.Timestamp("2026-01-01")
              + pd.to_timedelta(data.groupby("machine_name").cumcount(), unit="h"))
    data["timestamp"] = ts
    data = data.reset_index(drop=True)
    data["_order"] = np.arange(len(data))
    first_seen = {m: k for k, m in enumerate(data["machine_name"].drop_duplicates())}
    data["_m"] = data["machine_name"].map(first_seen)
    data = data.sort_values(["_m", "timestamp", "_order"], kind="mergesort")
    return data.drop(columns=["_order", "_m"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# B. Sensor validation
# --------------------------------------------------------------------------
def validate_sensors(df, config=None):
    """Check every reading. Returns (clean_df, sensor_report).

    INVALID  = missing / negative / impossible value  -> value is removed (NaN)
               in clean_df so it is NOT mistaken for a real machine failure.
    WARNING  = sudden jump, frozen (repeated) value, duplicate/missing timestamp
               -> value is kept but flagged "verify sensor".
    VALID    = nothing suspicious.
    """
    cfg = _merge(config)
    rules = cfg["validation"]
    data = prepare_dataframe(df)
    present = [c for c in SENSOR_PARAMS + COUNT_PARAMS if data[c].notna().any()]
    missing_cols = [c for c in SENSOR_PARAMS + COUNT_PARAMS if c not in present]

    clean = data.copy()
    clean["sensor_status"] = "VALID"
    clean["sensor_invalid_params"] = ""
    clean["sensor_warn_params"] = ""
    clean["sensor_reason"] = ""
    report_rows = []

    for machine, g in data.groupby("machine_name", sort=False):
        last_valid, recent, prev_ts = {}, {p: [] for p in rules["stale_params"]}, None
        for idx, row in g.iterrows():
            invalid, warn = {}, {}
            for p in present:
                val = row[p]
                if pd.isna(val):
                    invalid[p] = "missing or non-numeric reading"
                    continue
                if val < 0:
                    invalid[p] = f"negative value ({val:g}) is physically impossible"
                    continue
                hi = rules["max_values"].get(p)
                if hi is not None and val > hi:
                    invalid[p] = f"value {val:g} is outside the realistic range (0-{hi:g})"
                    continue
                jump = rules["jump"].get(p)
                if jump and p in last_valid:
                    prev = last_valid[p]
                    diff = abs(val - prev)
                    if diff > jump["min_abs"] and diff > jump["pct"] * abs(prev):
                        warn[p] = f"sudden jump from {prev:g} to {val:g}"
                last_valid[p] = val
                if p in recent:
                    recent[p].append(val)
                    recent[p] = recent[p][-rules["stale_count"]:]
                    if len(recent[p]) == rules["stale_count"] and max(recent[p]) == min(recent[p]):
                        warn[p] = (f"identical value {val:g} repeated {rules['stale_count']} "
                                   "times (frozen/stale sensor?)")
            if "defect_count" in present and "total_inspected" in present:
                d, t = row["defect_count"], row["total_inspected"]
                if pd.notna(d) and pd.notna(t) and d > t:
                    invalid["defect_count"] = f"defects ({d:g}) exceed inspected units ({t:g})"
                    invalid["total_inspected"] = "inconsistent with defect_count"
            ts = row["timestamp"]
            if pd.isna(ts):
                warn["timestamp"] = "missing or unreadable timestamp"
            elif prev_ts is not None and ts == prev_ts:
                warn["timestamp"] = "duplicate timestamp for this machine"
            if pd.notna(ts):
                prev_ts = ts

            status = "INVALID" if invalid else ("WARNING" if warn else "VALID")
            parts = [f"{p}: {t}" for p, t in {**warn, **invalid}.items()]
            reason = "; ".join(parts)
            if invalid:
                reason += "  ->  likely a SENSOR/DATA fault, not a machine failure"
            elif warn:
                reason += "  ->  verify the sensor before acting"
            for p in invalid:
                clean.at[idx, p] = np.nan
            clean.at[idx, "sensor_status"] = status
            clean.at[idx, "sensor_invalid_params"] = ",".join(invalid)
            clean.at[idx, "sensor_warn_params"] = ",".join(warn)
            clean.at[idx, "sensor_reason"] = reason
            report_rows.append({"timestamp": ts, "machine_name": machine,
                                "sensor_status": status,
                                "flagged_parameters": ", ".join({**warn, **invalid}),
                                "reason": reason if reason else "All checks passed"})
    report = pd.DataFrame(report_rows, columns=["timestamp", "machine_name", "sensor_status",
                                                "flagged_parameters", "reason"])
    report.attrs["missing_columns"] = missing_cols
    return clean, report


# --------------------------------------------------------------------------
# D. Anomaly detection pieces (threshold, z-score, trend)
# --------------------------------------------------------------------------
def _baseline(machine, param, hist, cfg):
    fixed = cfg["baselines"].get(machine, {}).get(param)
    if fixed:
        return float(fixed)
    valid = hist[~np.isnan(hist)]
    if len(valid) < cfg["baseline_min_readings"]:
        return None
    return float(np.median(valid[: cfg["baseline_readings"]]))


def _threshold_finding(machine, param, v, baseline, cfg):
    label, unit = LABELS[param]
    if param in ("temperature", "downtime_minutes"):
        lim = get_limits(cfg, machine, param)
        if v >= lim["critical"]:
            return _finding(param, "CRITICAL", f"{label} is at a critical level ({v:.1f} {unit})",
                            _fmt(v, param), f">= {lim['critical']:g} {unit} (critical limit)", "Threshold rule")
        if v >= lim["warning"]:
            return _finding(param, "WARNING", f"{label} is approaching its limit ({v:.1f} {unit})",
                            _fmt(v, param), f">= {lim['warning']:g} {unit} (warning limit)", "Threshold rule")
        return None
    if param in ("processing_time", "output_per_hour"):
        if not baseline or baseline <= 0:
            return None
        rule, ratio = cfg["relative"][param], v / baseline
        if param == "processing_time":
            if ratio >= rule["critical"]:
                sev, lim = "CRITICAL", rule["critical"]
            elif ratio >= rule["warning"]:
                sev, lim = "WARNING", rule["warning"]
            else:
                return None
            return _finding(param, sev, f"Processing time is {ratio * 100 - 100:.0f}% above normal ({baseline:.1f} s)",
                            _fmt(v, param), f">= {lim * 100:.0f}% of baseline ({baseline * lim:.1f} s)",
                            "Baseline ratio rule")
        if ratio <= rule["critical"]:
            sev, lim = "CRITICAL", rule["critical"]
        elif ratio <= rule["warning"]:
            sev, lim = "WARNING", rule["warning"]
        else:
            return None
        return _finding(param, sev, f"Output fell to {ratio * 100:.0f}% of normal ({v:.0f} vs {baseline:.0f} units/h)",
                        _fmt(v, param), f"<= {lim * 100:.0f}% of baseline ({baseline * lim:.0f} units/h)",
                        "Baseline ratio rule")
    if param == "buffer_quantity":
        b = cfg["buffer"]
        frac = v / b["capacity"]
        if frac >= b["high_critical"]:
            return _finding(param, "CRITICAL", f"Buffer is almost full ({v:.0f}/{b['capacity']:.0f}) - downstream may be blocked",
                            _fmt(v, param), f">= {b['high_critical'] * 100:.0f}% of capacity", "Threshold rule")
        if frac >= b["high_warning"]:
            return _finding(param, "WARNING", f"Buffer is filling up ({v:.0f}/{b['capacity']:.0f}) - possible downstream slowdown",
                            _fmt(v, param), f">= {b['high_warning'] * 100:.0f}% of capacity", "Threshold rule")
        if frac <= b["low_warning"]:
            return _finding(param, "WARNING", f"Buffer is nearly empty ({v:.0f}/{b['capacity']:.0f}) - machine may be starved",
                            _fmt(v, param), f"<= {b['low_warning'] * 100:.0f}% of capacity", "Threshold rule")
    return None


def _zscore_finding(param, hist, cfg):
    """Rolling Z-score: how many standard deviations is the newest reading from
    the mean of the previous `window` readings?  z = (x - mean) / std"""
    z = cfg["zscore"]
    direction = z["params"].get(param)
    if not direction:
        return None
    v = hist[-1]
    past = hist[:-1]
    past = past[~np.isnan(past)][-z["window"]:]
    if len(past) < z["min_points"]:
        return None
    mean, std = float(past.mean()), float(past.std(ddof=1))
    std_eff = max(std, 0.02 * abs(mean), 1e-6)       # floor: avoids huge z on very flat data
    score = (v - mean) / std_eff
    thr = z["threshold"]
    hit = ((direction == "high" and score >= thr) or (direction == "low" and score <= -thr)
           or (direction == "both" and abs(score) >= thr))
    if not hit:
        return None
    label = LABELS[param][0]
    return _finding(param, "WARNING",
                    f"{label} is unusual: {score:+.1f} standard deviations from its recent average ({mean:.1f})",
                    _fmt(v, param), f"|z| >= {thr:g} vs last {len(past)} readings", "Rolling Z-score")


def _trend_finding(param, hist, cfg):
    """Simple trend: fit a straight line to the last N readings (least squares).
    Flag if the line moves more than X% in the bad direction and most steps agree."""
    t = cfg["trend"]
    direction = t["params"].get(param)
    if not direction:
        return None
    n = t["window"]
    pts = hist[~np.isnan(hist)][-n:]
    if len(pts) < n:
        return None
    slope = float(np.polyfit(np.arange(n), pts, 1)[0])
    rel = slope * (n - 1) / max(abs(float(pts.mean())), 1e-6)
    diffs = np.diff(pts)
    up, down = int((diffs > 0).sum()), int((diffs < 0).sum())
    need, minrel = t["min_steps_in_direction"], t["min_relative_change"]
    label = LABELS[param][0]
    if direction == "high" and rel >= minrel and up >= need:
        return _finding(param, "WARNING", f"{label} has been rising steadily (+{rel * 100:.0f}% over last {n} readings)",
                        _fmt(pts[-1], param), f"rise >= {minrel * 100:.0f}% over {n} readings", "Linear trend")
    if direction == "low" and rel <= -minrel and down >= need:
        return _finding(param, "WARNING", f"{label} has been dropping steadily ({rel * 100:.0f}% over last {n} readings)",
                        _fmt(pts[-1], param), f"drop >= {minrel * 100:.0f}% over {n} readings", "Linear trend")
    return None


def _assess_param(machine, param, arr, i, cfg):
    """Look at reading i using ONLY readings up to i (no peeking into the future).
    Priority: threshold rule > z-score > trend. One finding per parameter."""
    hist = arr[: i + 1]
    baseline = _baseline(machine, param, hist, cfg)
    return (_threshold_finding(machine, param, float(hist[-1]), baseline, cfg)
            or _zscore_finding(param, hist, cfg)
            or _trend_finding(param, hist, cfg))


# --------------------------------------------------------------------------
# C. Defect rate logic
# --------------------------------------------------------------------------
def _defect_assessment(defects, totals, i, cfg):
    """Defect rate = defect_count / total_inspected * 100.
    'recent' = pooled rate of the last few readings (stable even if one reading is small).
    'previous' = pooled rate of the readings just before that."""
    d = cfg["defect"]
    ok = ~np.isnan(defects) & ~np.isnan(totals) & (totals > 0)
    dd, tt = np.where(ok, defects, 0.0), np.where(ok, totals, 0.0)
    lo = max(0, i - d["recent_window"] + 1)
    plo = max(0, lo - d["previous_window"])
    nan = float("nan")
    rt, rd = tt[lo:i + 1].sum(), dd[lo:i + 1].sum()
    pt, pd_ = tt[plo:lo].sum(), dd[plo:lo].sum()
    recent = rd / rt * 100 if rt >= d["min_sample"] else nan
    previous = pd_ / pt * 100 if pt >= d["min_sample"] else nan
    current = dd[i] / tt[i] * 100 if ok[i] else nan

    trend = "UNKNOWN"
    if not np.isnan(recent) and not np.isnan(previous):
        inc = recent - previous
        # two-proportion z-test: is the jump bigger than normal random variation?
        pooled = (rd + pd_) / (rt + pt)
        se = np.sqrt(max(pooled * (1 - pooled), 1e-9) * (1 / rt + 1 / pt))
        rise_z = (recent - previous) / 100 / se
        if (inc >= d["min_increase_pp"] and recent >= previous * d["rise_ratio"]
                and rise_z >= d["rise_z"]):
            trend = "RISING"
        elif -inc >= d["min_increase_pp"] and recent <= previous / d["rise_ratio"]:
            trend = "FALLING"
        else:
            trend = "STABLE"

    severity, threshold, reason = "NORMAL", "", "Defect rate is within limits"
    if np.isnan(recent):
        reason = "Not enough inspected units to judge the defect rate"
    else:
        rise = f", up from {previous:.1f}% earlier" if trend == "RISING" else ""
        if recent >= d["critical_pct"]:
            severity, threshold = "CRITICAL", f">= {d['critical_pct']:g}% (critical limit)"
            reason = f"Defect rate {recent:.1f}% over the last {d['recent_window']} readings is dangerously high{rise}"
        elif recent >= d["warning_pct"]:
            severity, threshold = "WARNING", f">= {d['warning_pct']:g}% (warning limit)"
            reason = f"Defect rate {recent:.1f}% over the last {d['recent_window']} readings is above the warning limit{rise}"
        elif trend == "RISING" and recent >= d["early_warning_pct"]:
            severity = "WARNING"
            threshold = f"rising trend (>= {d['rise_ratio']:g}x previous, z >= {d['rise_z']:g})"
            reason = f"Defect rate is rising ({previous:.1f}% -> {recent:.1f}%) before reaching the limit"
    return {"current_rate": current, "recent_rate": recent, "previous_rate": previous,
            "trend": trend, "severity": severity, "threshold": threshold, "reason": reason}


def detect_defect_trends(df, config=None):
    """Per-reading defect rate table with trend and severity. Needs defect_count
    and total_inspected; returns an empty table if they are not available."""
    cfg = _merge(config)
    cols = ["timestamp", "machine_name", "stage", "defect_count", "total_inspected",
            "defect_rate_pct", "recent_rate_pct", "previous_rate_pct", "trend",
            "severity", "reason"]
    clean = df if "sensor_status" in df.columns else validate_sensors(df, cfg)[0]
    rows = []
    for machine, g in clean.groupby("machine_name", sort=False):
        g = g.reset_index(drop=True)
        if not (g["total_inspected"].notna().any() and g["defect_count"].notna().any()):
            continue
        stage = get_stage(machine, g)
        dc, ti = g["defect_count"].to_numpy(float), g["total_inspected"].to_numpy(float)
        for i in range(len(g)):
            a = _defect_assessment(dc, ti, i, cfg)
            rows.append({"timestamp": g.at[i, "timestamp"], "machine_name": machine, "stage": stage,
                         "defect_count": dc[i], "total_inspected": ti[i],
                         "defect_rate_pct": round(a["current_rate"], 2),
                         "recent_rate_pct": round(a["recent_rate"], 2),
                         "previous_rate_pct": round(a["previous_rate"], 2),
                         "trend": a["trend"], "severity": a["severity"], "reason": a["reason"]})
    return pd.DataFrame(rows, columns=cols)


# --------------------------------------------------------------------------
# A. Alert generation (with de-duplication)
# --------------------------------------------------------------------------
def generate_alerts(df, config=None):
    """Replay the readings in time order and create alerts.

    De-duplication: an alert is created only when an issue is NEW or gets WORSE
    (WARNING -> CRITICAL). While the same issue continues no new alert is added.
    An issue is closed after `clear_after` normal readings in a row.

    Returns (alerts_history, machine_status, active_alerts)."""
    cfg = _merge(config)
    if "sensor_status" not in df.columns:
        df, _ = validate_sensors(df, cfg)
    clear_after = cfg["alerts"]["clear_after"]
    alerts, status_rows, active_rows = [], [], []

    for machine, g in df.groupby("machine_name", sort=False):
        g = g.reset_index(drop=True)
        stage = get_stage(machine, g)
        arr = {p: g[p].to_numpy(dtype=float) for p in SENSOR_PARAMS + COUNT_PARAMS}
        active = {}
        for i in range(len(g)):
            ts = g.at[i, "timestamp"]
            findings, evaluated = {}, {"sensor"}
            invalid = [p for p in str(g.at[i, "sensor_invalid_params"]).split(",") if p]
            warn_p = {p for p in str(g.at[i, "sensor_warn_params"]).split(",") if p}
            for p in SENSOR_PARAMS:
                if np.isnan(arr[p][i]):
                    continue                      # invalid/missing -> never judged as machine fault
                evaluated.add(p)
                f = _assess_param(machine, p, arr[p], i, cfg)
                if f:
                    if p in warn_p:
                        f["sensor_note"] = "Reading was also flagged by sensor validation - verify the sensor before shutting down the machine."
                    findings[p] = f
            da = _defect_assessment(arr["defect_count"], arr["total_inspected"], i, cfg)
            if not np.isnan(da["recent_rate"]):
                evaluated.add("defect_rate")
                if da["severity"] != "NORMAL":
                    findings["defect_rate"] = _finding(
                        "defect_rate", da["severity"], da["reason"],
                        f"{da['recent_rate']:.1f} %", da["threshold"],
                        "Defect threshold + trend comparison")
            if invalid:
                findings["sensor"] = _finding(
                    "sensor", "WARNING",
                    f"Sensor fault suspected on: {', '.join(invalid)}. Reading ignored - NOT treated as a machine failure.",
                    "INVALID reading", str(g.at[i, "sensor_reason"]), "Sensor validation rules")

            for key, f in findings.items():
                sev, st = f["severity"], active.get(key)
                if st is None or SEVERITY_RANK[sev] > SEVERITY_RANK[st["severity"]]:
                    alerts.append({
                        "timestamp": ts, "machine_name": machine, "stage": stage, "severity": sev,
                        "category": "SENSOR" if key == "sensor" else ("QUALITY" if key == "defect_rate" else "MACHINE"),
                        "parameter": key, "message": f["message"], "current_reading": f["current_reading"],
                        "threshold": f["threshold"], "recommended_action": recommended_action(key, sev),
                        "detection_method": f["method"], "event": "NEW" if st is None else "ESCALATED",
                        "sensor_note": f["sensor_note"]})
                    active[key] = {"severity": sev, "quiet": 0, "finding": f, "since": ts}
                else:
                    st["quiet"] = 0                # same issue continues -> no duplicate alert
            for key in list(active):
                if key in findings or key not in evaluated:
                    continue
                active[key]["quiet"] += 1
                if active[key]["quiet"] >= clear_after:
                    del active[key]

        ordered = sorted(active.items(), key=lambda kv: -SEVERITY_RANK[kv[1]["severity"]])
        for key, st in ordered:
            f = st["finding"]
            active_rows.append({
                "machine_name": machine, "stage": stage, "severity": st["severity"],
                "category": "SENSOR" if key == "sensor" else ("QUALITY" if key == "defect_rate" else "MACHINE"),
                "parameter": key, "message": f["message"], "current_reading": f["current_reading"],
                "threshold": f["threshold"], "recommended_action": recommended_action(key, st["severity"]),
                "since": st["since"], "sensor_note": f["sensor_note"]})
        if len(g):
            last = g.iloc[-1]
            last_def = _defect_assessment(arr["defect_count"], arr["total_inspected"], len(g) - 1, cfg)
            top = ordered[0] if ordered else None
            status_rows.append({
                "machine_name": machine, "stage": stage,
                "status": top[1]["severity"] if top else "NORMAL",
                "issue_type": (("Sensor fault" if top[0] == "sensor" else
                                "Quality" if top[0] == "defect_rate" else "Machine")) if top else "-",
                "active_issues": len(ordered),
                "top_issue": top[1]["finding"]["message"] if top else "All readings within limits",
                "last_update": last["timestamp"],
                "temperature": last["temperature"], "processing_time": last["processing_time"],
                "output_per_hour": last["output_per_hour"], "downtime_minutes": last["downtime_minutes"],
                "buffer_quantity": last["buffer_quantity"],
                "defect_rate_pct": round(last_def["recent_rate"], 2),
                "sensor_status": last["sensor_status"]})

    alerts_df = pd.DataFrame(alerts, columns=[c for c in ALERT_COLUMNS if c != "alert_id"])
    if len(alerts_df):
        alerts_df["_r"] = alerts_df["severity"].map(SEVERITY_RANK)
        alerts_df = (alerts_df.sort_values(["timestamp", "_r"], ascending=[True, False], kind="mergesort")
                     .drop(columns="_r").reset_index(drop=True))
    alerts_df.insert(0, "alert_id", [f"ALT-{k + 1:04d}" for k in range(len(alerts_df))])
    status_df = pd.DataFrame(status_rows)
    active_df = pd.DataFrame(active_rows, columns=[
        "machine_name", "stage", "severity", "category", "parameter", "message",
        "current_reading", "threshold", "recommended_action", "since", "sensor_note"])
    return alerts_df, status_df, active_df


# --------------------------------------------------------------------------
# One-call entry point for teammates
# --------------------------------------------------------------------------
def run_monitoring(df, config=None):
    """Run validation, alerts and defect analysis on a DataFrame.

    Returns a dict:
      alerts          alert history (de-duplicated)
      active_alerts   issues that are still open at the latest reading
      status          one row per machine (NORMAL / WARNING / CRITICAL)
      sensor_report   one row per reading with VALID / WARNING / INVALID
      defects         defect-rate time series with trend
      clean_data      readings after validation (invalid values -> NaN)
      missing_columns input columns that were absent or empty
      summary         counts for dashboard cards
    """
    cfg = _merge(config)
    clean, report = validate_sensors(df, cfg)
    alerts, status, active = generate_alerts(clean, cfg)
    defects = detect_defect_trends(clean, cfg)
    count = lambda frame, col, val: int((frame[col] == val).sum()) if len(frame) else 0
    summary = {
        "machines": int(clean["machine_name"].nunique()) if len(clean) else 0,
        "machines_critical": count(status, "status", "CRITICAL"),
        "machines_warning": count(status, "status", "WARNING"),
        "machines_normal": count(status, "status", "NORMAL"),
        "history_critical": count(alerts, "severity", "CRITICAL"),
        "history_warning": count(alerts, "severity", "WARNING"),
        "sensor_invalid": count(report, "sensor_status", "INVALID"),
        "sensor_warning": count(report, "sensor_status", "WARNING"),
        "sensor_valid": count(report, "sensor_status", "VALID"),
    }
    return {"alerts": alerts, "active_alerts": active, "status": status,
            "sensor_report": report, "defects": defects, "clean_data": clean,
            "missing_columns": report.attrs.get("missing_columns", []), "summary": summary}


if __name__ == "__main__":      # quick self-check: python alert_engine.py
    try:
        from sample_data import generate_sample_data
    except ImportError:
        raise SystemExit("Put sample_data.py in the same folder to run this self-check.")
    result = run_monitoring(generate_sample_data())
    print(result["summary"])
    print(result["status"][["machine_name", "status", "top_issue"]].to_string(index=False))
