import re
from collections import Counter, defaultdict
from datetime import date

import pytest

from recallsim.config import AS_OF, FULL, SEED, STARTER
from recallsim.db import create_db, insert_rows
from recallsim.generate.master import generate_master
from recallsim.generate.production import generate_production
from recallsim.schema import ID_PATTERNS

TABLES = ("material_lot", "production_order", "wo_input_lot", "finished_lot")


@pytest.fixture(scope="module")
def master():
    return generate_master(FULL)


@pytest.fixture(scope="module")
def built(master):
    return generate_production(FULL, master)


@pytest.fixture(scope="module")
def rows(built):
    return built[0]


@pytest.fixture(scope="module")
def stats(built):
    return built[1]


def d(s):
    return date.fromisoformat(s)


def test_exact_counts_full(rows):
    assert len(rows["material_lot"]) == 10_000
    assert len(rows["production_order"]) == 5_000
    assert len(rows["finished_lot"]) == 8_000
    assert len(rows["wo_input_lot"]) > 8_000  # many-to-many: more bridge rows than lots


def test_exact_counts_starter():
    master = generate_master(STARTER)
    rows, _ = generate_production(STARTER, master)
    assert len(rows["material_lot"]) == STARTER.raw_lots
    assert len(rows["production_order"]) == STARTER.work_orders
    assert len(rows["finished_lot"]) == STARTER.finished_lots


def test_loads_into_sqlite_and_fk_clean(master, rows):
    conn = create_db()
    for t in ("supplier", "customer", "product", "bom_line"):
        insert_rows(conn, t, master[t])
    for t in TABLES:
        insert_rows(conn, t, rows[t])
    conn.commit()
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_ids_unique_and_match_pattern(rows):
    for table, pk in (("material_lot", "raw_lot_id"), ("production_order", "wo_id"),
                      ("finished_lot", "finished_lot_id")):
        ids = [r[pk] for r in rows[table]]
        assert len(ids) == len(set(ids))
        assert all(re.match(ID_PATTERNS[pk], i) for i in ids)
    pairs = [(r["wo_id"], r["raw_lot_id"]) for r in rows["wo_input_lot"]]
    assert len(pairs) == len(set(pairs))


def test_raw_lot_id_embeds_its_supplier(rows):
    for r in rows["material_lot"]:
        assert r["raw_lot_id"].startswith(f"RAWLOT-{r['supplier_id']}-2026-")


def test_ids_follow_chronological_order(rows):
    lots = rows["material_lot"]
    assert [l["received_date"] for l in lots] == sorted(l["received_date"] for l in lots)
    wos = rows["production_order"]
    assert [w["start_date"] for w in wos] == sorted(w["start_date"] for w in wos)


def test_consumption_never_exceeds_received(rows):
    used = defaultdict(float)
    for r in rows["wo_input_lot"]:
        used[r["raw_lot_id"]] += r["qty_consumed"]
    received = {l["raw_lot_id"]: l["qty_received"] for l in rows["material_lot"]}
    assert all(used[i] <= received[i] + 1e-9 for i in used)


def test_mass_balance_per_job_and_material(master, rows):
    bom = defaultdict(list)
    for l in master["bom_line"]:
        bom[l["product_id"]].append(l)
    wo = {w["wo_id"]: w for w in rows["production_order"]}
    lot_material = {l["raw_lot_id"]: l["material_code"] for l in rows["material_lot"]}
    produced = defaultdict(int)
    for f in rows["finished_lot"]:
        produced[f["wo_id"]] += f["qty_produced"]
    consumed = defaultdict(float)
    for r in rows["wo_input_lot"]:
        consumed[(r["wo_id"], lot_material[r["raw_lot_id"]])] += r["qty_consumed"]
    for (wo_id, material), kg in consumed.items():
        w = wo[wo_id]
        qty = [l["qty_per_pack"] for l in bom[w["product_id"]]
               if l["material_code"] == material and l["effective_from"] <= w["start_date"]
               and (l["effective_to"] is None or l["effective_to"] >= w["start_date"])]
        assert len(qty) == 1, (wo_id, material)
        ratio = kg / (produced[wo_id] * qty[0])
        assert 1.0 <= ratio <= 1.05, (wo_id, material, ratio)


def test_recipe_version_matches_job_start_date(master, rows):
    wo = {w["wo_id"]: w for w in rows["production_order"]}
    lot_material = {l["raw_lot_id"]: l["material_code"] for l in rows["material_lot"]}
    used = defaultdict(set)
    for r in rows["wo_input_lot"]:
        used[r["wo_id"]].add(lot_material[r["raw_lot_id"]])
    for wo_id, materials in used.items():
        w = wo[wo_id]
        expected = {l["material_code"] for l in master["bom_line"]
                    if l["product_id"] == w["product_id"] and l["effective_from"] <= w["start_date"]
                    and (l["effective_to"] is None or l["effective_to"] >= w["start_date"])}
        assert materials == expected, wo_id


