import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

from recallsim.config import FULL, STARTER
from recallsim.db import create_db, insert_rows
from recallsim.inject import ISSUE_TYPES, TRUTH_COLUMNS, inject, per_type, write_ground_truth
from recallsim.pipeline import build_clean
from recallsim.recall import build_graph, trace_scope
from recallsim.schema import ID_PATTERNS, TABLES

PKS = {t.name: t.pk for t in TABLES}
ROOT = Path(__file__).resolve().parent.parent / "recallsim"


@pytest.fixture(scope="module")
def world():
    rows, key = build_clean(FULL)
    snapshot = json.dumps(rows, sort_keys=True)
    bad, truth = inject(rows, FULL)
    return rows, key, bad, truth, snapshot


def of(truth, code):
    return [t for t in truth if t["issue_type"] == ISSUE_TYPES[code]]


def keyed(rows, table):
    return {tuple(r[c] for c in PKS[table]): r for r in rows[table]}


def test_counts_and_ids(world):
    _, _, _, truth, _ = world
    n = per_type(FULL)
    assert n == 5 and len(truth) == 20
    for code in ISSUE_TYPES:
        assert len(of(truth, code)) == n
    ids = [t["anomaly_id"] for t in truth]
    assert ids == [f"ANOM-{i:04d}" for i in range(1, 21)]
    assert all(list(t) == TRUTH_COLUMNS for t in truth)


def test_clean_rows_not_mutated(world):
    rows, _, _, _, snapshot = world
    assert json.dumps(rows, sort_keys=True) == snapshot


def test_only_intended_rows_changed(world):
    """Diff clean vs corrupted: every difference is explained by exactly one ground-truth entry."""
    rows, _, bad, truth, _ = world
    diffs = set()
    for table in rows:
        a, b = keyed(rows, table), keyed(bad, table)
        for k in a.keys() | b.keys():
            if a.get(k) != b.get(k):
                diffs.add((table, k))
    expected = set()
    for t in truth:
        if t["table"] == "recall_action":
            for aid in json.loads(t["detail"])["removed_action_ids"]:
                expected.add(("recall_action", (aid,)))
        elif t["table"] == "wo_input_lot":
            wo, old = t["row_key"].split("|")
            expected.add(("wo_input_lot", (wo, old)))
            expected.add(("wo_input_lot", (wo, t["corrupted_value"])))
        else:
            expected.add((t["table"], (t["row_key"],)))
    assert diffs == expected


def test_a1_orphans(world):
    rows, key, bad, truth, _ = world
    existing = {l["raw_lot_id"] for l in rows["material_lot"]}
    a1 = of(truth, "A1")
    for t in a1:
        assert re.fullmatch(ID_PATTERNS["raw_lot_id"], t["corrupted_value"])
        assert t["corrupted_value"] not in existing
        assert t["original_value"] in existing
    assert sum(json.loads(t["detail"])["in_recall_scope"] for t in a1) == 2
    # schema with FK enforcement rejects the corrupted data, proving the defect is real
    conn = create_db()
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in PKS:
        insert_rows(conn, table, bad[table])
    assert len(conn.execute("PRAGMA foreign_key_check").fetchall()) == len(a1)


def test_a1_changes_recall_trace_only_for_inside_cases(world):
    rows, key, bad, truth, _ = world
    g_clean, g_bad = build_graph(rows), build_graph(bad)
    hit = {t["recall_id"] for t in of(truth, "A1") if t["recall_id"]}
    for k in key:
        kind = "RAW" if k["trigger_lot_type"] == "RAW" else "FINISHED"
        clean = trace_scope(g_clean, kind, k["trigger_lot_id"]).as_sorted()
        broken = trace_scope(g_bad, kind, k["trigger_lot_id"]).as_sorted()
        assert clean == k["expected_scope"]
        if k["recall_id"] in hit:
            assert broken != clean and len(broken["work_orders"]) < len(clean["work_orders"])
        else:
            assert broken == clean


def test_a2_over_delivery(world):
    rows, _, bad, truth, _ = world
    def shipped(r):
        s = defaultdict(int)
        for d in r["delivery"]:
            if d["status"] != "FAILED":
                s[d["finished_lot_id"]] += d["qty_delivered"]
        return s
    produced = {f["finished_lot_id"]: f["qty_produced"] for f in rows["finished_lot"]}
    clean, broken = shipped(rows), shipped(bad)
    over_clean = {l for l, q in clean.items() if q > produced[l]}
    over_bad = {l for l, q in broken.items() if q > produced[l]}
    assert over_clean == set()
    assert over_bad == {json.loads(t["detail"])["finished_lot_id"] for t in of(truth, "A2")}


def test_a3_missed_customer(world):
    rows, key, bad, truth, _ = world
    scope = {k["recall_id"]: k["expected_scope"] for k in key}
    def notified(r):
        return {(a["recall_id"], a["customer_id"]) for a in r["recall_action"]
                if a["action_type"] == "NOTIFY"}
    clean_n, bad_n = notified(rows), notified(bad)
    for t in of(truth, "A3"):
        d = json.loads(t["detail"])
        pair = (t["recall_id"], d["customer_id"])
        assert d["customer_id"] in scope[t["recall_id"]]["customers"]
        assert pair in clean_n and pair not in bad_n
    # trace unchanged: the miss is in the actions, not the genealogy
    def edges(r):
        return {(d["delivery_id"], d["finished_lot_id"], d["customer_id"]) for d in r["delivery"]}
    assert edges(bad) == edges(rows)


def test_a4_recalled_still_available(world):
    rows, _, bad, truth, _ = world
    quarantined = {a["target_id"] for a in rows["recall_action"]
                   if a["action_type"] == "QUARANTINE" and a["target_type"] == "FINISHED_LOT"}
    clean = {f["finished_lot_id"]: f["sale_status"] for f in rows["finished_lot"]}
    broken = {f["finished_lot_id"]: f["sale_status"] for f in bad["finished_lot"]}
    for t in of(truth, "A4"):
        lot = t["row_key"]
        assert lot in quarantined and clean[lot] == "RECALLED" and broken[lot] == "AVAILABLE"
    assert not any(clean[l] == "AVAILABLE" for l in quarantined)


def test_clean_sale_status_matches_scopes(world):
    rows, key, _, _, _ = world
    in_scope = set()
    for k in key:
        in_scope |= set(k["expected_scope"]["finished_lots"])
    recalled = {f["finished_lot_id"] for f in rows["finished_lot"] if f["sale_status"] == "RECALLED"}
    assert recalled == in_scope


def test_deterministic_starter():
    rows, _ = build_clean(STARTER)
    a, b = inject(rows, STARTER), inject(rows, STARTER)
    assert a == b
    assert len(a[1]) == 4 * per_type(STARTER)


def test_ground_truth_files_roundtrip(world, tmp_path):
    _, _, _, truth, _ = world
    write_ground_truth(truth, tmp_path / "gt")
    assert json.loads((tmp_path / "gt" / "ground_truth.json").read_text()) == truth
    with open(tmp_path / "gt" / "ground_truth.csv", encoding="utf-8") as fh:
        got = list(csv.DictReader(fh))
    assert [r["anomaly_id"] for r in got] == [t["anomaly_id"] for t in truth]


def test_nothing_reads_ground_truth_or_injector():
    """Isolation: only inject.py (and the CLI/exporter later) may mention the injector."""
    for path in ROOT.rglob("*.py"):
        if path.name in {"inject.py", "score.py", "__main__.py", "export.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "inject" not in text.lower(), path
        assert "ground_truth" not in text, path
