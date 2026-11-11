import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime

import pytest

from recallsim.config import AS_OF, FULL, SEED, STARTER
from recallsim.db import create_db, insert_rows
from recallsim.generate.distribution import generate_distribution
from recallsim.generate.master import generate_master
from recallsim.generate.production import generate_production
from recallsim.recall import (DATA_TABLES, build_graph, generate_recalls, sql_trace,
                              trace_scope)
from recallsim.schema import ID_PATTERNS


def _build(scale):
    master = generate_master(scale)
    production, _ = generate_production(scale, master)
    dist, _ = generate_distribution(scale, master, production)
    return {**master, **production, **dist}


@pytest.fixture(scope="module")
def world():
    rows = _build(FULL)
    out, key, stats = generate_recalls(FULL, rows)
    return rows, out, key, stats


def D(s):
    return date.fromisoformat(s)


def TS(s):
    return datetime.fromisoformat(s)


def test_case_counts_and_mix(world):
    _, out, key, _ = world
    assert len(out["recall_case"]) == 15
    buckets = Counter(k["bucket"] for k in key)
    assert buckets["unused"] == 1
    types = Counter(c["trigger_lot_type"] for c in out["recall_case"])
    assert types["RAW"] == 10      # 9 contaminated + 1 unused
    assert types["FINISHED"] == 5
    assert {"small", "medium", "large"} <= set(buckets)


def test_unused_lot_case_has_empty_downstream(world):
    _, out, key, _ = world
    k = next(k for k in key if k["bucket"] == "unused")
    s = k["expected_scope"]
    assert s["raw_lots"] == [k["trigger_lot_id"]]
    assert not (s["work_orders"] or s["finished_lots"] or s["deliveries"] or s["customers"])
    rid = k["recall_id"]
    acts = [a for a in out["recall_action"] if a["recall_id"] == rid]
    assert not any(a["action_type"] == "NOTIFY" for a in acts)


def test_bfs_equals_sql_cte_for_every_case(world):
    rows, _, key, _ = world
    g = build_graph(rows)
    conn = create_db()
    for t in DATA_TABLES:
        insert_rows(conn, t, rows[t])
    for k in key:
        t = "RAW" if k["trigger_lot_type"] == "RAW" else "FINISHED"
        bfs = trace_scope(g, t, k["trigger_lot_id"]).as_sorted()
        sql = sql_trace(conn, t, k["trigger_lot_id"]).as_sorted()
        assert bfs == sql == k["expected_scope"]


def test_scope_matches_independent_manual_join(world):
    """No graph code: plain joins straight on the rows for the first raw case."""
    rows, _, key, _ = world
    k = next(k for k in key if k["trigger_lot_type"] == "RAW" and k["bucket"] == "large")
    wos = {r["wo_id"] for r in rows["wo_input_lot"] if r["raw_lot_id"] == k["trigger_lot_id"]}
    fins = {f["finished_lot_id"] for f in rows["finished_lot"] if f["wo_id"] in wos}
    dels = {d["delivery_id"] for d in rows["delivery"]
            if d["finished_lot_id"] in fins and d["status"] != "FAILED"}
    assert sorted(wos) == k["expected_scope"]["work_orders"]
    assert sorted(fins) == k["expected_scope"]["finished_lots"]
    assert sorted(dels) == k["expected_scope"]["deliveries"]


def test_scopes_are_disjoint(world):
    _, _, key, _ = world
    seen = set()
    for k in key:
        fl = set(k["expected_scope"]["finished_lots"])
        assert not (fl & seen)
        seen |= fl


def test_one_notify_per_affected_delivery(world):
    _, out, key, _ = world
    by_case = defaultdict(list)
    for a in out["recall_action"]:
        if a["action_type"] == "NOTIFY":
            by_case[a["recall_id"]].append(a["target_id"])
    for k in key:
        got = by_case.get(k["recall_id"], [])
        assert sorted(got) == k["expected_scope"]["deliveries"]


def test_failed_deliveries_never_notified(world):
    rows, out, _, _ = world
    failed = {d["delivery_id"] for d in rows["delivery"] if d["status"] == "FAILED"}
    notified = {a["target_id"] for a in out["recall_action"] if a["action_type"] == "NOTIFY"}
    assert not (failed & notified)


