import random
import time
from collections import deque
from typing import Dict, List, Any


class FactorySimulator:
    """
    Simulates an automobile assembly line with 17 machines across 5 stages
    and 5 inter-stage buffers, tracking per-car quality and fault propagation.
    """

    def __init__(self) -> None:
        self.tick_count: int = 0
        self.fault_mode: str = "none"  # 'none', 'welding_fault', 'bad_sensor'
        self.car_counter: int = 1000
        self.recent_cars: deque = deque(maxlen=25)

        # 5 Buffers connecting the stages (capacity = 20 chassis each)
        self.buffers: List[Dict[str, Any]] = [
            {"id": "BUF-1", "name": "Stamping -> Welding Buffer", "from_stage": "Stamping", "to_stage": "Body Welding", "level": 4, "capacity": 20},
            {"id": "BUF-2", "name": "Welding -> Paint Buffer", "from_stage": "Body Welding", "to_stage": "Paint Shop", "level": 5, "capacity": 20},
            {"id": "BUF-3", "name": "Paint -> Powertrain Buffer", "from_stage": "Paint Shop", "to_stage": "Powertrain Assembly", "level": 4, "capacity": 20},
            {"id": "BUF-4", "name": "Powertrain -> QA Buffer", "from_stage": "Powertrain Assembly", "to_stage": "Final QA", "level": 3, "capacity": 20},
            {"id": "BUF-5", "name": "Final QA Dispatch Buffer", "from_stage": "Final QA", "to_stage": "Dispatch", "level": 2, "capacity": 20},
        ]

        # 17 Machines distributed across the 5 stages
        self.machine_configs: List[Dict[str, Any]] = [
            # Stage 1: Stamping (3 machines)
            {"id": "M01", "name": "Blanking Press", "stage": "Stamping", "target_cycle": 42.0, "base_temp": 58.0, "base_vib": 2.1},
            {"id": "M02", "name": "Deep Draw Press", "stage": "Stamping", "target_cycle": 45.0, "base_temp": 64.0, "base_vib": 2.6},
            {"id": "M03", "name": "Trim & Pierce Press", "stage": "Stamping", "target_cycle": 43.0, "base_temp": 60.0, "base_vib": 2.3},
            # Stage 2: Body Welding (4 machines)
            {"id": "M04", "name": "Underbody Spot Welder", "stage": "Body Welding", "target_cycle": 48.0, "base_temp": 74.0, "base_vib": 3.0},
            {"id": "M05", "name": "Left Side Framing Robot", "stage": "Body Welding", "target_cycle": 50.0, "base_temp": 76.0, "base_vib": 3.2},
            {"id": "M06", "name": "Right Side Framing Robot", "stage": "Body Welding", "target_cycle": 50.0, "base_temp": 75.0, "base_vib": 3.1},
            {"id": "M07", "name": "Roof Laser Welder", "stage": "Body Welding", "target_cycle": 49.0, "base_temp": 79.0, "base_vib": 2.9},
            # Stage 3: Paint Shop (4 machines)
            {"id": "M08", "name": "E-Coat Dip Tank", "stage": "Paint Shop", "target_cycle": 52.0, "base_temp": 42.0, "base_vib": 1.1},
            {"id": "M09", "name": "Primer Spray Booth", "stage": "Paint Shop", "target_cycle": 54.0, "base_temp": 36.0, "base_vib": 1.4},
            {"id": "M10", "name": "Base & Clear Coat Robot", "stage": "Paint Shop", "target_cycle": 55.0, "base_temp": 38.0, "base_vib": 1.5},
            {"id": "M11", "name": "Curing Oven", "stage": "Paint Shop", "target_cycle": 53.0, "base_temp": 145.0, "base_vib": 1.2},
            # Stage 4: Powertrain Assembly (4 machines)
            {"id": "M12", "name": "Engine Decking Station", "stage": "Powertrain Assembly", "target_cycle": 56.0, "base_temp": 52.0, "base_vib": 2.4},
            {"id": "M13", "name": "Transmission Mating", "stage": "Powertrain Assembly", "target_cycle": 55.0, "base_temp": 50.0, "base_vib": 2.2},
            {"id": "M14", "name": "Suspension & Axle Torque", "stage": "Powertrain Assembly", "target_cycle": 54.0, "base_temp": 48.0, "base_vib": 2.7},
            {"id": "M15", "name": "Fluid Fill & Battery Mount", "stage": "Powertrain Assembly", "target_cycle": 52.0, "base_temp": 44.0, "base_vib": 1.8},
            # Stage 5: Final QA (2 machines)
            {"id": "M16", "name": "Wheel Alignment & Dyno", "stage": "Final QA", "target_cycle": 48.0, "base_temp": 46.0, "base_vib": 2.5},
            {"id": "M17", "name": "3D Vision & Leak Inspection", "stage": "Final QA", "target_cycle": 46.0, "base_temp": 32.0, "base_vib": 1.0},
        ]

    def inject_fault(self, fault_type: str) -> Dict[str, Any]:
        """
        Switches the simulation fault mode.
        Supported modes: 'none', 'welding_fault', 'bad_sensor'
        """
        valid_modes = {"none", "welding_fault", "bad_sensor"}
        if fault_type not in valid_modes:
            raise ValueError(f"Invalid fault_type '{fault_type}'. Choose from {valid_modes}.")

        self.fault_mode = fault_type
        return {
            "status": "updated",
            "fault_mode": self.fault_mode,
            "tick": self.tick_count,
        }

    def step(self) -> Dict[str, Any]:
        """
        Advances the factory simulation by 1 tick, updates machine telemetry,
        recalculates buffer levels, and logs a completed car's pass/fail outcome.
        """
        self.tick_count += 1
        machines_snapshot: List[Dict[str, Any]] = []
        car_defects: List[Dict[str, str]] = []

        for cfg in self.machine_configs:
            m_id = cfg["id"]
            target = cfg["target_cycle"]

            # Baseline healthy jitter
            actual_cycle = round(target + random.uniform(-1.8, 2.2), 2)
            reported_temp = round(cfg["base_temp"] + random.uniform(-1.5, 1.5), 1)
            reported_vib = round(cfg["base_vib"] + random.uniform(-0.2, 0.2), 2)
            sensor_health = "OK"
            defect_prob = 0.015  # 1.5% baseline defect probability

            # Fault Mode 1: Real physical slowdown & defect spike on M05 (Left Side Framing Robot)
            if self.fault_mode == "welding_fault" and m_id == "M05":
                actual_cycle = round(target * 1.65 + random.uniform(0.0, 4.0), 2)  # ~82-86s vs 50s target
                reported_temp = round(cfg["base_temp"] + 26.5 + random.uniform(-1.0, 2.0), 1)
                reported_vib = round(cfg["base_vib"] + 3.1 + random.uniform(-0.2, 0.4), 2)
                defect_prob = 0.65  # 65% chance of weld defect per car

            # Fault Mode 2: Corrupted sensor on M10 (Base & Clear Coat Robot) while physical cycle remains normal
            elif self.fault_mode == "bad_sensor" and m_id == "M10":
                sensor_health = "FAULTY"
                # Physically impossible / frozen spikes in telemetry while actual_cycle stays normal (~55s)
                reported_temp = round(random.choice([-99.9, 412.5, 0.0]), 1)
                reported_vib = round(random.choice([0.0, 29.8]), 2)

            # Evaluate per-car quality at this station
            machine_pass = random.random() > defect_prob
            pass_fail = "PASS" if machine_pass else "FAIL"
            if not machine_pass:
                car_defects.append({
                    "machine_id": m_id,
                    "machine_name": cfg["name"],
                    "stage": cfg["stage"],
                    "reason": "Weld integrity deviation" if m_id == "M05" else "Process tolerance drift",
                })

            machines_snapshot.append({
                "id": m_id,
                "name": cfg["name"],
                "stage": cfg["stage"],
                "cycle_time": actual_cycle,
                "target_cycle": target,
                "temp": reported_temp,
                "vibration": reported_vib,
                "sensor_health": sensor_health,
                "pass_fail": pass_fail,
            })

        # Update the 5 inter-stage buffers based on fault propagation
        self._update_buffers()

        # Record completed car exiting Final QA
        self.car_counter += 1
        overall_car_status = "FAIL" if car_defects else "PASS"
        car_record = {
            "car_id": f"VIN-{self.car_counter}",
            "tick": self.tick_count,
            "timestamp": time.strftime("%H:%M:%S"),
            "status": overall_car_status,
            "failed_at": car_defects,
        }
        self.recent_cars.appendleft(car_record)

        # Format buffers with percentage fill for downstream consumers (P3, P5, P6)
        formatted_buffers = []
        for buf in self.buffers:
            fill_pct = round((buf["level"] / buf["capacity"]) * 100, 1)
            formatted_buffers.append({
                **buf,
                "fill_percent": fill_pct,
            })

        return {
            "tick": self.tick_count,
            "timestamp": time.strftime("%H:%M:%S"),
            "fault_mode": self.fault_mode,
            "machines": machines_snapshot,
            "buffers": formatted_buffers,
            "latest_car": car_record,
            "recent_cars": list(self.recent_cars),
        }

    def _update_buffers(self) -> None:
        """
        Adjusts buffer levels dynamically:
        - Normal / Bad Sensor: buffers hover smoothly around 20-30% (4-6 units).
        - Welding Fault (M05 slowdown): BUF-1 backs up toward capacity (blocking Stamping),
          while BUF-2, BUF-3, BUF-4 drain toward 0 (starving Paint, Powertrain, QA).
        """
        if self.fault_mode == "welding_fault":
            # BUF-1 (Stamping -> Body Welding) fills up rapidly due to M05 bottleneck
            self.buffers[0]["level"] = min(self.buffers[0]["capacity"], self.buffers[0]["level"] + random.randint(1, 2))
            # Downstream buffers starve
            self.buffers[1]["level"] = max(0, self.buffers[1]["level"] - 1)
            self.buffers[2]["level"] = max(0, self.buffers[2]["level"] - 1)
            self.buffers[3]["level"] = max(1, self.buffers[3]["level"] - random.randint(0, 1))
            self.buffers[4]["level"] = max(1, self.buffers[4]["level"] - random.randint(0, 1))
        else:
            # Gradual recovery / normal balanced flow
            targets = [4, 5, 4, 3, 2]
            for idx, buf in enumerate(self.buffers):
                target_lvl = targets[idx]
                if buf["level"] > target_lvl:
                    buf["level"] -= 1
                elif buf["level"] < target_lvl:
                    buf["level"] += 1
                else:
                    buf["level"] = max(1, min(buf["capacity"] - 2, buf["level"] + random.choice([-1, 0, 1])))


