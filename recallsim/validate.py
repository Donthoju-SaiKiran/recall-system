"""Phase 6: data validator.

Reads rows only. Returns a list of issues, each {check, table, row_key, message}.
Works on any copy of the data, clean or damaged, and never reads the answer sheet.
Foreign keys are checked in Python, so it works even when the database cannot enforce them.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from .config import AS_OF
from .recall import build_graph, trace_scope
from .schema import ID_PATTERNS, TABLES

CHECKS = (
    "PK_UNIQUE", "REQUIRED", "TYPE", "ENUM", "ID_FORMAT", "RANGE", "DATE_VALID", "FK",
    "POLY_TARGET", "DATE_ORDER", "ARITH_DELIVERED", "ARITH_CONSUMED", "ARITH_RECOVERED",
    "LIFECYCLE_ORDER", "CASE_STATUS", "SALE_STATUS", "DUPLICATE", "SCOPE_COVERAGE",
)
TOLERANCE = 1e-6


def _key(table, row):
    return "|".join(str(row.get(c)) for c in table.pk)


def _day(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _stamp(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def validate(rows: dict[str, list[dict]], as_of: date = AS_OF) -> list[dict]:
    issues: list[dict] = []

    def bad(check, table, row_key, message):
        issues.append({"check": check, "table": table, "row_key": row_key, "message": message})

    # ---------- generic checks driven by schema.py
    pools = {}
    for t in TABLES:
        for c in t.cols:
            if c.fk is None:
                continue
        pools[t.name] = {c.name: {r.get(c.name) for r in rows.get(t.name, [])} for c in t.cols}
    for t in TABLES:
        seen = set()
        for r in rows.get(t.name, []):
            rk = _key(t, r)
            if rk in seen:
                bad("PK_UNIQUE", t.name, rk, "duplicate primary key")
            seen.add(rk)
            for c in t.cols:
                v = r.get(c.name)
                if v is None or v == "":
                    if c.required:
                        bad("REQUIRED", t.name, rk, f"{c.name} is empty")
                    continue
                if c.type == "INTEGER" and (isinstance(v, bool) or not isinstance(v, int)):
                    bad("TYPE", t.name, rk, f"{c.name} not an integer: {v!r}")
                elif c.type == "REAL" and (isinstance(v, bool) or not isinstance(v, (int, float))):
                    bad("TYPE", t.name, rk, f"{c.name} not a number: {v!r}")
                elif c.type == "TEXT" and not isinstance(v, str):
                    bad("TYPE", t.name, rk, f"{c.name} not text: {v!r}")
                if c.allowed is not None and v not in c.allowed:
                    bad("ENUM", t.name, rk, f"{c.name}={v!r} not in allowed list")
                if c.name in ID_PATTERNS and c.type == "TEXT" and isinstance(v, str) \
                        and not re.fullmatch(ID_PATTERNS[c.name], v):
                    bad("ID_FORMAT", t.name, rk, f"{c.name}={v!r} breaks the ID format")
                if c.minimum is not None and isinstance(v, (int, float)) and v < c.minimum:
                    bad("RANGE", t.name, rk, f"{c.name}={v} below minimum {c.minimum}")
                if c.type == "DATE" and _day(v) is None:
                    bad("DATE_VALID", t.name, rk, f"{c.name}={v!r} is not a valid date")
                if c.type == "TIMESTAMP" and _stamp(v) is None:
                    bad("DATE_VALID", t.name, rk, f"{c.name}={v!r} is not a valid timestamp")
                if c.fk is not None and v not in pools[c.fk[0]][c.fk[1]]:
                    bad("FK", t.name, rk, f"{c.name}={v!r} not found in {c.fk[0]}.{c.fk[1]}")

    # ---------- polymorphic references
    lots = {"RAW": pools["material_lot"]["raw_lot_id"], "FINISHED": pools["finished_lot"]["finished_lot_id"]}
    for r in rows["recall_case"]:
        if r["trigger_lot_id"] not in lots.get(r["trigger_lot_type"], set()):
            bad("POLY_TARGET", "recall_case", r["recall_id"],
                f"trigger {r['trigger_lot_id']!r} not found as {r['trigger_lot_type']} lot")
    targets = {"RAW_LOT": lots["RAW"], "FINISHED_LOT": lots["FINISHED"],
               "DELIVERY": pools["delivery"]["delivery_id"]}
    for r in rows["recall_action"]:
        if r["target_id"] not in targets.get(r["target_type"], set()):
            bad("POLY_TARGET", "recall_action", r["action_id"],
                f"target {r['target_id']!r} not found as {r['target_type']}")

    # ---------- date ordering
    wo = {r["wo_id"]: r for r in rows["production_order"]}
    raw = {r["raw_lot_id"]: r for r in rows["material_lot"]}
    fin = {r["finished_lot_id"]: r for r in rows["finished_lot"]}
    ship = {r["shipment_id"]: r for r in rows["shipment"]}
    case = {r["recall_id"]: r for r in rows["recall_case"]}

    def order(table, rk, earlier, later, label):
        a, b = _day(earlier), _day(later)
        if a and b and a > b:
            bad("DATE_ORDER", table, rk, label)

    for r in rows["production_order"]:
        if r["end_date"]:
            order("production_order", r["wo_id"], r["start_date"], r["end_date"], "end_date before start_date")
    for r in rows["material_lot"]:
        order("material_lot", r["raw_lot_id"], r["received_date"], r["expiry_date"], "expiry before received")
    for r in rows["finished_lot"]:
        k, job = r["finished_lot_id"], wo.get(r["wo_id"])
        order("finished_lot", k, r["produced_date"], r["expiry_date"], "expiry before produced")
        if job:
            order("finished_lot", k, job["start_date"], r["produced_date"], "produced before job start")
            if job["end_date"]:
                order("finished_lot", k, r["produced_date"], job["end_date"], "produced after job end")
    for r in rows["wo_input_lot"]:
        k, lot, job = f"{r['wo_id']}|{r['raw_lot_id']}", raw.get(r["raw_lot_id"]), wo.get(r["wo_id"])
        if lot:
            order("wo_input_lot", k, lot["received_date"], r["consumed_date"], "consumed before lot received")
        if job:
            order("wo_input_lot", k, job["start_date"], r["consumed_date"], "consumed before job start")
            if job["end_date"]:
                order("wo_input_lot", k, r["consumed_date"], job["end_date"], "consumed after job end")
    for r in rows["delivery"]:
        k = r["delivery_id"]
        if r["shipment_id"] in ship:
            order("delivery", k, ship[r["shipment_id"]]["ship_date"], r["delivery_date"], "delivered before ship date")
        if r["finished_lot_id"] in fin:
            order("delivery", k, fin[r["finished_lot_id"]]["produced_date"], r["delivery_date"],
                  "delivered before produced")
        if r["status"] != "IN_TRANSIT":   # an in-transit date is the expected arrival
            order("delivery", k, r["delivery_date"], as_of.isoformat(), "delivery date after as-of date")
    for r in rows["recall_case"]:
        k = r["recall_id"]
        order("recall_case", k, r["opened_date"], as_of.isoformat(), "opened after as-of date")
        if r["closed_date"]:
            order("recall_case", k, r["opened_date"], r["closed_date"], "closed before opened")
        lot = (raw if r["trigger_lot_type"] == "RAW" else fin).get(r["trigger_lot_id"])
        if lot:
            order("recall_case", k, lot.get("received_date") or lot.get("produced_date"),
                  r["opened_date"], "opened before trigger lot existed")
    for r in rows["recall_action"]:
        c, ts = case.get(r["recall_id"]), _stamp(r["action_ts"])
        if c and ts:
            order("recall_action", r["action_id"], c["opened_date"], ts.date().isoformat(), "action before case opened")
        if ts and ts.date() > as_of:
            bad("DATE_ORDER", "recall_action", r["action_id"], "action after as-of date")

    # ---------- arithmetic reconciliation
    shipped = defaultdict(int)
    for r in rows["delivery"]:
        shipped[r["finished_lot_id"]] += r["qty_delivered"] if isinstance(r["qty_delivered"], int) else 0
    for lot, qty in sorted(shipped.items()):
        if lot in fin and qty > fin[lot]["qty_produced"]:
            bad("ARITH_DELIVERED", "finished_lot", lot,
                f"delivered {qty} exceeds produced {fin[lot]['qty_produced']}")
    used = defaultdict(float)
    for r in rows["wo_input_lot"]:
        used[r["raw_lot_id"]] += r["qty_consumed"]
    for lot, qty in sorted(used.items()):
        if lot in raw and qty > raw[lot]["qty_received"] + TOLERANCE:
            bad("ARITH_CONSUMED", "material_lot", lot, f"consumed {qty:.3f} exceeds received")
    for r in rows["recall_action"]:
        k, rec = r["action_id"], r["qty_recovered"]
        if r["action_type"] == "RECOVER":
            if rec is None:
                bad("ARITH_RECOVERED", "recall_action", k, "RECOVER without qty_recovered")
            elif rec > r["qty_affected"] + TOLERANCE:
                bad("ARITH_RECOVERED", "recall_action", k, "recovered more than affected")
        elif rec is not None:
            bad("ARITH_RECOVERED", "recall_action", k, "qty_recovered set on a non-RECOVER action")

    # ---------- lifecycle
    first = {}
    by_case = defaultdict(list)
    for r in rows["recall_action"]:
        by_case[r["recall_id"]].append(r)
        first.setdefault((r["recall_id"], r["action_type"], r["target_id"]), r)
    follows = {"RECOVER": "NOTIFY", "DISPOSE": "QUARANTINE"}
    for (rid, kind, tid), r in sorted(first.items()):
        if kind in follows:
            prev = first.get((rid, follows[kind], tid))
            if prev is None:
                bad("LIFECYCLE_ORDER", "recall_action", r["action_id"], f"{kind} without {follows[kind]}")
            elif _stamp(r["action_ts"]) and _stamp(prev["action_ts"]) \
                    and _stamp(r["action_ts"]) < _stamp(prev["action_ts"]):
                bad("LIFECYCLE_ORDER", "recall_action", r["action_id"], f"{kind} before {follows[kind]}")
    for rid, c in sorted(case.items()):
        acts = by_case.get(rid, [])
        need_r = {a["target_id"] for a in acts if a["action_type"] == "NOTIFY"}
        got_r = {a["target_id"] for a in acts if a["action_type"] == "RECOVER"}
        need_d = {a["target_id"] for a in acts if a["action_type"] == "QUARANTINE"}
        got_d = {a["target_id"] for a in acts if a["action_type"] == "DISPOSE"}
        done = need_r <= got_r and need_d <= got_d
        if (c["status"] == "CLOSED") != done:
            bad("CASE_STATUS", "recall_case", rid, f"status {c['status']} does not match its actions")
        if (c["status"] == "CLOSED") != bool(c["closed_date"]):
            bad("CASE_STATUS", "recall_case", rid, "closed_date inconsistent with status")

    # ---------- traceability: scope, coverage, sale status
    graph = build_graph(rows)
    scopes = {}
    for rid, c in case.items():
        if c["trigger_lot_id"] in lots.get(c["trigger_lot_type"], set()):
            scopes[rid] = trace_scope(graph, c["trigger_lot_type"], c["trigger_lot_id"])
    quarantined = {a["target_id"] for a in rows["recall_action"]
                   if a["action_type"] == "QUARANTINE" and a["target_type"] == "FINISHED_LOT"}
    in_scope = set().union(*(s.finished_lots for s in scopes.values())) if scopes else set()
    for lot_id in sorted((quarantined | in_scope) & fin.keys()):
        if fin[lot_id].get("sale_status") == "AVAILABLE":
            bad("SALE_STATUS", "finished_lot", lot_id, "lot is under recall but still AVAILABLE for sale")
    notified = {(a["recall_id"], a["customer_id"]) for a in rows["recall_action"]
                if a["action_type"] == "NOTIFY"}
    for rid, s in sorted(scopes.items()):
        per_cust = defaultdict(list)
        for did in s.deliveries:
            per_cust[graph.delivery[did]["customer_id"]].append(did)
        for cust, dels in sorted(per_cust.items()):
            if (rid, cust) not in notified:
                for did in sorted(dels):
                    bad("SCOPE_COVERAGE", "recall_action", f"{rid}|{did}",
                        f"customer {cust} received delivery {did} in scope but was never notified")

    # ---------- duplicates on natural keys
    seen_nat = defaultdict(int)
    for r in rows["delivery"]:
        seen_nat[("delivery", r["shipment_id"], r["finished_lot_id"], r["customer_id"])] += 1
    for r in rows["recall_action"]:
        seen_nat[("recall_action", r["recall_id"], r["action_type"], r["target_type"], r["target_id"])] += 1
    for nat, n in sorted(seen_nat.items()):
        if n > 1:
            bad("DUPLICATE", nat[0], "|".join(nat[1:]), f"{n} rows share the same natural key")

    issues.sort(key=lambda i: (CHECKS.index(i["check"]), i["table"], i["row_key"], i["message"]))
    return issues


def summarize(issues: list[dict], rows: dict[str, list[dict]]) -> dict:
    counts = {c: 0 for c in CHECKS}
    for i in issues:
        counts[i["check"]] += 1
    return {"as_of": AS_OF.isoformat(),
            "row_counts": {t.name: len(rows.get(t.name, [])) for t in TABLES},
            "checks": {c: {"issues": n, "status": "PASS" if n == 0 else "FAIL"} for c, n in counts.items()},
            "total_issues": len(issues), "result": "PASS" if not issues else "FAIL"}


def write_summary(issues: list[dict], rows: dict[str, list[dict]], out_dir: Path, max_listed: int = 50) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(issues, rows)
    summary["sample_issues"] = issues[:max_listed]
    (out_dir / "validation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    lines = ["# Validation summary", "", f"Result: **{summary['result']}**, total issues: {summary['total_issues']}",
             "", "| Check | Status | Issues |", "|---|---|---|"]
    lines += [f"| {c} | {v['status']} | {v['issues']} |" for c, v in summary["checks"].items()]
    lines += ["", "## Row counts", "", "| Table | Rows |", "|---|---|"]
    lines += [f"| {t} | {n} |" for t, n in summary["row_counts"].items()]
    (out_dir / "validation_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary
