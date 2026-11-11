import re
from collections import Counter, defaultdict
from datetime import date

import pytest

from recallsim.config import AS_OF, FULL, SEED, STARTER
from recallsim.db import create_db, insert_rows
from recallsim.generate.distribution import REGION_WAREHOUSES, generate_distribution
from recallsim.generate.master import generate_master
from recallsim.generate.production import generate_production
from recallsim.schema import ID_PATTERNS


@pytest.fixture(scope="module")
def world():
    master = generate_master(FULL)
    production, _ = generate_production(FULL, master)
    dist, stats = generate_distribution(FULL, master, production)
    return master, production, dist, stats


def d(s):
    return date.fromisoformat(s)


def test_exact_counts(world):
    _, _, dist, _ = world
    assert len(dist["shipment"]) == 12_000
    assert len(dist["delivery"]) == 20_000


def test_exact_counts_starter():
    m = generate_master(STARTER)
    p, _ = generate_production(STARTER, m)
    dist, _ = generate_distribution(STARTER, m, p)
    assert len(dist["shipment"]) == STARTER.shipments
    assert len(dist["delivery"]) == STARTER.deliveries


def test_all_tables_load_and_fk_clean(world):
    master, production, dist, _ = world
    conn = create_db()
    for src in (master, production, dist):
        for table, rows in src.items():
            insert_rows(conn, table, rows)
    conn.commit()
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_ids_unique_pattern_and_chronological(world):
    _, _, dist, _ = world
    for table, pk in (("shipment", "shipment_id"), ("delivery", "delivery_id")):
        ids = [r[pk] for r in dist[table]]
        assert len(ids) == len(set(ids))
        assert all(re.match(ID_PATTERNS[pk], i) for i in ids)
    dates = [s["ship_date"] for s in dist["shipment"]]
    assert dates == sorted(dates)


def test_every_shipment_has_1_to_6_deliveries(world):
    _, _, dist, _ = world
    per = Counter(x["shipment_id"] for x in dist["delivery"])
    assert set(per) == {s["shipment_id"] for s in dist["shipment"]}
    assert 1 <= min(per.values()) and max(per.values()) <= 6


def test_delivered_never_exceeds_produced_per_lot(world):
    _, production, dist, _ = world
    sent = defaultdict(int)
    kept = defaultdict(int)
    for x in dist["delivery"]:
        sent[x["finished_lot_id"]] += x["qty_delivered"]
        if x["status"] != "FAILED":
            kept[x["finished_lot_id"]] += x["qty_delivered"]
    produced = {l["finished_lot_id"]: l["qty_produced"] for l in production["finished_lot"]}
    assert all(sent[i] <= produced[i] for i in sent)
    assert all(kept[i] <= sent[i] for i in kept)
    assert all(x["qty_delivered"] >= 1 for x in dist["delivery"])


def test_date_ordering_chain(world):
    _, production, dist, _ = world
    produced = {l["finished_lot_id"]: l["produced_date"] for l in production["finished_lot"]}
    ship = {s["shipment_id"]: s["ship_date"] for s in dist["shipment"]}
    for x in dist["delivery"]:
        assert produced[x["finished_lot_id"]] <= ship[x["shipment_id"]] <= x["delivery_date"]
        assert d(ship[x["shipment_id"]]) <= AS_OF
        assert 1 <= (d(x["delivery_date"]) - d(ship[x["shipment_id"]])).days <= 4


def test_one_warehouse_per_shipment_matching_customer_region(world):
    master, _, dist, _ = world
    region = {c["customer_id"]: c["region"] for c in master["customer"]}
    wh = {s["shipment_id"]: s["warehouse_code"] for s in dist["shipment"]}
    for x in dist["delivery"]:
        assert wh[x["shipment_id"]] in REGION_WAREHOUSES[region[x["customer_id"]]]


def test_status_rules(world):
    _, _, dist, _ = world
    by_ship = defaultdict(list)
    for x in dist["delivery"]:
        by_ship[x["shipment_id"]].append(x["status"])
    for s in dist["shipment"]:
        sts = by_ship[s["shipment_id"]]
        if all(v == "FAILED" for v in sts):
            expected = "CANCELLED"
        elif "IN_TRANSIT" in sts:
            expected = "IN_TRANSIT"
        else:
            expected = "DELIVERED"
        assert s["status"] == expected
    for x in dist["delivery"]:
        assert (x["status"] == "IN_TRANSIT") == (d(x["delivery_date"]) > AS_OF)


def test_no_duplicate_lot_customer_pairs(world):
    _, _, dist, _ = world
    pairs = [(x["finished_lot_id"], x["customer_id"]) for x in dist["delivery"]]
    assert len(pairs) == len(set(pairs))


def test_inactive_customers_only_early(world):
    master, _, dist, _ = world
    inactive = {c["customer_id"] for c in master["customer"] if c["status"] == "INACTIVE"}
    ship = {s["shipment_id"]: s["ship_date"] for s in dist["shipment"]}
    assert inactive
    for x in dist["delivery"]:
        if x["customer_id"] in inactive:
            assert x["delivery_date"] <= "2026-07-05"  # ready cutoff 06-30 plus lag and transit
            assert ship[x["shipment_id"]] <= "2026-07-05"


def test_distribution_shapes(world):
    master, production, dist, stats = world
    failed = sum(1 for x in dist["delivery"] if x["status"] == "FAILED")
    assert 0.01 <= failed / 20_000 <= 0.035
    per_customer = Counter(x["customer_id"] for x in dist["delivery"])
    assert len(per_customer) >= 0.85 * len(master["customer"])
    top = sum(v for _, v in per_customer.most_common(len(master["customer"]) // 10))
    assert top / 20_000 >= 0.25  # skewed, not uniform
    per_lot = Counter(x["finished_lot_id"] for x in dist["delivery"])
    assert max(per_lot.values()) > 5 and min(per_lot.values()) >= 1
    sent = defaultdict(int)
    for x in dist["delivery"]:
        if x["status"] != "FAILED":
            sent[x["finished_lot_id"]] += x["qty_delivered"]
    total_prod = sum(l["qty_produced"] for l in production["finished_lot"])
    on_hand_share = 1 - sum(sent.values()) / total_prod
    assert 0.03 <= on_hand_share <= 0.40  # some stock stays on hand, most has shipped


def test_same_seed_identical_and_different_seed_differs():
    m = generate_master(STARTER)
    p, _ = generate_production(STARTER, m)
    a, _ = generate_distribution(STARTER, m, p, SEED)
    b, _ = generate_distribution(STARTER, m, p, SEED)
    c, _ = generate_distribution(STARTER, m, p, SEED + 1)
    assert a == b
    assert a != c
