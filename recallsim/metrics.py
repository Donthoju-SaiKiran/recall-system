"""Phase 6: recall metrics.

1. scope precision and recall: engine trace on the given data vs the expected scope
2. completion: cases closed, notified deliveries recovered, units recovered over units delivered
3. time to notify: hours from case opening to each NOTIFY, median and p90, overall and by channel
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, time

from .recall import build_graph, trace_scope

CASE_OPEN_HOUR = 9   # the simulator opens each case at 09:00 on its opened_date
SCOPE_FIELDS = ("finished_lots", "deliveries", "customers")


def _ratio(a, b):
    return round(a / b, 4) if b else 1.0


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * q) - 1)], 2)


def scope_metrics(rows: dict[str, list[dict]], answer_key: list[dict]) -> dict:
    graph = build_graph(rows)
    cases = {c["recall_id"]: c for c in rows["recall_case"]}
    per_case, tp, found, expected = [], defaultdict(int), defaultdict(int), defaultdict(int)
    for k in answer_key:
        c = cases[k["recall_id"]]
        kind = "RAW" if c["trigger_lot_type"] == "RAW" else "FINISHED"
        got = trace_scope(graph, kind, c["trigger_lot_id"]).as_sorted()
        entry = {"recall_id": k["recall_id"], "bucket": k["bucket"]}
        for f in SCOPE_FIELDS:
            want, have = set(k["expected_scope"][f]), set(got[f])
            hit = len(want & have)
            tp[f] += hit
            found[f] += len(have)
            expected[f] += len(want)
            entry[f"{f}_precision"] = _ratio(hit, len(have))
            entry[f"{f}_recall"] = _ratio(hit, len(want))
        per_case.append(entry)
    overall = {}
    for f in SCOPE_FIELDS:
        overall[f"{f}_precision"] = _ratio(tp[f], found[f])
        overall[f"{f}_recall"] = _ratio(tp[f], expected[f])
    return {"overall": overall, "per_case": per_case}


def completion_metrics(rows: dict[str, list[dict]]) -> dict:
    cases = rows["recall_case"]
    notified = {(a["recall_id"], a["target_id"]): a for a in rows["recall_action"] if a["action_type"] == "NOTIFY"}
    recovered = {(a["recall_id"], a["target_id"]): a for a in rows["recall_action"] if a["action_type"] == "RECOVER"}
    units_out = sum(a["qty_affected"] for a in notified.values())
    units_back = sum(a["qty_recovered"] or 0 for a in recovered.values())
    return {
        "cases": len(cases),
        "cases_closed_pct": _ratio(sum(c["status"] == "CLOSED" for c in cases), len(cases)),
        "notified_deliveries": len(notified),
        "deliveries_recovered_pct": _ratio(len(set(notified) & set(recovered)), len(notified)),
        "units_notified": units_out,
        "units_recovered": units_back,
        "units_recovered_pct": _ratio(units_back, units_out),
    }


def time_to_notify(rows: dict[str, list[dict]]) -> dict:
    opened = {c["recall_id"]: datetime.combine(datetime.fromisoformat(c["opened_date"]).date(), time(CASE_OPEN_HOUR))
              for c in rows["recall_case"]}
    channel = {c["customer_id"]: c["contact_channel"] for c in rows["customer"]}
    hours, by_channel = [], defaultdict(list)
    for a in rows["recall_action"]:
        if a["action_type"] != "NOTIFY":
            continue
        h = (datetime.fromisoformat(a["action_ts"]) - opened[a["recall_id"]]).total_seconds() / 3600
        hours.append(h)
        by_channel[channel.get(a["customer_id"], "UNKNOWN")].append(h)

    def stats(v):
        return {"count": len(v), "median_hours": _quantile(v, 0.5), "p90_hours": _quantile(v, 0.9)}

    return {"overall": stats(hours), "by_channel": {k: stats(v) for k, v in sorted(by_channel.items())}}


def all_metrics(rows: dict[str, list[dict]], answer_key: list[dict]) -> dict:
    return {"scope": scope_metrics(rows, answer_key), "completion": completion_metrics(rows),
            "time_to_notify": time_to_notify(rows)}
