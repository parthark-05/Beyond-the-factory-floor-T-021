"""
sample_data.py - simulated machine readings for the alert demo (NOT real sensor data).

generate_sample_data() returns a DataFrame with the agreed columns:
machine_name, temperature, processing_time, output_per_hour, downtime_minutes,
buffer_quantity, defect_count, total_inspected, timestamp

It injects a few known problems so the demo has something to detect:
  Weld Robot 2  - overheating drift + output drop + rising defects (-> CRITICAL)
  Body Conveyor - buffer filling up (knock-on effect of the slow robot)
  Gearbox Line  - processing time slowly increasing (-> WARNING)
  Paint Booth   - rising defect rate
  Curing Oven   - excessive downtime at the end
  Trim Line     - output collapses at the end
  Draw Press    - sensor faults (missing, negative, frozen, jump, impossible)
  Wheel Fit / Vision Check - one invalid output / defect reading
"""
import numpy as np
import pandas as pd

try:                                   # works as package or as plain script folder
    from .alert_engine import ALL_COLUMNS
except ImportError:
    from alert_engine import ALL_COLUMNS

# machine: (temperature C, processing time s, output per hour, buffer units)
PROFILES = {
    "Blank Press": (55, 12, 300, 30), "Draw Press": (58, 15, 280, 35),
    "Weld Robot 1": (62, 40, 110, 40), "Weld Robot 2": (62, 40, 110, 40),
    "Weld Robot 3": (62, 40, 110, 40), "Body Conveyor": (40, 20, 105, 35),
    "Paint Booth": (25, 60, 100, 30), "Curing Oven": (180, 90, 100, 30),
    "Paint Conveyor": (40, 20, 100, 30),
    "Engine Line": (70, 50, 95, 25), "Gearbox Line": (65, 45, 95, 25),
    "Engine Test": (85, 70, 90, 20),
    "Marriage": (35, 30, 90, 25), "Trim Line": (30, 55, 90, 30), "Wheel Fit": (32, 25, 90, 25),
    "Vision Check": (38, 18, 90, 20), "End-of-Line Inspection": (36, 35, 88, 15),
}
INSPECTION = {"Vision Check", "End-of-Line Inspection"}


def generate_sample_data(hours=48, seed=42, end_time=None):
    """One reading per machine per hour for `hours` hours."""
    hours = max(int(hours), 30)
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(end_time) if end_time is not None else pd.Timestamp.now().floor("h")
    times = pd.date_range(end=end, periods=hours, freq="h")
    drift = hours - 22              # Weld Robot 2 starts drifting here
    rows = []
    for machine, (temp, ptime, out, buf) in PROFILES.items():
        for k, t in enumerate(times):
            temperature = temp + rng.normal(0, max(0.8, 0.012 * temp))
            processing = ptime * (1 + rng.normal(0, 0.015))
            output = out * (1 + rng.normal(0, 0.02))
            buffer = buf + rng.normal(0, 2)
            downtime = float(rng.choice([0, 0, 0, 0, 1, 2, 3]))
            inspected = int(rng.integers(280, 321) if machine in INSPECTION else rng.integers(180, 221))
            p_def = 0.012

            if machine == "Weld Robot 2" and k >= drift:
                n = k - drift + 1
                temperature += 1.5 * n
                output *= max(0.55, 1 - 0.018 * n)
                p_def = 0.012 + 0.0028 * n
            if machine == "Body Conveyor" and k >= drift + 6:
                buffer += 2.5 * (k - drift - 5)
            if machine == "Gearbox Line" and k >= hours - 16:
                processing *= 1 + 0.012 * (k - (hours - 16) + 1)
            if machine == "Paint Booth" and k >= hours - 14:
                p_def = 0.01 + 0.004 * (k - (hours - 14) + 1)
            if machine == "Curing Oven" and k >= hours - 3:
                downtime = [14, 32, 38][k - (hours - 3)]
            if machine == "Trim Line" and k >= hours - 4:
                output *= [0.93, 0.80, 0.62, 0.50][k - (hours - 4)]

            defects = int(rng.binomial(inspected, min(p_def, 0.5)))
            row = {"machine_name": machine, "temperature": temperature,
                   "processing_time": processing, "output_per_hour": output,
                   "downtime_minutes": downtime, "buffer_quantity": buffer,
                   "defect_count": defects, "total_inspected": inspected, "timestamp": t}

            if machine == "Draw Press":                       # sensor problems
                if k == hours - 30: row["temperature"] = np.nan          # missing
                if k == hours - 20: row["temperature"] = -12.0           # negative
                if hours - 12 <= k <= hours - 8: row["temperature"] = 58.0   # frozen
                if k == hours - 6: row["temperature"] = 88.0             # sudden jump
                if k == hours - 3: row["temperature"] = 999.0            # impossible
            if machine == "Wheel Fit" and k == hours - 18: row["output_per_hour"] = -50.0
            if machine == "Vision Check" and k == hours - 10: row["defect_count"] = np.nan
            rows.append(row)

    df = pd.DataFrame(rows, columns=ALL_COLUMNS)
    for col in ["temperature", "processing_time", "output_per_hour", "buffer_quantity"]:
        df[col] = df[col].round(2)
    df = df.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    return df


if __name__ == "__main__":
    data = generate_sample_data()
    data.to_csv("sample_machine_data.csv", index=False)
    print(data.head(10).to_string(index=False))
    print(f"\nSaved {len(data)} rows to sample_machine_data.csv")
