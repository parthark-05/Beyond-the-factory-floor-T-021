import sqlite3
import time
from pathlib import Path
from typing import Dict, Any, List

# Stores factory_twin.db inside the database/ folder automatically
DB_FILE = Path(__file__).resolve().parent / "factory_twin.db"


class FactoryDB:
    def __init__(self, db_path: Path = DB_FILE) -> None:
        self.db_path = db_path
        self._create_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_tables(self) -> None:
        with self._connect() as conn:
            # Table 1: Stores 17 machine readings every second, including health_status
            conn.execute("""
                CREATE TABLE IF NOT EXISTS machine_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    machine_name TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    working_speed_pct REAL NOT NULL,
                    temperature_c REAL NOT NULL,
                    last_car_time_sec REAL NOT NULL,
                    health_status TEXT NOT NULL DEFAULT 'HEALTHY'
                )
            """)

            # Table 2: Stores whether each finished car is GOOD or BROKEN
            conn.execute("""
                CREATE TABLE IF NOT EXISTS finished_cars (
                    car_id TEXT PRIMARY KEY,
                    tick INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    quality_status TEXT NOT NULL,
                    defect_reason TEXT
                )
            """)

    @staticmethod
    def _evaluate_machine_health(machine: Dict[str, Any]) -> str:
        """
        Determines whether a machine is HEALTHY, WORRIED, or BROKEN
        based on cycle time slowdown, temperature spikes, sensor health, or part defects.
        """
        target = max(machine.get("target_cycle", 50.0), 0.1)
        cycle = machine.get("cycle_time", target)
        temp = machine.get("temp", 50.0)
        sensor_health = machine.get("sensor_health", "OK")
        pass_fail = machine.get("pass_fail", "PASS")

        ratio = cycle / target

        if ratio >= 1.35 or pass_fail == "FAIL" or temp >= 160.0:
            return "BROKEN"
        if ratio >= 1.12 or sensor_health == "FAULTY" or temp >= 95.0:
            return "WORRIED"
        return "HEALTHY"

    def save_simulation_tick(self, sim_output: Dict[str, Any]) -> None:
        """
        Accepts the dictionary returned by P1's simulator.step()
        and logs all 17 machine readings (with health_status) + latest car quality.
        """
        tick = sim_output["tick"]
        ts = sim_output["timestamp"]
        machines = sim_output["machines"]
        latest_car = sim_output["latest_car"]

        machine_rows = []
        for m in machines:
            speed_pct = round((m["target_cycle"] / max(m["cycle_time"], 0.1)) * 100, 1)
            health = m.get("health_status") or self._evaluate_machine_health(m)

            machine_rows.append((
                tick,
                ts,
                m["id"],
                m["name"],
                m["stage"],
                speed_pct,
                m["temp"],
                m["cycle_time"],
                health,
            ))

        car_quality = "GOOD" if latest_car["status"] == "PASS" else "BROKEN"
        reasons = ", ".join(
            f"{d['machine_id']} ({d['reason']})" for d in latest_car.get("failed_at", [])
        ) or "None"

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO machine_telemetry (
                    tick, timestamp, machine_id, machine_name, stage,
                    working_speed_pct, temperature_c, last_car_time_sec, health_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                machine_rows,
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO finished_cars (
                    car_id, tick, timestamp, quality_status, defect_reason
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (latest_car["car_id"], tick, ts, car_quality, reasons),
            )

    def seed_unhealthy_machines(self, tick: int = 1) -> None:
        """
        Inserts a full 17-machine snapshot into SQLite where specific machines
        are WORRIED or BROKEN so the database immediately reflects degraded factory states.
        """
        ts = time.strftime("%H:%M:%S")
        machines_17 = [
            # Stage 1: Stamping (M02 is WORRIED due to hydraulic overheating & slowdown)
            {"id": "M01", "name": "Blanking Press", "stage": "Stamping", "cycle_time": 42.2, "target_cycle": 42.0, "temp": 58.4, "sensor_health": "OK", "pass_fail": "PASS"},
            {"id": "M02", "name": "Deep Draw Press", "stage": "Stamping", "cycle_time": 53.5, "target_cycle": 45.0, "temp": 98.2, "sensor_health": "OK", "pass_fail": "PASS"},
            {"id": "M03", "name": "Trim & Pierce Press", "stage": "Stamping", "cycle_time": 43.1, "target_cycle": 43.0, "temp": 61.0, "sensor_health": "OK", "pass_fail": "PASS"},

            # Stage 2: Body Welding (M05 is BROKEN — major cycle spike & causing defective welds)
            {"id": "M04", "name": "Underbody Spot Welder", "stage": "Body Welding", "cycle_time": 48.5, "target_cycle": 48.0, "temp": 74.2, "sensor_health": "OK", "pass_fail": "PASS"},
            {"id": "M05", "name": "Left Side Framing Robot", "stage": "Body Welding", "cycle_time": 84.0, "target_cycle": 50.0, "temp": 106.5, "sensor_health": "OK", "pass_fail": "FAIL"},
            {"id": "M06", "name": "Right Side Framing Robot", "stage": "Body Welding", "cycle_time": 56.8, "target_cycle": 50.0, "temp": 82.0, "sensor_health": "OK", "pass_fail": "PASS"},
            {"id": "M07", "name": "Roof Laser Welder", "stage": "Body Welding", "cycle_time": 49.2, "target_cycle": 49.0, "temp": 79.1, "sensor_health": "OK", "pass_fail": "PASS"},

            # Stage 3: Paint Shop (M10 is WORRIED due to faulty temperature sensor)
            {"id": "M08", "name": "E-Coat Dip Tank", "stage": "Paint Shop", "cycle_time": 52.0, "target_cycle": 52.0, "temp": 42.1, "sensor_health": "OK", "pass_fail": "PASS"},
            {"id": "M09", "name": "Primer Spray Booth", "stage": "Paint Shop", "cycle_time": 54.3, "target_cycle": 54.0, "temp": 36.4, "sensor_health": "OK", "pass_fail": "PASS"},
            {"id": "M10", "name": "Base & Clear Coat Robot", "stage": "Paint Shop", "cycle_time": 55.1, "target_cycle": 55.0, "temp": 412.5, "sensor_health": "FAULTY", "pass_fail": "PASS"},
            {"id": "M11", "name": "Curing Oven", "stage": "Paint Shop", "cycle_time": 53.4, "target_cycle": 53.0, "temp": 146.0, "sensor_health": "OK", "pass_fail": "PASS"},

            # Stage 4: Powertrain Assembly (M14 is BROKEN — torque controller failure)
            {"id": "M12", "name": "Engine Decking Station", "stage": "Powertrain Assembly", "cycle_time": 56.0, "target_cycle": 56.0, "temp": 52.3, "sensor_health": "OK", "pass_fail": "PASS"},
            {"id": "M13", "name": "Transmission Mating", "stage": "Powertrain Assembly", "cycle_time": 55.2, "target_cycle": 55.0, "temp": 50.1, "sensor_health": "OK", "pass_fail": "PASS"},
            {"id": "M14", "name": "Suspension & Axle Torque", "stage": "Powertrain Assembly", "cycle_time": 76.4, "target_cycle": 54.0, "temp": 88.7, "sensor_health": "OK", "pass_fail": "FAIL"},
            {"id": "M15", "name": "Fluid Fill & Battery Mount", "stage": "Powertrain Assembly", "cycle_time": 52.1, "target_cycle": 52.0, "temp": 44.2, "sensor_health": "OK", "pass_fail": "PASS"},

            # Stage 5: Final QA (All healthy, catching defects from M05 and M14)
            {"id": "M16", "name": "Wheel Alignment & Dyno", "stage": "Final QA", "cycle_time": 48.0, "target_cycle": 48.0, "temp": 46.5, "sensor_health": "OK", "pass_fail": "PASS"},
            {"id": "M17", "name": "3D Vision & Leak Inspection", "stage": "Final QA", "cycle_time": 46.2, "target_cycle": 46.0, "temp": 32.1, "sensor_health": "OK", "pass_fail": "PASS"},
        ]

        sample_output = {
            "tick": tick,
            "timestamp": ts,
            "machines": machines_17,
            "latest_car": {
                "car_id": f"VIN-{1000 + tick}",
                "status": "FAIL",
                "failed_at": [
                    {"machine_id": "M05", "reason": "Weld integrity deviation"},
                    {"machine_id": "M14", "reason": "Axle torque out of spec"},
                ],
            },
        }
        self.save_simulation_tick(sample_output)

    def get_unhealthy_machines(self) -> List[Dict[str, Any]]:
        """Returns all latest machine records that are WORRIED or BROKEN."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT machine_id, machine_name, stage, working_speed_pct,
                       temperature_c, last_car_time_sec, health_status
                FROM machine_telemetry
                WHERE id IN (
                    SELECT MAX(id) FROM machine_telemetry GROUP BY machine_id
                )
                AND health_status != 'HEALTHY'
                ORDER BY machine_id ASC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_machine_logs(self, machine_id: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Fetch recent history for a single machine."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT tick, timestamp, working_speed_pct, temperature_c,
                       last_car_time_sec, health_status
                FROM machine_telemetry
                WHERE machine_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (machine_id, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_car_quality_counts(self) -> Dict[str, int]:
        """Returns total count of GOOD vs BROKEN cars."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT quality_status, COUNT(*) as total FROM finished_cars GROUP BY quality_status"
            ).fetchall()
        counts = {"GOOD": 0, "BROKEN": 0}
        for r in rows:
            counts[r["quality_status"]] = r["total"]
        return counts


# Standalone test: seeds all 17 machines (with 5 unhealthy ones) and prints summary
if __name__ == "__main__":
    # Remove old DB schema if testing fresh locally
    if DB_FILE.exists():
        DB_FILE.unlink()

    db = FactoryDB()
    db.seed_unhealthy_machines(tick=1)

    print("Car Quality Counts:", db.get_car_quality_counts())
    print("\nUnhealthy Machines Detected in Database:")
    for m in db.get_unhealthy_machines():
        print(
            f" - [{m['health_status']}] {m['machine_id']} ({m['machine_name']}): "
            f"Speed={m['working_speed_pct']}%, Temp={m['temperature_c']}°C, LastCar={m['last_car_time_sec']}s"
        )