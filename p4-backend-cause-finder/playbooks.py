from typing import Dict, Any, Optional


PLAYBOOK_LIBRARY: Dict[str, Dict[str, Any]] = {
    "welding_fault": {
        "playbook_id": "PB-WELD-05",
        "title": "Left Framing Robot (M05) Servo & Tip Recovery",
        "target_machine": "M05 • Left Side Framing Robot",
        "urgency": "IMMEDIATE",
        "estimated_recovery_mins": 4.5,
        "expected_oee_gain": "+24.5%",
        "steps": [
            "Reroute incoming chassis load (30% split) to parallel cell M06 (Right Side Framing Robot).",
            "Throttle Stage 1 Stamping press feed rate by 15% until BUF-1 drops below 60%.",
            "Trigger automated weld-tip dressing cycle and reset M05 servo current threshold.",
            "Run 2 test-weld verification cycles before restoring 100% line speed.",
        ],
    },
    "bad_sensor": {
        "playbook_id": "PB-SENS-10",
        "title": "Clear Coat Robot (M10) Telemetry Sensor Failover",
        "target_machine": "M10 • Base & Clear Coat Robot",
        "urgency": "HIGH",
        "estimated_recovery_mins": 1.5,
        "expected_oee_gain": "Prevents False Line Stop",
        "steps": [
            "Keep physical conveyor running—cycle time is healthy (55s); do not halt Paint Shop.",
            "Switch M10 thermal & vibration stream to redundant PLC backup channel B.",
            "Suppress false CRITICAL alerts triggered by out-of-range (-99.9°C / 412°C) probe spikes.",
            "Dispatch instrumentation tech during next scheduled shift to replace Type-K probe.",
        ],
    },
}


def get_prescriptive_playbook(fault_mode: str) -> Optional[Dict[str, Any]]:
    """
    Returns the matching step-by-step resolution playbook for an active fault,
    or None when the assembly line is healthy.
    """
    return PLAYBOOK_LIBRARY.get(fault_mode)