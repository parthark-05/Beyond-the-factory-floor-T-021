import sqlite3
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
            # Table 1: Stores 17 machine readings every second
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
                    last_car_time_sec REAL NOT NULL
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

    def save_simulation_tick(self, sim_output: Dict[str, Any]) -> None:
        """
        Accepts the exact dictionary returned by P1's simulator.step()
        without requiring any changes to simulator.py.
        """
        tick = sim_output["tick"]
        ts = sim_output["timestamp"]
        machines = sim_output["machines"]
        latest_car = sim_output["latest_car"]

        machine_rows = []
        for m in machines:
            # Calculate working speed % relative to target cycle time
            speed_pct = round((m["target_cycle"] / max(m["cycle_time"], 0.1)) * 100, 1)
            machine_rows.append((
                tick,
                ts,
                m["id"],
                m["name"],
                m["stage"],
                speed_pct,
                m["temp"],
                m["cycle_time"],
            ))

        # Map P1's PASS/FAIL to GOOD/BROKEN
        car_quality = "GOOD" if latest_car["status"] == "PASS" else "BROKEN"
        reasons = ", ".join(
            f"{d['machine_id']} ({d['reason']})" for d in latest_car.get("failed_at", [])
        ) or "None"

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO machine_telemetry (
                    tick, timestamp, machine_id, machine_name, stage,
                    working_speed_pct, temperature_c, last_car_time_sec
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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

    def get_recent_machine_logs(self, machine_id: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Fetch recent history for a single machine."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT tick, timestamp, working_speed_pct, temperature_c, last_car_time_sec
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


# Standalone test to verify the database works without touching p1-backend-data
if __name__ == "__main__":
    db = FactoryDB()
    sample_tick = {
        "tick": 1,
        "timestamp": "13:15:00",
        "machines": [
            {"id": "M01", "name": "Blanking Press", "stage": "Stamping", "cycle_time": 42.5, "target_cycle": 42.0, "temp": 58.2}
        ],
        "latest_car": {"car_id": "VIN-1001", "status": "PASS", "failed_at": []},
    }
    db.save_simulation_tick(sample_tick)
    print("Saved! Quality counts:", db.get_car_quality_counts())
    print("Machine logs:", db.get_recent_machine_logs("M01"))