def test_date_ordering(rows):
    lot = {l["raw_lot_id"]: l for l in rows["material_lot"]}
    wo = {w["wo_id"]: w for w in rows["production_order"]}
    for l in lot.values():
        assert l["expiry_date"] > l["received_date"]
    for r in rows["wo_input_lot"]:
        w, l = wo[r["wo_id"]], lot[r["raw_lot_id"]]
        assert l["received_date"] <= r["consumed_date"] <= l["expiry_date"]
        assert w["start_date"] <= r["consumed_date"] <= w["end_date"]
    for f in rows["finished_lot"]:
        w = wo[f["wo_id"]]
        assert w["start_date"] <= f["produced_date"] <= w["end_date"]
        assert f["expiry_date"] > f["produced_date"]


def test_status_rules(rows):
    wo = rows["production_order"]
    status = Counter(w["status"] for w in wo)
    assert 0.88 <= status["COMPLETED"] / len(wo) <= 0.92
    assert status["CANCELLED"] > 0 and status["IN_PROGRESS"] > 0 and status["PLANNED"] > 0
    by_id = {w["wo_id"]: w for w in wo}
    producing = {r["wo_id"] for r in rows["wo_input_lot"]} | {f["wo_id"] for f in rows["finished_lot"]}
    assert all(by_id[i]["status"] == "COMPLETED" for i in producing)
    for w in wo:
        if w["status"] == "COMPLETED":
            assert d(w["end_date"]) < AS_OF
        if w["status"] == "PLANNED":
            assert d(w["start_date"]) > AS_OF and w["end_date"] is None
        if w["status"] == "IN_PROGRESS":
            assert d(w["start_date"]) <= AS_OF and w["end_date"] is None


def test_every_completed_job_has_inputs_and_output(rows):
    completed = {w["wo_id"] for w in rows["production_order"] if w["status"] == "COMPLETED"}
    with_inputs = {r["wo_id"] for r in rows["wo_input_lot"]}
    with_output = {f["wo_id"] for f in rows["finished_lot"]}
    assert completed == with_inputs == with_output


def test_finished_lots_per_job_distribution(rows):
    per_job = Counter(f["wo_id"] for f in rows["finished_lot"])
    dist = Counter(per_job.values())
    assert set(dist) <= {1, 2, 3, 4}
    assert dist[1] > dist[3]  # one-lot jobs are more common than three-lot jobs


def test_finished_expiry_uses_product_shelf_life(master, rows):
    shelf = {p["product_id"]: p["shelf_life_days"] for p in master["product"]}
    prod = {w["wo_id"]: w["product_id"] for w in rows["production_order"]}
    for f in rows["finished_lot"][:2000]:
        gap = (d(f["expiry_date"]) - d(f["produced_date"])).days
        assert gap == shelf[prod[f["wo_id"]]]


def test_supplier_rules(master, rows):
    sup = {s["supplier_id"]: s for s in master["supplier"]}
    for l in rows["material_lot"]:
        s = sup[l["supplier_id"]]
        assert s["onboarded_date"] <= l["received_date"]
        if s["status"] == "INACTIVE":
            assert l["received_date"] <= "2026-06-30"


def test_unused_lot_share_and_no_shortage(stats):
    assert 0.15 <= stats["unused_lots"] / stats["lots"] <= 0.25
    assert stats["cancelled_for_shortage"] == 0
    assert stats["reduced_wos"] / FULL.work_orders <= 0.01


def test_materials_and_lot_sizes_are_varied(rows):
    qty = [l["qty_received"] for l in rows["material_lot"]]
    assert len({l["material_code"] for l in rows["material_lot"]}) >= 10
    assert max(qty) / min(qty) > 10
    assert min(qty) >= 1.0


def test_same_seed_identical_and_different_seed_differs():
    m = generate_master(STARTER)
    a, _ = generate_production(STARTER, m, SEED)
    b, _ = generate_production(STARTER, m, SEED)
    c, _ = generate_production(STARTER, m, SEED + 1)
    assert a == b
    assert a != c


def test_finished_lots_are_not_tiny_slivers(rows):
    totals = defaultdict(int)
    for f in rows["finished_lot"]:
        totals[f["wo_id"]] += f["qty_produced"]
    for f in rows["finished_lot"]:
        assert f["qty_produced"] >= max(1, totals[f["wo_id"]] // 10)
