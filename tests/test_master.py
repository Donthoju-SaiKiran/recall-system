import re
from collections import Counter, defaultdict

import pytest

from recallsim.config import FULL, SEED, STARTER, get_scale
from recallsim.db import create_db, insert_rows
from recallsim.generate.master import generate_master
from recallsim.ids import make_id
from recallsim.schema import ID_PATTERNS, TABLE_BY_NAME


@pytest.fixture(scope="module")
def full():
    return generate_master(FULL)


@pytest.fixture(scope="module")
def starter():
    return generate_master(STARTER)


def test_row_counts_full(full):
    assert len(full["supplier"]) == 500
    assert len(full["customer"]) == 1500
    assert len(full["product"]) == 40
    assert 3 * 40 <= len(full["bom_line"]) <= 2 * 6 * 40


def test_row_counts_starter(starter):
    assert len(starter["supplier"]) == 25
    assert len(starter["customer"]) == 75
    assert len(starter["product"]) == 10


def test_unknown_scale_rejected():
    with pytest.raises(ValueError):
        get_scale("huge")


def test_loads_into_sqlite_with_constraints(full):
    conn = create_db()
    for table in ("supplier", "customer", "product", "bom_line"):
        assert insert_rows(conn, table, full[table]) == len(full[table])
    conn.commit()
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_ids_match_pattern_and_unique(full):
    for table, rows in full.items():
        pk = TABLE_BY_NAME[table].pk[0]
        ids = [r[pk] for r in rows]
        assert len(ids) == len(set(ids)), table
        assert all(re.match(ID_PATTERNS[pk], i) for i in ids), table


def test_id_format_examples():
    assert make_id("supplier_id", 1) == "S0001"
    assert make_id("raw_lot_id", 7, supplier_id="S0042") == "RAWLOT-S0042-2026-000007"
    assert make_id("wo_id", 123) == "WO-2026-000123"


def test_bom_sum_never_exceeds_pack_size_per_version(full):
    packs = {p["product_id"]: p["pack_size_kg"] for p in full["product"]}
    totals = defaultdict(float)
    for line in full["bom_line"]:
        totals[(line["product_id"], line["effective_from"])] += line["qty_per_pack"]
    for (product_id, _from), total in totals.items():
        assert 0.80 * packs[product_id] <= total <= packs[product_id], (product_id, total)


def test_bom_versions_do_not_overlap(full):
    spans = defaultdict(set)
    for line in full["bom_line"]:
        spans[(line["product_id"], line["material_code"])].add(
            (line["effective_from"], line["effective_to"]))
    for key, versions in spans.items():
        ordered = sorted(versions)
        for (_f1, to1), (from2, _t2) in zip(ordered, ordered[1:]):
            assert to1 is not None and to1 < from2, key
        for f, t in versions:
            assert t is None or t >= f


def test_some_products_have_two_recipe_versions(full):
    versions = defaultdict(set)
    for line in full["bom_line"]:
        versions[line["product_id"]].add(line["effective_from"])
    changed = sum(1 for v in versions.values() if len(v) == 2)
    assert 1 <= changed <= 20  # target is 20 percent of 40


def test_every_product_has_core_materials(full):
    mats = defaultdict(set)
    for line in full["bom_line"]:
        mats[line["product_id"]].add(line["material_code"])
    cat = {p["product_id"]: p["category"] for p in full["product"]}
    for pid, m in mats.items():
        assert len(m) >= 3
        if cat[pid] == "CHOCOLATE":
            assert "COCOA" in m


def test_distribution_near_targets(full):
    tiers = Counter(s["tier"] for s in full["supplier"])
    assert 0.15 <= tiers["A"] / 500 <= 0.25
    assert 0.42 <= tiers["B"] / 500 <= 0.58
    types = Counter(c["customer_type"] for c in full["customer"])
    assert 0.55 <= types["RETAILER"] / 1500 <= 0.65
    status = Counter(s["status"] for s in full["supplier"])
    assert status["ACTIVE"] / 500 >= 0.85


def test_same_seed_gives_identical_data():
    assert generate_master(STARTER, SEED) == generate_master(STARTER, SEED)


def test_different_seed_gives_different_data():
    assert generate_master(STARTER, SEED) != generate_master(STARTER, SEED + 1)


def test_supplier_onboarded_before_2026(full):
    assert all(s["onboarded_date"] < "2026-01-01" for s in full["supplier"])
