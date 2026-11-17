import sqlite3
from pathlib import Path
from typing import Dict, Any, List

# Stores factory_twin.db inside the database/ folder automatically.
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
        """Save all machine readings and the latest completed vehicle."""
        tick = sim_output["tick"]
        timestamp = sim_output["timestamp"]
        machines = sim_output["machines"]
        latest_car = sim_output["latest_car"]

        machine_rows = []
        for machine in machines:
            speed_pct = round(
                (machine["target_cycle"] / max(machine["cycle_time"], 0.1)) * 100,
                1,
            )
            machine_rows.append((
                tick,
                timestamp,
                machine["id"],
                machine["name"],
                machine["stage"],
                speed_pct,
                machine["temp"],
                machine["cycle_time"],
            ))

        quality_status = (
            "GOOD" if latest_car["status"] == "PASS" else "BROKEN"
        )
        defect_reason = ", ".join(
            f"{defect['machine_id']} ({defect['reason']})"
            for defect in latest_car.get("failed_at", [])
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

            # IGNORE prevents an accidental duplicate VIN from replacing
            # an existing vehicle's stored quality record.
            conn.execute(
                """
                INSERT OR IGNORE INTO finished_cars (
                    car_id, tick, timestamp, quality_status, defect_reason
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    latest_car["car_id"],
                    tick,
                    timestamp,
                    quality_status,
                    defect_reason,
                ),
            )

    def get_latest_car_number(self) -> int:
        """Return the highest numeric VIN suffix stored in the database."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT MAX(CAST(SUBSTR(car_id, 5) AS INTEGER))
                FROM finished_cars
                WHERE car_id LIKE 'VIN-%'
            """).fetchone()

        return int(row[0]) if row[0] is not None else 1000

    def get_recent_machine_logs(
        self,
        machine_id: str,
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        """Fetch recent history for a single machine."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT tick, timestamp, working_speed_pct,
                       temperature_c, last_car_time_sec
                FROM machine_telemetry
                WHERE machine_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (machine_id, limit),
            ).fetchall()

        return [dict(row) for row in reversed(rows)]

    def get_car_quality_counts(self) -> Dict[str, int]:
        """Return total counts of GOOD and BROKEN finished cars."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT quality_status, COUNT(*) AS total
                FROM finished_cars
                GROUP BY quality_status
            """).fetchall()

        counts = {"GOOD": 0, "BROKEN": 0}
        for row in rows:
            counts[row["quality_status"]] = row["total"]

        return counts

    def get_telemetry_count(self) -> int:
        """Return the total number of machine telemetry rows."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM machine_telemetry"
            ).fetchone()

        return int(row[0])


if __name__ == "__main__":
    # Standalone smoke test. It uses a unique VIN and does not delete the DB.
    db = FactoryDB()
    next_vin = db.get_latest_car_number() + 1

    sample_tick = {
        "tick": 1,
        "timestamp": "13:15:00",
        "machines": [{
            "id": "M01",
            "name": "Blanking Press",
            "stage": "Stamping",
            "cycle_time": 42.5,
            "target_cycle": 42.0,
            "temp": 58.2,
        }],
        "latest_car": {
            "car_id": f"VIN-{next_vin}",
            "status": "PASS",
            "failed_at": [],
        },
    }

    db.save_simulation_tick(sample_tick)
    print("Quality counts:", db.get_car_quality_counts())
    print("Latest VIN number:", db.get_latest_car_number())
    print("Machine logs:", db.get_recent_machine_logs("M01"))
