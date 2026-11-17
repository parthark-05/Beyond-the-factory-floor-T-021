
import pandas as pd
import networkx as nx

FLAG_THRESHOLD = 35

SIMULATED_DATA_NOTICE = (
    "DEMO MODE: Factory readings are simulated. "
    "Risk scores indicate possible causes, not proven faults."
)

ALL_MACHINES = [
    "Blank Press",
    "Draw Press",
    "Weld Robot 1",
    "Weld Robot 2",
    "Weld Robot 3",
    "Body Conveyor",
    "Paint Booth",
    "Curing Oven",
    "Paint Conveyor",
    "Engine Line",
    "Gearbox Line",
    "Engine Test",
    "Marriage",
    "Trim Line",
    "Wheel Fit",
    "Vision Check",
    "End-of-Line Inspection"
]

# Machine positions for the interactive factory flowchart
NODE_POSITIONS = {
    "Blank Press": (0, 2),
    "Draw Press": (1.5, 2),
    "Weld Robot 1": (3, 2.5),
    "Weld Robot 2": (4.5, 2.5),
    "Weld Robot 3": (6, 2.5),
    "Body Conveyor": (7.5, 2),
    "Paint Booth": (8.5, 2),
    "Curing Oven": (9, 1.5),
    "Paint Conveyor": (9.5, 2),
    "Engine Line": (3, 0),
    "Gearbox Line": (5, 0),
    "Engine Test": (7, 0),
    "Marriage": (10, 1),
    "Trim Line": (11, 1),
    "Wheel Fit": (11.8, 1),
    "Vision Check": (12.5, 1),
    "End-of-Line Inspection": (13.2, 1)
}


# -------------------------------------------------
# FACTORY DEPENDENCY GRAPH
# -------------------------------------------------

def build_factory_graph():
    graph = nx.DiGraph()
    graph.add_nodes_from(ALL_MACHINES)

    edges = [
        ("Blank Press", "Draw Press"),

        ("Draw Press", "Weld Robot 1"),
        ("Draw Press", "Weld Robot 2"),
        ("Draw Press", "Weld Robot 3"),

        ("Weld Robot 1", "Body Conveyor"),
        ("Weld Robot 2", "Body Conveyor"),
        ("Weld Robot 3", "Body Conveyor"),

        ("Body Conveyor", "Paint Booth"),
        ("Paint Booth", "Curing Oven"),
        ("Curing Oven", "Paint Conveyor"),
        ("Paint Conveyor", "Marriage"),

        ("Engine Line", "Engine Test"),
        ("Gearbox Line", "Engine Test"),
        ("Engine Test", "Marriage"),

        ("Marriage", "Trim Line"),
        ("Trim Line", "Wheel Fit"),
        ("Wheel Fit", "Vision Check"),
        ("Vision Check", "End-of-Line Inspection")
    ]

    graph.add_edges_from(edges)
    return graph


# -------------------------------------------------
# SAMPLE FACTORY DATA
# -------------------------------------------------

def get_sample_readings(mode="weld_failure"):
    rows = []

    for i, machine in enumerate(ALL_MACHINES):

        failed = (
            mode == "weld_failure"
            and machine == "Weld Robot 2"
        )

        rows.append({
            "machine": machine,
            "temperature": 95 if failed else 65 + (i % 5) * 2,
            "processing_time": 18 if failed else 10 + (i % 4),
            "output_per_hour": 20 if failed else 55 + (i % 6) * 3,
            "downtime_minutes": 35 if failed else 2,
            "buffer_qty": 45 if failed else 10 + (i % 5),
            "defect_count": 8 if failed else i % 2
        })

    return pd.DataFrame(rows)


def get_sample_defects():
    return pd.DataFrame([
        {
            "car_id": "CAR-101",
            "defect_type": "Weld defect",
            "verified_machine": ""
        },
        {
            "car_id": "CAR-102",
            "defect_type": "Paint scratch",
            "verified_machine": ""
        },
        {
            "car_id": "CAR-103",
            "defect_type": "Engine test failure",
            "verified_machine": ""
        }
    ])


# -------------------------------------------------
# ROOT CAUSE RANKING ENGINE
# -------------------------------------------------

