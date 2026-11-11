"""Phase 4: recall engine.

- trace_scope: downstream genealogy traversal (BFS) over in-memory rows
- sql_trace: the same traversal as a SQL recursive CTE, used as an independent check
- generate_recalls: pick contaminated lots, then simulate notify / quarantine / recover / dispose

The trace functions only read the data tables. The answer key is computed on clean data and is
never read by the engine.
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .config import AS_OF, SEED, Scale
from .db import create_db, insert_rows
from .ids import IdCounter
from .rng import stage_rng

DATA_TABLES = ("supplier", "customer", "product", "bom_line", "material_lot", "production_order",
               "wo_input_lot", "finished_lot", "shipment", "delivery")

REASON_WEIGHTS = {"PATHOGEN": 35, "ALLERGEN_UNDECLARED": 25, "FOREIGN_MATTER": 25, "CHEMICAL": 15}
SEVERITY_WEIGHTS = {
    "PATHOGEN": {"CLASS_I": 80, "CLASS_II": 20},
    "ALLERGEN_UNDECLARED": {"CLASS_I": 70, "CLASS_II": 30},
    "FOREIGN_MATTER": {"CLASS_II": 60, "CLASS_III": 40},
    "CHEMICAL": {"CLASS_I": 30, "CLASS_II": 50, "CLASS_III": 20},
}
CHANNEL_NOTIFY_DAYS = {"EMAIL": (0, 1), "PORTAL": (0, 2), "PHONE": (1, 4)}
CHANNEL_RESPONSE_MEDIAN_DAYS = {"EMAIL": 5, "PORTAL": 7, "PHONE": 10}
NON_RESPONDER_SHARE = 0.03
SELL_THROUGH_DAYS = 45
MAX_SELL_THROUGH = 0.9
OPEN_AFTER_LAST_DELIVERY_DAYS = (1, 9)
LATEST_OPEN = AS_OF - timedelta(days=7)
UNUSED_LOT_LATEST_RECEIVED = date(2026, 8, 20)
BASE_CASES = 15  # at full scale, two thirds raw-lot triggers


# ------------------------------------------------------------------ scope
@dataclass
class Scope:
    raw_lots: set = field(default_factory=set)
    work_orders: set = field(default_factory=set)
    finished_lots: set = field(default_factory=set)
    deliveries: set = field(default_factory=set)
    customers: set = field(default_factory=set)
    shipments: set = field(default_factory=set)

    def as_sorted(self) -> dict[str, list[str]]:
        return {k: sorted(v) for k, v in self.__dict__.items()}


@dataclass
class Graph:
    raw_to_wo: dict = field(default_factory=lambda: defaultdict(set))
    wo_to_fin: dict = field(default_factory=lambda: defaultdict(list))
    fin_to_del: dict = field(default_factory=lambda: defaultdict(list))
    delivery: dict = field(default_factory=dict)


def build_graph(rows: dict[str, list[dict]]) -> Graph:
    g = Graph()
    for r in rows["wo_input_lot"]:
        g.raw_to_wo[r["raw_lot_id"]].add(r["wo_id"])
    for f in rows["finished_lot"]:
        g.wo_to_fin[f["wo_id"]].append(f["finished_lot_id"])
    for d in rows["delivery"]:
        g.delivery[d["delivery_id"]] = d
        if d["status"] != "FAILED":          # failed deliveries never reached the customer
            g.fin_to_del[d["finished_lot_id"]].append(d["delivery_id"])
    return g


def trace_scope(g: Graph, trigger_type: str, trigger_id: str) -> Scope:
    """Breadth first walk downstream from a trigger lot. trigger_type is RAW or FINISHED."""
    s = Scope()
    queue = deque([(trigger_type, trigger_id)])
    seen = set(queue)
    while queue:
        kind, ident = queue.popleft()
        children = []
        if kind == "RAW":
            s.raw_lots.add(ident)
            children = [("WO", w) for w in g.raw_to_wo.get(ident, ())]
        elif kind == "WO":
            s.work_orders.add(ident)
            children = [("FINISHED", f) for f in g.wo_to_fin.get(ident, ())]
        elif kind == "FINISHED":
            s.finished_lots.add(ident)
            children = [("DELIVERY", d) for d in g.fin_to_del.get(ident, ())]
        elif kind == "DELIVERY":
            s.deliveries.add(ident)
            d = g.delivery[ident]
            s.customers.add(d["customer_id"])
            s.shipments.add(d["shipment_id"])
        for child in children:
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return s


EDGE_VIEW = """
CREATE TEMP VIEW IF NOT EXISTS genealogy_edge AS
SELECT 'RAW' AS pt, raw_lot_id AS pid, 'WO' AS ct, wo_id AS cid FROM wo_input_lot
UNION ALL SELECT 'WO', wo_id, 'FINISHED', finished_lot_id FROM finished_lot
UNION ALL SELECT 'FINISHED', finished_lot_id, 'DELIVERY', delivery_id FROM delivery WHERE status != 'FAILED'
UNION ALL SELECT 'DELIVERY', delivery_id, 'CUSTOMER', customer_id FROM delivery WHERE status != 'FAILED'
UNION ALL SELECT 'DELIVERY', delivery_id, 'SHIPMENT', shipment_id FROM delivery WHERE status != 'FAILED'
"""

WALK = """
WITH RECURSIVE walk(t, i) AS (
  SELECT ?, ?
  UNION
  SELECT e.ct, e.cid FROM genealogy_edge e JOIN walk w ON e.pt = w.t AND e.pid = w.i
) SELECT t, i FROM walk
"""


def sql_trace(conn: sqlite3.Connection, trigger_type: str, trigger_id: str) -> Scope:
    """Same traversal as trace_scope, done by the database. Independent cross-check."""
    conn.execute(EDGE_VIEW)
    key = {"RAW": "raw_lots", "WO": "work_orders", "FINISHED": "finished_lots",
           "DELIVERY": "deliveries", "CUSTOMER": "customers", "SHIPMENT": "shipments"}
    s = Scope()
    for kind, ident in conn.execute(WALK, (trigger_type, trigger_id)):
        getattr(s, key[kind]).add(ident)
    return s


# ------------------------------------------------------------------ planning
def _quantile_bucket(entries: list[dict]) -> None:
    entries.sort(key=lambda e: (e["n_customers"], e["trigger_id"]))
    n = len(entries)
    for i, e in enumerate(entries):
        e["bucket"] = "small" if i < n / 3 else "medium" if i < 2 * n / 3 else "large"


def _candidates(g: Graph, rows, trigger_type: str, ids: list[str]) -> list[dict]:
    latest_delivery = (AS_OF - timedelta(days=17)).isoformat()
    out = []
    for ident in ids:
        scope = trace_scope(g, trigger_type, ident)
        if not scope.deliveries:
            continue
        last = max(g.delivery[d]["delivery_date"] for d in scope.deliveries)
        if last > latest_delivery:
            continue
        out.append({"trigger_type": trigger_type, "trigger_id": ident, "scope": scope,
                    "n_customers": len(scope.customers), "last_delivery": last})
    _quantile_bucket(out)
    return out


def _pick(rng, pool: list[dict], kind: str, used: set) -> dict:
    order = [kind] + [b for b in ("medium", "large", "small") if b != kind]
    for bucket in order:
        options = [e for e in pool if e["bucket"] == bucket and not (e["scope"].finished_lots & used)]
        if options:
            choice = rng.choice(options)
            used |= choice["scope"].finished_lots
            pool.remove(choice)
            return choice
    raise ValueError("no disjoint recall candidate left")


def plan_cases(rng, scale: Scale, g: Graph, rows) -> list[dict]:
    n_cases = max(3, round(BASE_CASES * scale.raw_lots / 10_000))
    n_raw = round(n_cases * 2 / 3)
    n_fin = n_cases - n_raw
    consumed_lots = set(g.raw_to_wo)
    raw_pool = _candidates(g, rows, "RAW", sorted(consumed_lots))
    fin_pool = _candidates(g, rows, "FINISHED", [f["finished_lot_id"] for f in rows["finished_lot"]])
    used: set = set()
    cases = []
    for kind in [("large", "medium", "small")[i % 3] for i in range(n_raw - 1)]:
        cases.append(_pick(rng, raw_pool, kind, used))
    for kind in [("medium", "small", "large", "medium", "small")[i % 5] for i in range(n_fin)]:
        cases.append(_pick(rng, fin_pool, kind, used))
    # boundary case: a raw lot that was received but never used
    unused = sorted(l["raw_lot_id"] for l in rows["material_lot"]
                    if l["raw_lot_id"] not in consumed_lots
                    and l["received_date"] <= UNUSED_LOT_LATEST_RECEIVED.isoformat())
    lot = rng.choice(unused)
    cases.append({"trigger_type": "RAW", "trigger_id": lot, "scope": Scope(raw_lots={lot}),
                  "n_customers": 0, "last_delivery": None, "bucket": "unused"})
    return cases


# ------------------------------------------------------------------ simulation
def _ts(base: datetime, **delta) -> datetime:
    return base + timedelta(**delta)


def _weighted(rng, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def simulate(rng, scale: Scale, rows, g: Graph, cases: list[dict]):
    cust = {c["customer_id"]: c for c in rows["customer"]}
    raw_lot = {l["raw_lot_id"]: l for l in rows["material_lot"]}
    fin_lot = {f["finished_lot_id"]: f for f in rows["finished_lot"]}
    consumed = defaultdict(float)
    for r in rows["wo_input_lot"]:
        consumed[r["raw_lot_id"]] += r["qty_consumed"]
    delivered = defaultdict(int)
    for d in rows["delivery"]:
        if d["status"] != "FAILED":
            delivered[d["finished_lot_id"]] += d["qty_delivered"]
    end = datetime.combine(AS_OF, time(23, 59, 59))

    case_rows, actions = [], []
    for case in cases:
        scope = case["scope"]
        if case["last_delivery"]:
            opened = date.fromisoformat(case["last_delivery"]) + timedelta(
                days=rng.randint(*OPEN_AFTER_LAST_DELIVERY_DAYS))
        else:
            opened = date.fromisoformat(raw_lot[case["trigger_id"]]["received_date"]) + timedelta(
                days=rng.randint(15, 60))
        assert opened <= LATEST_OPEN, (case["trigger_id"], opened)
        reason = _weighted(rng, REASON_WEIGHTS)
        base = datetime.combine(opened, time(9, 0))
        mine = []

        def add(kind, target_type, target_id, qty, disposition, ts, customer=None, recovered=None):
            if ts <= end:
                mine.append({"_case": case, "action_type": kind, "target_type": target_type,
                             "target_id": target_id, "customer_id": customer, "qty_affected": qty,
                             "qty_recovered": recovered, "disposition": disposition, "ts": ts})
                return True
            return False

        stock = []  # (target_type, target_id, qty, quarantine_ts)
        if case["trigger_type"] == "RAW":
            remaining = round(raw_lot[case["trigger_id"]]["qty_received"] - consumed[case["trigger_id"]], 3)
            if remaining > 0:
                stock.append(("RAW_LOT", case["trigger_id"], remaining, _ts(base, hours=rng.randint(1, 30))))
        for fid in sorted(scope.finished_lots):
            on_hand = fin_lot[fid]["qty_produced"] - delivered[fid]
            if on_hand > 0:
                stock.append(("FINISHED_LOT", fid, on_hand, _ts(base, hours=rng.randint(1, 30))))
        for target_type, target_id, qty, q_ts in stock:
            add("QUARANTINE", target_type, target_id, qty, "QUARANTINED", q_ts)
            if target_type == "RAW_LOT":
                disposition = "RETURNED" if rng.random() < 0.6 else "DESTROYED"
            else:
                disposition = "DESTROYED"
            add("DISPOSE", target_type, target_id, qty, disposition, _ts(q_ts, days=rng.randint(3, 12)))
        for did in sorted(scope.deliveries):
            d = g.delivery[did]
            c = cust[d["customer_id"]]
            n_ts = _ts(base, days=rng.randint(*CHANNEL_NOTIFY_DAYS[c["contact_channel"]]),
                       hours=rng.randint(0, 8))
            add("NOTIFY", "DELIVERY", did, d["qty_delivered"], "PENDING", n_ts, d["customer_id"])
            if rng.random() < NON_RESPONDER_SHARE:
                continue
            median = CHANNEL_RESPONSE_MEDIAN_DAYS[c["contact_channel"]]
            wait = max(0.25, rng.lognormvariate(math.log(median), 0.7))
            r_ts = _ts(n_ts, hours=wait * 24)
            age = (n_ts.date() - date.fromisoformat(d["delivery_date"])).days
            unsold = 1 - min(MAX_SELL_THROUGH, age / SELL_THROUGH_DAYS)
            recovered = int(d["qty_delivered"] * unsold * rng.uniform(0.6, 1.0))
            add("RECOVER", "DELIVERY", did, d["qty_delivered"],
                "RETURNED" if recovered > 0 else "DESTROYED", r_ts, d["customer_id"], recovered)

        need_recover = {a["target_id"] for a in mine if a["action_type"] == "NOTIFY"}
        done_recover = {a["target_id"] for a in mine if a["action_type"] == "RECOVER"}
        need_dispose = {(a["target_type"], a["target_id"]) for a in mine if a["action_type"] == "QUARANTINE"}
        done_dispose = {(a["target_type"], a["target_id"]) for a in mine if a["action_type"] == "DISPOSE"}
        complete = need_recover <= done_recover and need_dispose <= done_dispose
        status = "CLOSED" if complete else "IN_PROGRESS"
        closed = max(a["ts"] for a in mine).date() if complete and mine else None
        case_rows.append({"_case": case, "trigger_lot_type": case["trigger_type"],
                          "trigger_lot_id": case["trigger_id"], "reason_code": reason,
                          "severity": _weighted(rng, SEVERITY_WEIGHTS[reason]),
                          "opened_date": opened, "closed_date": closed, "status": status})
        actions.extend(mine)
    return case_rows, actions


def generate_recalls(scale: Scale, rows: dict[str, list[dict]], seed: int = SEED):
    """rows holds the ten data tables. Returns (recall rows, answer key, stats)."""
    g = build_graph(rows)
    cases = plan_cases(stage_rng(seed, "recall.select"), scale, g, rows)
    case_rows, actions = simulate(stage_rng(seed, "recall.actions"), scale, rows, g, cases)

    case_rows.sort(key=lambda c: (c["opened_date"], c["trigger_lot_id"]))
    rec_ids = IdCounter("recall_id")
    for c in case_rows:
        c["recall_id"] = rec_ids.next()
    by_case = {id(c["_case"]): c["recall_id"] for c in case_rows}
    actions.sort(key=lambda a: (a["ts"], by_case[id(a["_case"])], a["action_type"], a["target_id"]))
    act_ids = IdCounter("action_id")

    conn = create_db()
    for t in DATA_TABLES:
        insert_rows(conn, t, rows[t])
    answer_key = []
    for c in case_rows:
        case = c["_case"]
        truth = sql_trace(conn, case["trigger_type"], case["trigger_id"])
        if truth.as_sorted() != case["scope"].as_sorted():
            raise AssertionError(f"BFS and SQL trace disagree for {case['trigger_id']}")
        answer_key.append({"recall_id": c["recall_id"], "trigger_lot_type": case["trigger_type"],
                           "trigger_lot_id": case["trigger_id"], "bucket": case["bucket"],
                           "expected_scope": truth.as_sorted()})
    conn.close()

    out = {
        "recall_case": [{
            "recall_id": c["recall_id"], "trigger_lot_type": c["trigger_lot_type"],
            "trigger_lot_id": c["trigger_lot_id"], "reason_code": c["reason_code"],
            "severity": c["severity"], "opened_date": c["opened_date"].isoformat(),
            "closed_date": c["closed_date"].isoformat() if c["closed_date"] else None,
            "status": c["status"],
        } for c in case_rows],
        "recall_action": [{
            "action_id": act_ids.next(), "recall_id": by_case[id(a["_case"])],
            "action_type": a["action_type"], "target_type": a["target_type"],
            "target_id": a["target_id"], "customer_id": a["customer_id"],
            "qty_affected": a["qty_affected"], "qty_recovered": a["qty_recovered"],
            "disposition": a["disposition"], "action_ts": a["ts"].isoformat(timespec="seconds"),
        } for a in actions],
    }
    stats = {"cases": len(case_rows), "actions": len(actions),
             "closed": sum(1 for c in case_rows if c["status"] == "CLOSED")}
    return out, answer_key, stats
