"""Detection scoring. The only module that reads the validator output and the ground truth together."""
from __future__ import annotations

import json

EXPECTED_CHECK = {
    "ORPHAN_INPUT_LOT": ("FK", "wo_input_lot"),
    "DELIVERED_EXCEEDS_PRODUCED": ("ARITH_DELIVERED", "finished_lot"),
    "RECALL_MISSED_CUSTOMER": ("SCOPE_COVERAGE", "recall_action"),
    "RECALLED_STILL_AVAILABLE": ("SALE_STATUS", "finished_lot"),
}


def truth_key(t: dict) -> tuple[str, str, str]:
    """(check, table, row_key) the validator should report for this ground-truth row."""
    check, table = EXPECTED_CHECK[t["issue_type"]]
    d = json.loads(t["detail"])
    if t["issue_type"] == "ORPHAN_INPUT_LOT":
        return check, table, f"{d['wo_id']}|{t['corrupted_value']}"
    if t["issue_type"] == "DELIVERED_EXCEEDS_PRODUCED":
        return check, table, d["finished_lot_id"]
    if t["issue_type"] == "RECALL_MISSED_CUSTOMER":
        return check, table, f"{t['recall_id']}|{d['delivery_id']}"
    return check, table, t["row_key"]


def score_detection(issues: list[dict], truth: list[dict]) -> dict:
    reported = {(i["check"], i["table"], i["row_key"]) for i in issues}
    expected = {truth_key(t): t for t in truth}
    per_type = {}
    for t in truth:
        slot = per_type.setdefault(t["issue_type"], {"expected": 0, "detected": 0, "missed": []})
        slot["expected"] += 1
        if truth_key(t) in reported:
            slot["detected"] += 1
        else:
            slot["missed"].append(t["anomaly_id"])
    unexplained = sorted(reported - expected.keys())
    detected = sum(s["detected"] for s in per_type.values())
    return {"per_type": per_type, "detected": detected, "expected": len(truth),
            "unexplained_issues": [list(u) for u in unexplained]}