# Quick standalone test for P1's 3 test cases (no fault, welding fault, bad sensor)
if __name__ == "__main__":
    sim = FactorySimulator()

    print("--- TEST 1: NO FAULT ---")
    sim.inject_fault("none")
    out1 = sim.step()
    print(f"Tick {out1['tick']} | Machines: {len(out1['machines'])} | BUF-1: {out1['buffers'][0]['fill_percent']}% | Car: {out1['latest_car']['status']}")

    print("\n--- TEST 2: WELDING FAULT ---")
    sim.inject_fault("welding_fault")
    for _ in range(5):
        out2 = sim.step()
    m05 = next(m for m in out2["machines"] if m["id"] == "M05")
    print(f"Tick {out2['tick']} | M05 Cycle: {m05['cycle_time']}s | BUF-1: {out2['buffers'][0]['fill_percent']}% | BUF-2: {out2['buffers'][1]['fill_percent']}% | Car: {out2['latest_car']['status']}")

    print("\n--- TEST 3: BAD SENSOR ---")
    sim.inject_fault("bad_sensor")
    out3 = sim.step()
    m10 = next(m for m in out3["machines"] if m["id"] == "M10")
    print(f"Tick {out3['tick']} | M10 Cycle: {m10['cycle_time']}s | Temp: {m10['temp']} | Sensor: {m10['sensor_health']}")