def analyze_factory(readings, operator_confirmations=None):

    graph = build_factory_graph()
    operator_confirmations = operator_confirmations or {}

    if readings is None or readings.empty:
        return {
            "ranking": pd.DataFrame(),
            "graph": graph,
            "top_cause": None,
            "warnings": ["No machine readings supplied."]
        }

    df = readings.copy()

    if "machine" not in df.columns and "machine_name" in df.columns:
        df = df.rename(columns={"machine_name": "machine"})

    required_columns = [
        "temperature",
        "processing_time",
        "output_per_hour",
        "downtime_minutes",
        "buffer_qty",
        "defect_count"
    ]

    warnings = []

    for column in required_columns:
        if column not in df.columns:
            df[column] = 0
            warnings.append(
                f"Missing {column}; treated as zero."
            )

    records = []

    for machine in ALL_MACHINES:

        machine_data = df[df["machine"] == machine]

        if machine_data.empty:
            continue

        row = machine_data.iloc[-1]

        # Risk score based on machine readings
        pts_temperature = (
            25 if row["temperature"] >= 85
            else 12 if row["temperature"] >= 75
            else 0
        )

        pts_processing = (
            20 if row["processing_time"] >= 16
            else 10 if row["processing_time"] >= 13
            else 0
        )

        pts_output = (
            20 if row["output_per_hour"] < 30
            else 10 if row["output_per_hour"] < 45
            else 0
        )

        pts_downtime = (
            15 if row["downtime_minutes"] >= 20
            else 7 if row["downtime_minutes"] >= 10
            else 0
        )

        pts_buffer = (
            10 if row["buffer_qty"] >= 35
            else 5 if row["buffer_qty"] >= 20
            else 0
        )

        pts_defects = (
            10 if row["defect_count"] >= 5
            else 5 if row["defect_count"] >= 3
            else 0
        )

        score = min(
            100,
            pts_temperature
            + pts_processing
            + pts_output
            + pts_downtime
            + pts_buffer
            + pts_defects
        )

        confirmed = machine in operator_confirmations

        label = "CONFIRMED" if confirmed else "INFERRED"

        reasons = []

        if pts_temperature:
            reasons.append("High machine temperature")

        if pts_processing:
            reasons.append("Long processing time")

        if pts_output:
            reasons.append("Low production output")

        if pts_downtime:
            reasons.append("High machine downtime")

        if pts_buffer:
            reasons.append("Buffer accumulation")

        if pts_defects:
            reasons.append("Elevated defect count")

        advice = []

        if pts_temperature:
            advice.append("Inspect cooling and temperature controls.")

        if pts_processing:
            advice.append("Check machine cycle time and operating settings.")

        if pts_output:
            advice.append("Inspect machine performance and material supply.")

        if pts_downtime:
            advice.append("Review downtime logs and maintenance history.")

        if pts_buffer:
            advice.append("Inspect upstream and downstream material flow.")

        if pts_defects:
            advice.append("Inspect tooling and product quality.")

        if not advice:
            advice.append("Continue monitoring machine operation.")

        records.append({
            "machine": machine,
            "area": "Production",
            "risk_score": round(score, 1),
            "risk_level": (
                "Critical" if score >= 65
                else "Warning" if score >= FLAG_THRESHOLD
                else "Normal"
            ),
            "flagged": score >= FLAG_THRESHOLD or confirmed,
            "label": label,
            "label_reason": (
                "Operator-confirmed fault"
                if confirmed
                else "Inferred from machine readings"
            ),
            "reasons": "; ".join(reasons) if reasons else "No abnormal readings",
            "reason_list": reasons,
            "advice_list": advice,
            "pts_temperature": pts_temperature,
            "pts_processing_time": pts_processing,
            "pts_output": pts_output,
            "pts_downtime": pts_downtime,
            "pts_buffer": pts_buffer,
            "pts_defects": pts_defects,
            "output_per_hour": row["output_per_hour"],
            "buffer_qty": row["buffer_qty"]
        })

    ranking = pd.DataFrame(records)

    if ranking.empty:
        return {
            "ranking": ranking,
            "graph": graph,
            "top_cause": None,
            "warnings": warnings
        }

    ranking = ranking.sort_values(
        "risk_score",
        ascending=False
    ).reset_index(drop=True)

    ranking.insert(0, "rank", range(1, len(ranking) + 1))

    top_cause = (
        ranking.iloc[0]["machine"]
        if ranking.iloc[0]["risk_score"] >= FLAG_THRESHOLD
        else None
    )

    return {
        "ranking": ranking,
        "graph": graph,
        "top_cause": top_cause,
        "warnings": warnings
    }


