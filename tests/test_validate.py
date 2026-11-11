import copy
import json

import pytest

from recallsim.config import FULL, STARTER
from recallsim.inject import ISSUE_TYPES, inject
from recallsim.metrics import all_metrics, completion_metrics, time_to_notify
from recallsim.pipeline import build_clean
from recallsim.score import score_detection
from recallsim.validate import CHECKS, summarize, validate, write_summary


@pytest.fixture(scope="module")
def world():
    rows, key = build_clean(FULL)
    bad, truth = inject(rows, FULL)
    return rows, key, bad, truth


@pytest.fixture(scope="module")
def tiny():
    rows, key = build_clean(STARTER)
    return rows, key


def checks_of(rows):
    return {i["check"] for i in validate(rows)}


# ---- clean data and detection scoring
def test_clean_data_has_zero_issues(world):
    rows, *_ = world
    assert validate(rows) == []


def test_every_planted_anomaly_detected_no_false_alarms(world):
    _, _, bad, truth = world
    res = score_detection(validate(bad), truth)
    assert res["detected"] == res["expected"] == 20
    assert res["unexplained_issues"] == []
    for t in ISSUE_TYPES.values():
        assert res["per_type"][t]["detected"] == res["per_type"][t]["expected"] == 5


def test_detection_also_at_starter_scale(tiny):
    rows, _ = tiny
    assert validate(rows) == []
    bad, truth = inject(rows, STARTER)
    res = score_detection(validate(bad), truth)
    assert res["detected"] == res["expected"] and res["unexplained_issues"] == []


def test_validator_is_deterministic(world):
    _, _, bad, _ = world
    assert validate(bad) == validate(bad)


# ---- one deliberately broken row per check, on a copy of clean data
def broken(tiny, edit):
    rows, _ = tiny
    r = copy.deepcopy(rows)
    edit(r)
    return r


def test_pk_duplicate(tiny):
    r = broken(tiny, lambda r: r["supplier"].append(dict(r["supplier"][0])))
    assert "PK_UNIQUE" in checks_of(r)


def test_required_empty(tiny):
    r = broken(tiny, lambda r: r["supplier"][0].update(supplier_name=None))
    assert "REQUIRED" in checks_of(r)


def test_type_wrong(tiny):
    r = broken(tiny, lambda r: r["delivery"][0].update(qty_delivered="5"))
    assert "TYPE" in checks_of(r)


def test_enum_bad(tiny):
    r = broken(tiny, lambda r: r["supplier"][0].update(tier="Z"))
    assert "ENUM" in checks_of(r)


def test_id_format_bad(tiny):
    r = broken(tiny, lambda r: r["shipment"][0].update(shipment_id="SHP-1"))
    assert "ID_FORMAT" in checks_of(r)


def test_range_below_minimum(tiny):
    r = broken(tiny, lambda r: r["delivery"][0].update(qty_delivered=0))
    assert "RANGE" in checks_of(r)


def test_date_invalid(tiny):
    r = broken(tiny, lambda r: r["material_lot"][0].update(received_date="2026-13-45"))
    assert "DATE_VALID" in checks_of(r)


def test_fk_missing(tiny):
    r = broken(tiny, lambda r: r["delivery"][0].update(customer_id="C99999"))
    assert "FK" in checks_of(r)


def test_poly_target_missing(tiny):
    r = broken(tiny, lambda r: r["recall_action"][0].update(target_id="DEL-2026-999999",
                                                               target_type="DELIVERY"))
    assert "POLY_TARGET" in checks_of(r)


def test_date_order(tiny):
    r = broken(tiny, lambda r: r["finished_lot"][0].update(expiry_date="2000-01-01"))
    assert "DATE_ORDER" in checks_of(r)


def test_arith_delivered(tiny):
    r = broken(tiny, lambda r: r["delivery"][0].update(qty_delivered=10**9))
    assert "ARITH_DELIVERED" in checks_of(r)


def test_arith_consumed(tiny):
    r = broken(tiny, lambda r: r["wo_input_lot"][0].update(qty_consumed=10**9))
    assert "ARITH_CONSUMED" in checks_of(r)


