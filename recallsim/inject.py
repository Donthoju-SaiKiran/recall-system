"""Phase 5: deliberate anomaly injection plus the separate ground truth.

inject() takes clean rows, returns corrupted copies and a ground_truth list. Nothing in the
generator, engine or validator imports this module. The clean rows are never modified.

Four documented rules (not random flips):
  A1 ORPHAN_INPUT_LOT           wo_input_lot.raw_lot_id points at a lot that does not exist
  A2 DELIVERED_EXCEEDS_PRODUCED one delivery qty raised so a lot ships more than it produced
  A3 RECALL_MISSED_CUSTOMER     NOTIFY and RECOVER removed for a delivery inside a recall scope
  A4 RECALLED_STILL_AVAILABLE   a quarantined finished lot is set back to sale_status AVAILABLE
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from .config import SEED, Scale
from .recall import build_graph, trace_scope
from .rng import stage_rng
from .schema import ID_PATTERNS

ISSUE_TYPES = {
    "A1": "ORPHAN_INPUT_LOT",
    "A2": "DELIVERED_EXCEEDS_PRODUCED",
    "A3": "RECALL_MISSED_CUSTOMER",
    "A4": "RECALLED_STILL_AVAILABLE",
}
RULES = {
    "A1": "wo_input_lot.raw_lot_id replaced by a well-formed id that is absent from material_lot; "
          "up to 2 rows chosen from raw-trigger recall scopes (the trigger edge), rest outside all scopes",
    "A2": "largest non-failed delivery of a lot outside all recall scopes raised so shipped > produced",
    "A3": "NOTIFY and RECOVER actions removed for a delivery whose customer has no other delivery in "
          "that recall scope, so the customer is never notified",
    "A4": "finished lot with a QUARANTINE action set to sale_status AVAILABLE",
}
PER_TYPE_FULL = 5
TRUTH_COLUMNS = ["anomaly_id", "issue_type", "table", "row_key", "field", "original_value",
                 "corrupted_value", "recall_id", "rule", "detail"]


def per_type(scale: Scale) -> int:
    return max(2, round(PER_TYPE_FULL * scale.raw_lots / 10_000))


def _round_robin(rng, by_case: dict[str, list[str]], n: int) -> list[tuple[str, str]]:
    """Pick n (case, item) pairs spread across cases, no repeats."""
    pools = {k: list(v) for k, v in by_case.items() if v}
    order = rng.sample(sorted(pools), len(pools))
    picks = []
    while len(picks) < n and any(pools.values()):
        for rid in order:
            if len(picks) == n:
                break
            if pools[rid]:
                item = pools[rid].pop(rng.randrange(len(pools[rid])))
                picks.append((rid, item))
    if len(picks) < n:
        raise ValueError(f"only {len(picks)} candidates, need {n}")
    return picks


def inject(rows: dict[str, list[dict]], scale: Scale, seed: int = SEED):
    rng = stage_rng(seed, "inject")
    n = per_type(scale)
    bad = {t: [dict(r) for r in v] for t, v in rows.items()}

    g = build_graph(rows)
    cases = {c["recall_id"]: c for c in rows["recall_case"]}
    scopes = {}
    for rid, c in cases.items():
        kind = "RAW" if c["trigger_lot_type"] == "RAW" else "FINISHED"
        scopes[rid] = trace_scope(g, kind, c["trigger_lot_id"])
    all_wo = set().union(*(s.work_orders for s in scopes.values()))
    all_fin = set().union(*(s.finished_lots for s in scopes.values()))
    all_raw = set().union(*(s.raw_lots for s in scopes.values()))

    truth: list[dict] = []

    def add(code, table, row_key, field, original, corrupted, recall_id=None, **detail):
        truth.append({"issue_type": ISSUE_TYPES[code], "table": table, "row_key": row_key,
                      "field": field, "original_value": original, "corrupted_value": corrupted,
                      "recall_id": recall_id, "rule": RULES[code],
                      "detail": json.dumps(detail, sort_keys=True)})

    # ---- A1 orphan input lot
    existing_raw = {l["raw_lot_id"] for l in rows["material_lot"]}
    by_raw = defaultdict(list)
    for i, r in enumerate(bad["wo_input_lot"]):
        by_raw[r["raw_lot_id"]].append(i)
    inside = []
    raw_cases = sorted(rid for rid, c in cases.items()
                       if c["trigger_lot_type"] == "RAW" and scopes[rid].work_orders)
    for rid in rng.sample(raw_cases, min(2, n, len(raw_cases))):
        trig = cases[rid]["trigger_lot_id"]
        idx = rng.choice(sorted(i for i in by_raw[trig]
                                if bad["wo_input_lot"][i]["wo_id"] in scopes[rid].work_orders))
        inside.append((idx, rid))
    chosen = {i for i, _ in inside}
    outside_pool = [i for i, r in enumerate(bad["wo_input_lot"])
                    if r["wo_id"] not in all_wo and r["raw_lot_id"] not in all_raw
                    and i not in chosen]
    plan = inside + [(i, None) for i in rng.sample(outside_pool, n - len(inside))]
    for k, (i, rid) in enumerate(plan, start=1):
        r = bad["wo_input_lot"][i]
        old = r["raw_lot_id"]
        new = old.rsplit("-", 1)[0] + f"-{900000 + k:06d}"
        assert re.fullmatch(ID_PATTERNS["raw_lot_id"], new) and new not in existing_raw
        r["raw_lot_id"] = new
        add("A1", "wo_input_lot", f"{r['wo_id']}|{old}", "raw_lot_id", old, new, rid,
            wo_id=r["wo_id"], in_recall_scope=rid is not None)

    # ---- A2 delivered exceeds produced
    produced = {f["finished_lot_id"]: f["qty_produced"] for f in rows["finished_lot"]}
    shipped = defaultdict(int)
    live = defaultdict(list)
    for i, d in enumerate(bad["delivery"]):
        if d["status"] != "FAILED":
            shipped[d["finished_lot_id"]] += d["qty_delivered"]
            live[d["finished_lot_id"]].append(i)
    lots = sorted(l for l in live if l not in all_fin)
    for lot in rng.sample(lots, n):
        i = max(live[lot], key=lambda j: (bad["delivery"][j]["qty_delivered"], j))
        d = bad["delivery"][i]
        extra = rng.randint(max(1, produced[lot] // 20), max(2, produced[lot] // 5))
        new = d["qty_delivered"] + (produced[lot] - shipped[lot]) + extra
        old = d["qty_delivered"]
        d["qty_delivered"] = new
        add("A2", "delivery", d["delivery_id"], "qty_delivered", old, new,
            finished_lot_id=lot, qty_produced=produced[lot], total_delivered_after=produced[lot] + extra)

    # ---- A3 recall missed customer
    notified = {(a["recall_id"], a["target_id"]) for a in rows["recall_action"]
                if a["action_type"] == "NOTIFY"}
    by_case = {}
    for rid, s in scopes.items():
        per_cust = defaultdict(list)
        for did in s.deliveries:
            per_cust[g.delivery[did]["customer_id"]].append(did)
        by_case[rid] = sorted(ds[0] for ds in per_cust.values()
                              if len(ds) == 1 and (rid, ds[0]) in notified)
    dropped_ids: set[str] = set()
    for rid, did in _round_robin(rng, by_case, n):
        gone = sorted(a["action_id"] for a in rows["recall_action"]
                      if a["recall_id"] == rid and a["target_id"] == did
                      and a["action_type"] in ("NOTIFY", "RECOVER"))
        dropped_ids.update(gone)
        add("A3", "recall_action", ",".join(gone), "(rows deleted)", "present", "deleted", rid,
            delivery_id=did, customer_id=g.delivery[did]["customer_id"], removed_action_ids=gone)
    bad["recall_action"] = [a for a in bad["recall_action"] if a["action_id"] not in dropped_ids]

    # ---- A4 recalled lot still available
    quarantined = defaultdict(list)
    for a in rows["recall_action"]:
        if a["action_type"] == "QUARANTINE" and a["target_type"] == "FINISHED_LOT":
            quarantined[a["recall_id"]].append(a["target_id"])
    pos = {f["finished_lot_id"]: i for i, f in enumerate(bad["finished_lot"])}
    for rid, lot in _round_robin(rng, {k: sorted(v) for k, v in quarantined.items()}, n):
        f = bad["finished_lot"][pos[lot]]
        old = f["sale_status"]
        f["sale_status"] = "AVAILABLE"
        add("A4", "finished_lot", lot, "sale_status", old, "AVAILABLE", rid)

    for k, t in enumerate(truth, start=1):
        t["anomaly_id"] = f"ANOM-{k:04d}"
    truth = [{c: t[c] for c in TRUTH_COLUMNS} for t in truth]
    return bad, truth


def write_ground_truth(truth: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "ground_truth.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=TRUTH_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(truth)
    (out_dir / "ground_truth.json").write_text(
        json.dumps(truth, indent=2, sort_keys=True) + "\n", encoding="utf-8")