# -------------------------------------------------
# DEFECT-TO-MACHINE LINKING
# -------------------------------------------------

def link_defects_to_machines(defects, ranking):

    defect_mapping = {
        "weld": [
            "Weld Robot 1",
            "Weld Robot 2",
            "Weld Robot 3"
        ],
        "paint": [
            "Paint Booth",
            "Curing Oven",
            "Paint Conveyor"
        ],
        "scratch": [
            "Paint Booth",
            "Curing Oven"
        ],
        "engine": [
            "Engine Line",
            "Engine Test"
        ],
        "gearbox": [
            "Gearbox Line"
        ],
        "wheel": [
            "Wheel Fit"
        ],
        "dent": [
            "Blank Press",
            "Draw Press"
        ]
    }

    risk = dict(
        zip(ranking["machine"], ranking["risk_score"])
    )

    results = []

    for _, defect in defects.iterrows():

        kind = str(defect.get("defect_type", "")).lower()

        candidates = next(
            (
                machines
                for keyword, machines in defect_mapping.items()
                if keyword in kind
            ),
            ALL_MACHINES
        )

        verified = str(
            defect.get("verified_machine", "")
        ).strip()

        valid_verified = verified in ALL_MACHINES

        if valid_verified:
            likely = verified
            probability = 1.0
            status = "CONFIRMED"

        else:
            likely = max(
                candidates,
                key=lambda machine: risk.get(machine, 0)
            )

            candidate_scores = [
                max(0, risk.get(machine, 0))
                for machine in candidates
            ]

            total = sum(candidate_scores)

            probability = (
                risk.get(likely, 0) / total
                if total > 0
                else 1 / len(candidates)
            )

            status = "INFERRED"

        results.append({
            "car_id": defect.get("car_id", "Unknown"),
            "defect_type": defect.get("defect_type", "Unknown"),
            "likely_machine": likely,
            "probability": round(probability, 2),
            "status": status,
            "candidates": ", ".join(candidates),
            "explanation": (
                "Verified by operator."
                if valid_verified
                else "Estimated from defect type and machine risk score."
            )
        })

    return pd.DataFrame(results)


def summarize_defect_links(links):

    if links.empty:
        return pd.DataFrame(
            columns=["machine", "linked_defects"]
        )

    return (
        links.groupby("likely_machine")
        .size()
        .reset_index(name="linked_defects")
        .rename(columns={"likely_machine": "machine"})
    )


# -------------------------------------------------
# DOWNSTREAM IMPACT ANALYSIS
# -------------------------------------------------

def get_downstream_impact(machine, graph):

    if machine not in graph:
        return {
            "machine": machine,
            "downstream": [],
            "parallel_unaffected": [],
            "disruption_path": [machine],
            "hops": {},
            "note": "Machine not found in factory graph."
        }

    downstream = list(nx.descendants(graph, machine))

    paths = [
        nx.shortest_path(graph, machine, node)
        for node in downstream
    ]

    disruption_path = (
        max(paths, key=len)
        if paths
        else [machine]
    )

    ancestors = set(nx.ancestors(graph, machine))

    parallel = []

    for node in graph.nodes:

        if node == machine or node in downstream or node in ancestors:
            continue

        # Identify other streams that eventually converge
        # with the selected machine's downstream route.
        if any(
            nx.has_path(graph, node, target)
            for target in downstream
        ):
            parallel.append(node)

    hops = {
        node: nx.shortest_path_length(graph, machine, node)
        for node in downstream
    }

    return {
        "machine": machine,
        "downstream": downstream,
        "parallel_unaffected": parallel,
        "disruption_path": disruption_path,
        "hops": hops,
        "note": (
            f"A disruption at {machine} may affect "
            f"{len(downstream)} downstream machines."
        )
    }