def test_arith_recovered(tiny):
    def edit(r):
        a = next(a for a in r["recall_action"] if a["action_type"] == "RECOVER")
        a["qty_recovered"] = a["qty_affected"] + 10
    assert "ARITH_RECOVERED" in checks_of(broken(tiny, edit))


def test_lifecycle_recover_without_notify(tiny):
    def edit(r):
        r["recall_action"] = [a for a in r["recall_action"] if a["action_type"] != "NOTIFY"]
    assert "LIFECYCLE_ORDER" in checks_of(broken(tiny, edit))


def test_case_status_mismatch(tiny):
    def edit(r):
        c = next(c for c in r["recall_case"] if c["status"] == "CLOSED")
        c["status"] = "IN_PROGRESS"
    assert "CASE_STATUS" in checks_of(broken(tiny, edit))


def test_sale_status(tiny):
    def edit(r):
        f = next(f for f in r["finished_lot"] if f["sale_status"] == "RECALLED")
        f["sale_status"] = "AVAILABLE"
    assert "SALE_STATUS" in checks_of(broken(tiny, edit))


def test_duplicate_natural_key(tiny):
    def edit(r):
        d = dict(r["delivery"][0])
        d["delivery_id"] = "DEL-2026-999999"
        r["delivery"].append(d)
    assert "DUPLICATE" in checks_of(broken(tiny, edit))


def test_scope_coverage(tiny):
    def edit(r):
        a = next(a for a in r["recall_action"] if a["action_type"] == "NOTIFY")
        r["recall_action"] = [x for x in r["recall_action"] if x["target_id"] != a["target_id"]
                              or x["recall_id"] != a["recall_id"]]
    assert "SCOPE_COVERAGE" in checks_of(broken(tiny, edit))


def test_every_check_has_a_test():
    here = open(__file__, encoding="utf-8").read()
    assert len(CHECKS) == 18
    for name in CHECKS:
        assert f'"{name}" in checks_of' in here or f'"{name}"' in here.replace("'", '"'), name


# ---- summary files
def test_summary_files(world, tmp_path):
    _, _, bad, _ = world
    issues = validate(bad)
    s = write_summary(issues, bad, tmp_path / "v")
    assert s["result"] == "FAIL" and s["total_issues"] == 20
    assert json.loads((tmp_path / "v" / "validation_summary.json").read_text())["total_issues"] == 20
    md = (tmp_path / "v" / "validation_summary.md").read_text()
    assert all(c in md for c in CHECKS)
    assert summarize([], bad)["result"] == "PASS"


# ---- metrics
def test_scope_metrics_perfect_on_clean_degraded_on_damaged(world):
    rows, key, bad, _ = world
    clean = all_metrics(rows, key)["scope"]["overall"]
    assert all(v == 1.0 for v in clean.values())
    damaged = all_metrics(bad, key)["scope"]["overall"]
    assert damaged["finished_lots_precision"] == 1.0
    assert damaged["finished_lots_recall"] < 1.0 and damaged["customers_recall"] < 1.0


def test_completion_metrics(world):
    rows, *_ = world
    m = completion_metrics(rows)
    assert m["cases"] == 15
    closed = sum(c["status"] == "CLOSED" for c in rows["recall_case"])
    assert m["cases_closed_pct"] == round(closed / 15, 4)
    assert 0 < m["units_recovered_pct"] < m["deliveries_recovered_pct"] <= 1


def test_time_to_notify(world):
    rows, *_ = world
    m = time_to_notify(rows)
    assert m["overall"]["count"] == 123
    assert 0 <= m["overall"]["median_hours"] <= m["overall"]["p90_hours"]
    assert set(m["by_channel"]) == {"EMAIL", "PHONE", "PORTAL"}
    assert m["by_channel"]["PHONE"]["median_hours"] > m["by_channel"]["EMAIL"]["median_hours"]


def test_validator_and_metrics_never_mention_the_answer_sheet():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "recallsim"
    for name in ("validate.py", "metrics.py"):
        text = (root / name).read_text(encoding="utf-8").lower()
        assert "ground_truth" not in text and "inject" not in text and "truth" not in text
