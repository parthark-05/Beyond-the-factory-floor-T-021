"""
backend/factory_map.py
======================
Factory topology + bottleneck propagation for a 17-machine, 5-buffer
automobile assembly line.

Line layout (cars flow left to right)
-------------------------------------
S1 Stamping      : [M01 || M02]
        B1
S2 Body Shop     : M03 -> [M04 || M05] -> M06
        B2
S3 Paint Shop    : M07 -> M08 -> M09 -> M10
        B3
S4 Assembly      : M11 -> M12 -> M13
        B4
S5 Final Line    : M14 -> M15 -> M16
        B5
S6 Inspection    : M17

Machines inside a stage are directly coupled (no inner buffer). The 5 buffers
sit between stages. "||" means parallel machines sharing the work of a step.

Model
-----
A fluid (cars/min) model. Each stage has a capacity = min over its steps of
the summed rate of the machines in that step. The line is paced by a takt
demand (default 1.0 car/min), so every stage runs at min(capacity, demand)
unless a buffer is empty (starved) or full (blocked). "Who gets hit and when"
is answered by stepping that model forward and recording the first time each
stage becomes blocked (upstream of the bottleneck) or starved (downstream).

Public API
----------
    fm = FactoryMap()
    fm.update_machine("M09", cycle_time_s=95, status="degraded", health=58)
    fm.update_buffers({"B1": 45, "B2": 62, "B3": 40, "B4": 50, "B5": 50})
    snap = fm.snapshot()      # JSON-serializable dict
    text = fm.to_json()       # same thing as a JSON string

Snapshot keys: nodes, edges, buffers, bottleneck, cascade_timeline, summary.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Tunables
# --------------------------------------------------------------------------- #
DEMAND_RATE = 1.0               # cars/min the line is paced to (60 JPH)
SIM_DT_MIN = 0.1                # simulation step (minutes)
SIM_HORIZON_MIN = 240.0         # how far ahead the cascade is predicted
INTRA_STAGE_LAG_MIN = 0.5       # assumed delay per step when a stage blocks/starves
                                # (machines in a stage have no inner buffer)
BOTTLENECK_SCORE_THRESHOLD = 0.30
EPS = 1e-6

STATUSES = {"running", "degraded", "down", "maintenance"}

# --------------------------------------------------------------------------- #
# Static line definition
# --------------------------------------------------------------------------- #
STAGES: List[Dict[str, Any]] = [
    {"id": "S1", "name": "Stamping",         "steps": [["M01", "M02"]]},
    {"id": "S2", "name": "Body Shop",        "steps": [["M03"], ["M04", "M05"], ["M06"]]},
    {"id": "S3", "name": "Paint Shop",       "steps": [["M07"], ["M08"], ["M09"], ["M10"]]},
    {"id": "S4", "name": "Assembly",         "steps": [["M11"], ["M12"], ["M13"]]},
    {"id": "S5", "name": "Final Line",       "steps": [["M14"], ["M15"], ["M16"]]},
    {"id": "S6", "name": "Final Inspection", "steps": [["M17"]]},
]

# machine id -> (name, nominal cycle time in seconds)
MACHINE_SPECS: Dict[str, Tuple[str, float]] = {
    "M01": ("Press Line A", 105.0),
    "M02": ("Press Line B", 105.0),
    "M03": ("Body Framing", 50.0),
    "M04": ("Weld Cell A", 100.0),
    "M05": ("Weld Cell B", 100.0),
    "M06": ("Body Finishing", 52.0),
    "M07": ("Pretreatment", 48.0),
    "M08": ("Primer / E-Coat", 50.0),
    "M09": ("Paint Booth", 52.0),
    "M10": ("Curing Oven", 50.0),
    "M11": ("Chassis Marriage", 50.0),
    "M12": ("Powertrain Install", 52.0),
    "M13": ("Interior Install", 50.0),
    "M14": ("Wheel Alignment", 48.0),
    "M15": ("Fluid Fill", 46.0),
    "M16": ("Test Bench", 50.0),
    "M17": ("Final Inspection", 48.0),
}

# Buffer i sits between stage i and stage i+1. (id, name, capacity in cars)
BUFFER_SPECS: List[Tuple[str, str, int]] = [
    ("B1", "Stamping \u2192 Body Buffer", 40),
    ("B2", "Body \u2192 Paint Buffer", 30),
    ("B3", "Paint \u2192 Assembly Buffer", 25),
    ("B4", "Assembly \u2192 Final Line Buffer", 20),
    ("B5", "Final Line \u2192 Inspection Buffer", 15),
]


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# --------------------------------------------------------------------------- #
# State containers
# --------------------------------------------------------------------------- #
@dataclass
class Machine:
    id: str
    name: str
    stage_idx: int
    step_idx: int
    nominal_cycle_s: float
    cycle_time_s: float
    status: str = "running"
    health: float = 100.0

    def rate(self) -> float:
        """Throughput in cars/min (0 when offline)."""
        if self.status in ("down", "maintenance") or self.cycle_time_s <= 0:
            return 0.0
        return 60.0 / self.cycle_time_s

    def cycle_ratio(self) -> Optional[float]:
        """actual / nominal cycle time; None when the machine is offline."""
        if self.rate() == 0.0:
            return None
        return self.cycle_time_s / self.nominal_cycle_s

    def effective_status(self) -> str:
        if self.status in ("down", "maintenance"):
            return self.status
        ratio = self.cycle_ratio() or 1.0
        if self.status == "degraded" or ratio >= 1.10 or self.health < 60:
            return "degraded"
        return "running"


@dataclass
class Buffer:
    id: str
    name: str
    capacity: int
    from_stage: int
    to_stage: int
    level_pct: float = 50.0

    @property
    def level_cars(self) -> float:
        return self.capacity * self.level_pct / 100.0


# --------------------------------------------------------------------------- #
# FactoryMap
# --------------------------------------------------------------------------- #
class FactoryMap:
    def __init__(
        self,
        demand_rate: float = DEMAND_RATE,
        horizon_min: float = SIM_HORIZON_MIN,
        dt_min: float = SIM_DT_MIN,
    ) -> None:
        self.demand = float(demand_rate)
        self.horizon_min = float(horizon_min)
        self.dt = float(dt_min)
        self._lock = threading.RLock()

        self.machines: Dict[str, Machine] = {}
        for si, stage in enumerate(STAGES):
            for ki, step in enumerate(stage["steps"]):
                for mid in step:
                    name, nominal = MACHINE_SPECS[mid]
                    self.machines[mid] = Machine(mid, name, si, ki, nominal, nominal)

        self.buffer_list: List[Buffer] = [
            Buffer(bid, name, cap, i, i + 1) for i, (bid, name, cap) in enumerate(BUFFER_SPECS)
        ]
        self.buffers: Dict[str, Buffer] = {b.id: b for b in self.buffer_list}
        # (timestamp_s, level_pct) samples used to estimate observed fill rates
        self._history: Dict[str, Deque[Tuple[float, float]]] = {
            b.id: deque(maxlen=120) for b in self.buffer_list
        }

        self._build_topology()
        assert len(self.machines) == 17 and len(self.buffer_list) == 5

    # ------------------------------------------------------------------ #
    # Topology (directed graph as a dictionary adjacency list)
    # ------------------------------------------------------------------ #
    def _build_topology(self) -> None:
        edges: List[Dict[str, Any]] = []
        n_buf = len(self.buffer_list)
        for si, stage in enumerate(STAGES):
            steps = stage["steps"]
            for k in range(len(steps) - 1):          # machine -> machine inside a stage
                for a in steps[k]:
                    for b in steps[k + 1]:
                        edges.append({"source": a, "target": b, "kind": "series",
                                      "buffer_id": None, "stage_idx": si})
            if si < n_buf:                           # stage -> buffer -> next stage
                bid = self.buffer_list[si].id
                for a in steps[-1]:
                    edges.append({"source": a, "target": bid, "kind": "to_buffer",
                                  "buffer_id": bid, "stage_idx": si})
                for b in STAGES[si + 1]["steps"][0]:
                    edges.append({"source": bid, "target": b, "kind": "from_buffer",
                                  "buffer_id": bid, "stage_idx": si + 1})
        self._edges_static = edges

        adj: Dict[str, List[str]] = {m: [] for m in self.machines}
        adj.update({b.id: [] for b in self.buffer_list})
        for e in edges:
            adj[e["source"]].append(e["target"])
        self.adjacency: Dict[str, List[str]] = adj
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        indeg = {n: 0 for n in self.adjacency}
        for targets in self.adjacency.values():
            for t in targets:
                indeg[t] += 1
        queue = [n for n, d in indeg.items() if d == 0]
        seen = 0
        while queue:
            n = queue.pop()
            seen += 1
            for t in self.adjacency[n]:
                indeg[t] -= 1
                if indeg[t] == 0:
                    queue.append(t)
        if seen != len(self.adjacency):
            raise ValueError("Factory graph contains a cycle")

    # ------------------------------------------------------------------ #
    # Live updates
    # ------------------------------------------------------------------ #
    def update_machine(
        self,
        machine_id: str,
        *,
        cycle_time_s: Optional[float] = None,
        status: Optional[str] = None,
        health: Optional[float] = None,
    ) -> None:
        with self._lock:
            if machine_id not in self.machines:
                raise KeyError(f"Unknown machine '{machine_id}'")
            m = self.machines[machine_id]
            if cycle_time_s is not None:
                m.cycle_time_s = float(cycle_time_s)
            if status is not None:
                if status not in STATUSES:
                    raise ValueError(f"status must be one of {sorted(STATUSES)}")
                m.status = status
            if health is not None:
                m.health = _clamp(float(health), 0.0, 100.0)

    def update_buffer(self, buffer_id: str, level_pct: float,
                      timestamp: Optional[float] = None) -> None:
        with self._lock:
            if buffer_id not in self.buffers:
                raise KeyError(f"Unknown buffer '{buffer_id}'")
            level = _clamp(float(level_pct), 0.0, 100.0)
            self.buffers[buffer_id].level_pct = level
            ts = time.time() if timestamp is None else float(timestamp)
            self._history[buffer_id].append((ts, level))

    def update_buffers(self, levels_pct: Dict[str, float],
                       timestamp: Optional[float] = None) -> None:
        with self._lock:
            for bid, lvl in levels_pct.items():
                self.update_buffer(bid, lvl, timestamp)

    def _observed_rate(self, buf_idx: int) -> Optional[float]:
        """Least-squares fill rate in %/min over the last 10 min of samples."""
        hist = self._history[self.buffer_list[buf_idx].id]
        if len(hist) < 2:
            return None
        t_end = hist[-1][0]
        pts = [(t, l) for t, l in hist if t >= t_end - 600]
        if len(pts) < 2 or pts[-1][0] - pts[0][0] < 30:
            return None
        n = len(pts)
        mt = sum(t for t, _ in pts) / n
        ml = sum(l for _, l in pts) / n
        den = sum((t - mt) ** 2 for t, _ in pts)
        if den == 0:
            return None
        return sum((t - mt) * (l - ml) for t, l in pts) / den * 60.0

    # ------------------------------------------------------------------ #
    # Capacities and bottleneck detection
    # ------------------------------------------------------------------ #
    def _stage_capacities(self) -> Tuple[List[float], List[int]]:
        """Per stage: capacity (cars/min) and index of the limiting step."""
        caps: List[float] = []
        limiting: List[int] = []
        for stage in STAGES:
            best_cap, best_k = None, 0
            for k, step in enumerate(stage["steps"]):
                cap = sum(self.machines[m].rate() for m in step)
                if best_cap is None or cap < best_cap:
                    best_cap, best_k = cap, k
            caps.append(best_cap or 0.0)
            limiting.append(best_k)
        return caps, limiting

    @staticmethod
    def _ratio_term(m: Machine) -> float:
        """0 = at nominal cycle time, 1 = 50%+ slower or offline."""
        if m.rate() == 0.0:
            return 1.0
        return _clamp((m.cycle_time_s / m.nominal_cycle_s - 1.0) / 0.5, 0.0, 1.0)

    def _limiting_machine(self, stage_idx: int, limiting: List[int]) -> Machine:
        step = STAGES[stage_idx]["steps"][limiting[stage_idx]]
        return max((self.machines[m] for m in step),
                   key=lambda m: (self._ratio_term(m), -m.rate()))

    def _detect_bottleneck(self, caps: List[float], limiting: List[int]) -> Optional[Dict[str, Any]]:
        """
        Score each stage's limiting machine on three signals:
          0.50  cycle time ratio (actual / nominal)
          0.25  upstream buffer buildup (input buffer fill, boosted if rising)
          0.25  downstream starvation (1 - output buffer fill, boosted if falling)
        Signals that do not exist (no buffer before S1 / after S6) are dropped
        and the weights renormalised. A stage must also be a real constraint.
        """
        best: Optional[Tuple[Tuple[float, float], Dict[str, Any]]] = None
        for si in range(len(STAGES)):
            m = self._limiting_machine(si, limiting)
            rt = self._ratio_term(m)

            up = down = None
            if si > 0:
                up = self.buffer_list[si - 1].level_pct / 100.0
                obs = self._observed_rate(si - 1)
                if obs is not None and obs > 0.1:
                    up = min(1.0, up + 0.15)
            if si < len(self.buffer_list):
                down = 1.0 - self.buffer_list[si].level_pct / 100.0
                obs = self._observed_rate(si)
                if obs is not None and obs < -0.1:
                    down = min(1.0, down + 0.15)

            parts = [(0.50, rt)]
            if up is not None:
                parts.append((0.25, up))
            if down is not None:
                parts.append((0.25, down))
            score = sum(w * v for w, v in parts) / sum(w for w, _ in parts)

            is_constraint = caps[si] < self.demand * 1.05 or (
                rt > 0 and (up or 0.0) >= 0.6 and (down is None or down >= 0.4)
            )
            if not is_constraint or score < BOTTLENECK_SCORE_THRESHOLD:
                continue

            ratio = m.cycle_ratio()
            info = {
                "machine_id": m.id,
                "machine_name": m.name,
                "stage_id": STAGES[si]["id"],
                "stage_idx": si,
                "score": round(score, 3),
                "cycle_ratio": None if ratio is None else round(ratio, 3),
                "stage_capacity_cars_per_min": round(caps[si], 3),
                "evidence": {
                    "upstream_buffer_fill_pct": None if up is None else round(up * 100, 1),
                    "downstream_starvation_pct": None if down is None else round(down * 100, 1),
                },
            }
            key = (score, -caps[si])
            if best is None or key > best[0]:
                best = (key, info)
        return None if best is None else best[1]

    # ------------------------------------------------------------------ #
    # Fluid simulation: the engine behind "who gets hit and when"
    # ------------------------------------------------------------------ #
    def _simulate(self, caps: List[float]) -> Dict[str, Any]:
        n = len(STAGES)
        nb = len(self.buffer_list)
        dt = self.dt
        capacity = [float(b.capacity) for b in self.buffer_list]
        level = [b.level_cars for b in self.buffer_list]
        base = [min(c, self.demand) for c in caps]

        def rates(lv: List[float]) -> List[float]:
            r = base[:]
            for _ in range(3 * n):
                changed = False
                for i in range(1, n):                       # starvation limit
                    lim = r[i - 1] + lv[i - 1] / dt
                    if r[i] > lim + 1e-12:
                        r[i], changed = lim, True
                for i in range(n - 2, -1, -1):              # blocking limit
                    lim = r[i + 1] + (capacity[i] - lv[i]) / dt
                    if r[i] > lim + 1e-12:
                        r[i], changed = lim, True
                if not changed:
                    break
            return r

        events: Dict[Tuple[int, str], float] = {}
        r0: List[float] = []
        steps = int(self.horizon_min / dt) + 1
        for k in range(steps):
            r = rates(level)
            if k == 0:
                r0 = r[:]
            t = round(k * dt, 4)
            for i in range(n):
                if r[i] >= base[i] - EPS:
                    continue                                # running at full pace
                if i < nb and level[i] >= capacity[i] - EPS:
                    kind = "blocked"
                elif i > 0 and level[i - 1] <= EPS:
                    kind = "starved"
                else:
                    continue
                events.setdefault((i, kind), t)
            for i in range(nb):
                level[i] = _clamp(level[i] + (r[i] - r[i + 1]) * dt, 0.0, capacity[i])
        return {"r0": r0, "events": events}

    # ------------------------------------------------------------------ #
    # Snapshot
    # ------------------------------------------------------------------ #
    @staticmethod
    def _severity(minutes: float) -> str:
        if minutes <= 5:
            return "critical"
        if minutes <= 20:
            return "high"
        if minutes <= 60:
            return "medium"
        return "low"

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            caps, limiting = self._stage_capacities()
            bottleneck = self._detect_bottleneck(caps, limiting)
            sim = self._simulate(caps)
            r0: List[float] = sim["r0"]
            n_buf = len(self.buffer_list)

            # Cause attribution: detected bottleneck, else the physical constraint.
            cause: Optional[Machine] = None
            if bottleneck is not None:
                cause = self.machines[bottleneck["machine_id"]]
            else:
                si_min = min(range(len(STAGES)), key=lambda i: caps[i])
                if caps[si_min] < self.demand - EPS:
                    cause = self._limiting_machine(si_min, limiting)

            # ---- cascade timeline ------------------------------------ #
            machine_event: Dict[str, Dict[str, Any]] = {}
            for (si, kind), t in sim["events"].items():
                if cause is not None and si == cause.stage_idx:
                    continue
                steps = STAGES[si]["steps"]
                ns = len(steps)
                bidx = si if kind == "blocked" else si - 1
                buf = self.buffer_list[bidx]
                away = abs(si - cause.stage_idx) if cause else None
                for ki, step in enumerate(steps):
                    lag = (ns - 1 - ki) * INTRA_STAGE_LAG_MIN if kind == "blocked" \
                        else ki * INTRA_STAGE_LAG_MIN
                    minute = round(t + lag, 1)
                    for mid in step:
                        m = self.machines[mid]
                        if kind == "blocked":
                            reason = (f"{buf.name} ({buf.id}) projected to reach 100%; "
                                      f"{m.name} cannot discharge cars")
                        else:
                            reason = (f"{buf.name} ({buf.id}) projected to run empty; "
                                      f"{m.name} receives no cars")
                        ev = {
                            "machine_id": mid,
                            "machine_name": m.name,
                            "stage_id": STAGES[si]["id"],
                            "impact_type": kind,
                            "side": "upstream" if kind == "blocked" else "downstream",
                            "minutes_until_impact": minute,
                            "status": "active" if minute <= 0 else "predicted",
                            "severity": "critical" if minute <= 0 else self._severity(minute),
                            "trigger_buffer": buf.id,
                            "cause_machine": cause.id if cause else None,
                            "stages_away": away,
                            "reason": reason,
                        }
                        prev = machine_event.get(mid)
                        if prev is None or minute < prev["minutes_until_impact"]:
                            machine_event[mid] = ev
            timeline = sorted(
                machine_event.values(),
                key=lambda e: (e["minutes_until_impact"],
                               e["stages_away"] if e["stages_away"] is not None else 0,
                               e["machine_id"]),
            )

            # ---- nodes ------------------------------------------------ #
            nodes: List[Dict[str, Any]] = []
            for mid, m in self.machines.items():
                ratio = m.cycle_ratio()
                ev = machine_event.get(mid)
                is_bn = bottleneck is not None and bottleneck["machine_id"] == mid
                if m.status in ("down", "maintenance"):
                    flow_state = "offline"
                elif ev and ev["minutes_until_impact"] <= 0:
                    flow_state = ev["impact_type"]
                else:
                    flow_state = "running"
                if is_bn:
                    role = "bottleneck"
                elif ev:
                    role = "upstream_blocked" if ev["impact_type"] == "blocked" else "downstream_starved"
                else:
                    role = "unaffected"
                nodes.append({
                    "id": mid,
                    "name": m.name,
                    "stage_id": STAGES[m.stage_idx]["id"],
                    "stage_name": STAGES[m.stage_idx]["name"],
                    "step_index": m.step_idx,
                    "health": round(m.health, 1),
                    "status": m.effective_status(),
                    "flow_state": flow_state,
                    "cycle_time_s": round(m.cycle_time_s, 2),
                    "nominal_cycle_time_s": m.nominal_cycle_s,
                    "cycle_ratio": None if ratio is None else round(ratio, 3),
                    "rate_cars_per_min": round(m.rate(), 3),
                    "is_bottleneck": is_bn,
                    "bottleneck_score": bottleneck["score"] if is_bn else None,
                    "impact_role": role,
                    "predicted_impact": None if ev is None else {
                        "type": ev["impact_type"],
                        "minutes_until_impact": ev["minutes_until_impact"],
                        "severity": ev["severity"],
                    },
                })

            # ---- edges ------------------------------------------------ #
            share: Dict[str, float] = {}
            for stage in STAGES:
                for step in stage["steps"]:
                    total = sum(self.machines[m].rate() for m in step)
                    for mid in step:
                        share[mid] = self.machines[mid].rate() / total if total > 0 else 0.0

            edges: List[Dict[str, Any]] = []
            for e in self._edges_static:
                flow_stage = r0[e["stage_idx"]]
                kind = e["kind"]
                if kind == "series":
                    flow = flow_stage * share[e["source"]] * share[e["target"]]
                elif kind == "to_buffer":
                    flow = flow_stage * share[e["source"]]
                else:
                    flow = flow_stage * share[e["target"]]
                status = "flowing"
                if kind in ("to_buffer", "from_buffer"):
                    lvl = self.buffers[e["buffer_id"]].level_pct
                    if kind == "to_buffer":
                        if lvl >= 99:
                            status = "blocked"
                        elif lvl >= 80:
                            status = "congested"
                    else:
                        if lvl <= 1:
                            status = "starved"
                        elif lvl <= 15:
                            status = "low"
                if flow < 0.01 and status == "flowing":
                    status = "stalled"
                edges.append({
                    "id": f"{e['source']}->{e['target']}",
                    "source": e["source"],
                    "target": e["target"],
                    "type": kind,
                    "buffer_id": e["buffer_id"],
                    "flow_rate_cars_per_min": round(flow, 3),
                    "flow_status": status,
                })

            # ---- buffers ---------------------------------------------- #
            buffers: List[Dict[str, Any]] = []
            for i, b in enumerate(self.buffer_list):
                net = r0[i] - r0[i + 1]                       # cars/min
                pct_rate = net / b.capacity * 100.0
                obs = self._observed_rate(i)
                to_full = (b.capacity - b.level_cars) / net if net > EPS and b.level_pct < 100 else None
                to_empty = b.level_cars / -net if net < -EPS and b.level_pct > 0 else None
                if b.level_pct >= 99:
                    state = "full"
                elif b.level_pct <= 1:
                    state = "empty"
                elif b.level_pct >= 80:
                    state = "high"
                elif b.level_pct <= 15:
                    state = "low"
                else:
                    state = "normal"
                buffers.append({
                    "id": b.id,
                    "name": b.name,
                    "from_stage": STAGES[b.from_stage]["id"],
                    "to_stage": STAGES[b.to_stage]["id"],
                    "capacity_cars": b.capacity,
                    "level_cars": round(b.level_cars, 2),
                    "level_pct": round(b.level_pct, 1),
                    "fill_rate_pct_per_min": round(pct_rate, 3),
                    "observed_fill_rate_pct_per_min": None if obs is None else round(obs, 3),
                    "trend": "rising" if pct_rate > 0.05 else "falling" if pct_rate < -0.05 else "stable",
                    "minutes_to_full": None if to_full is None else round(to_full, 1),
                    "minutes_to_empty": None if to_empty is None else round(to_empty, 1),
                    "status": state,
                })

            # ---- summary ---------------------------------------------- #
            steady = min(self.demand, min(caps))
            summary = {
                "demand_cars_per_min": self.demand,
                "current_throughput_cars_per_min": round(r0[-1], 3),
                "steady_state_throughput_cars_per_min": round(steady, 3),
                "steady_state_pct_of_demand": round(100.0 * steady / self.demand, 1),
                "projected_loss_cars_per_hour": round(max(0.0, self.demand - steady) * 60.0, 1),
                "upstream_machines_affected": sum(1 for e in timeline if e["side"] == "upstream"),
                "downstream_machines_affected": sum(1 for e in timeline if e["side"] == "downstream"),
                "first_impact_minutes": timeline[0]["minutes_until_impact"] if timeline else None,
                "prediction_horizon_min": self.horizon_min,
            }

            return {
                "timestamp": round(time.time(), 3),
                "nodes": nodes,
                "edges": edges,
                "buffers": buffers,
                "bottleneck": bottleneck,
                "cascade_timeline": timeline,
                "summary": summary,
            }

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.snapshot(), indent=indent, allow_nan=False)


# Shared instance for the FastAPI app: `from factory_map import get_factory_map`
_default_map: Optional[FactoryMap] = None


def get_factory_map() -> FactoryMap:
    global _default_map
    if _default_map is None:
        _default_map = FactoryMap()
    return _default_map


# --------------------------------------------------------------------------- #
# Demo / self-check:  python factory_map.py
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    fm = FactoryMap()
    fm.update_buffers({"B1": 50, "B2": 50, "B3": 50, "B4": 50, "B5": 50})

    base = fm.snapshot()
    assert len(base["nodes"]) == 17 and len(base["buffers"]) == 5
    assert base["bottleneck"] is None and base["cascade_timeline"] == [], "nominal line must be quiet"
    print("Nominal line: no bottleneck, empty cascade  [ok]")

    # Scenario: paint booth slows from 52 s to 95 s per car
    fm.update_machine("M09", cycle_time_s=95, status="degraded", health=58)
    fm.update_buffers({"B1": 45, "B2": 62, "B3": 40, "B4": 50, "B5": 50})
    snap = fm.snapshot()
    json.dumps(snap, allow_nan=False)                      # must be JSON-safe

    bn = snap["bottleneck"]
    assert bn and bn["machine_id"] == "M09", bn
    print(f"\nBottleneck: {bn['machine_id']} {bn['machine_name']}  "
          f"score={bn['score']}  cycle_ratio={bn['cycle_ratio']}")
    s = snap["summary"]
    print(f"Steady-state throughput {s['steady_state_throughput_cars_per_min']} cars/min "
          f"({s['steady_state_pct_of_demand']}% of demand), "
          f"loss {s['projected_loss_cars_per_hour']} cars/hour")

    print("\nBuffers:")
    for b in snap["buffers"]:
        print(f"  {b['id']} {b['level_pct']:>5}%  rate {b['fill_rate_pct_per_min']:>+7.3f} %/min  "
              f"full in {b['minutes_to_full']}  empty in {b['minutes_to_empty']}")

    print("\nCascade timeline (who gets hit, and when):")
    for e in snap["cascade_timeline"]:
        print(f"  t+{e['minutes_until_impact']:>6} min  {e['machine_id']} {e['machine_name']:<20} "
              f"{e['impact_type']:<8} [{e['severity']}]  via {e['trigger_buffer']}")

    sides = {e["side"] for e in snap["cascade_timeline"]}
    assert sides == {"upstream", "downstream"}
    times = [e["minutes_until_impact"] for e in snap["cascade_timeline"]]
    assert times == sorted(times)
    print(f"\nAffected: {s['upstream_machines_affected']} upstream, "
          f"{s['downstream_machines_affected']} downstream  [ok]")