def test_quarantine_qty_equals_on_hand(world):
    rows, out, _, _ = world
    consumed = defaultdict(float)
    for r in rows["wo_input_lot"]:
        consumed[r["raw_lot_id"]] += r["qty_consumed"]
    raw = {l["raw_lot_id"]: l for l in rows["material_lot"]}
    delivered = defaultdict(int)
    for d in rows["delivery"]:
        if d["status"] != "FAILED":
            delivered[d["finished_lot_id"]] += d["qty_delivered"]
    fin = {f["finished_lot_id"]: f for f in rows["finished_lot"]}
    n = 0
    for a in out["recall_action"]:
        if a["action_type"] != "QUARANTINE":
            continue
        n += 1
        if a["target_type"] == "RAW_LOT":
            exp = round(raw[a["target_id"]]["qty_received"] - consumed[a["target_id"]], 3)
            assert a["qty_affected"] == pytest.approx(exp)
        else:
            f = fin[a["target_id"]]
            assert a["qty_affected"] == f["qty_produced"] - delivered[a["target_id"]]
        assert a["qty_affected"] > 0
    assert n > 0


def test_action_ordering_and_window(world):
    _, out, _, _ = world
    cases = {c["recall_id"]: c for c in out["recall_case"]}
    first = {}
    for a in out["recall_action"]:
        c = cases[a["recall_id"]]
        ts = TS(a["action_ts"])
        assert ts.date() >= D(c["opened_date"])
        assert ts.date() <= AS_OF
        first.setdefault((a["recall_id"], a["action_type"], a["target_id"]), ts)
    for (rid, kind, tid), ts in first.items():
        if kind == "RECOVER":
            assert ts >= first[(rid, "NOTIFY", tid)]
        if kind == "DISPOSE":
            assert ts >= first[(rid, "QUARANTINE", tid)]


def test_recovered_never_exceeds_delivered(world):
    _, out, _, _ = world
    n = 0
    for a in out["recall_action"]:
        if a["action_type"] == "RECOVER":
            n += 1
            assert 0 <= a["qty_recovered"] <= a["qty_affected"]
        else:
            assert a["qty_recovered"] is None
    assert n > 0


def test_case_status_matches_derivation(world):
    _, out, _, _ = world
    acts = defaultdict(list)
    for a in out["recall_action"]:
        acts[a["recall_id"]].append(a)
    for c in out["recall_case"]:
        a = acts[c["recall_id"]]
        notified = {x["target_id"] for x in a if x["action_type"] == "NOTIFY"}
        recovered = {x["target_id"] for x in a if x["action_type"] == "RECOVER"}
        quarantined = {x["target_id"] for x in a if x["action_type"] == "QUARANTINE"}
        disposed = {x["target_id"] for x in a if x["action_type"] == "DISPOSE"}
        done = notified <= recovered and quarantined <= disposed
        assert (c["status"] == "CLOSED") == done
        if done:
            assert c["closed_date"] == max(TS(x["action_ts"]) for x in a).date().isoformat()
        else:
            assert c["closed_date"] is None


def test_ids_and_foreign_keys(world):
    rows, out, _, _ = world
    import re
    for c in out["recall_case"]:
        assert re.fullmatch(ID_PATTERNS["recall_id"], c["recall_id"])
        assert D(c["opened_date"]) <= AS_OF
    for a in out["recall_action"]:
        assert re.fullmatch(ID_PATTERNS["action_id"], a["action_id"])
    ids = [a["action_id"] for a in out["recall_action"]]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    # the real schema enforces FKs and checks
    conn = create_db()
    for t in DATA_TABLES:
        insert_rows(conn, t, rows[t])
    insert_rows(conn, "recall_case", out["recall_case"])
    insert_rows(conn, "recall_action", out["recall_action"])
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    # polymorphic target must exist in its own table
    pools = {"RAW_LOT": {l["raw_lot_id"] for l in rows["material_lot"]},
             "FINISHED_LOT": {f["finished_lot_id"] for f in rows["finished_lot"]},
             "DELIVERY": {d["delivery_id"] for d in rows["delivery"]}}
    for a in out["recall_action"]:
        assert a["target_id"] in pools[a["target_type"]]


def test_deterministic():
    rows = _build(STARTER)
    a = generate_recalls(STARTER, rows)
    b = generate_recalls(STARTER, rows)
    assert a[0] == b[0] and a[1] == b[1]


def test_engine_does_not_mutate_input():
    rows = _build(STARTER)
    before = {t: [dict(r) for r in rows[t]] for t in DATA_TABLES}
    generate_recalls(STARTER, rows)
    assert {t: rows[t] for t in DATA_TABLES} == before
