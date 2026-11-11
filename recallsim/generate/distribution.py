"""Phase 3: shipments and deliveries.

Bottom-up: build deliveries from a dispatch ledger per finished lot, then group them into
shipments by contiguous chunking so the shipment count is exact and no shipment can leave
before its last parcel exists (ship_date = max ready date of its deliveries).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from itertools import accumulate

from ..config import AS_OF, SEED, Scale
from ..ids import IdCounter
from ..rng import stage_rng
from ..util import allocate

REGION_WAREHOUSES = {
    "NORTH": ("WH-DEL", "WH-AMD"),
    "SOUTH": ("WH-HYD", "WH-BLR", "WH-CHN"),
    "EAST": ("WH-KOL", "WH-CHN"),
    "WEST": ("WH-MUM", "WH-PUN", "WH-AMD"),
    "CENTRAL": ("WH-DEL", "WH-HYD", "WH-PUN"),
}
CARRIERS = tuple(f"CAR-{i:02d}" for i in range(1, 13))
TYPE_POPULARITY = {"DISTRIBUTOR": 5.0, "FOODSERVICE": 1.5, "RETAILER": 1.0}
TYPE_SIZE = {"DISTRIBUTOR": 4.0, "FOODSERVICE": 1.5, "RETAILER": 1.0}
MIN_DISPATCH_AGE_DAYS = 3
READY_LAG_DAYS = (0, 14)
TRANSIT_DAYS = (1, 4)
INACTIVE_CUSTOMER_CUTOFF = date(2026, 6, 30)
MAX_PER_SHIPMENT = 6
FAILED_SHARE = 0.02
FANOUT_EXPONENT = 0.7


def _dispatch_qty(rng, lot: dict) -> int:
    """Packs that have left the plant. Old lots are mostly gone, fresh lots mostly still on hand."""
    age = (AS_OF - date.fromisoformat(lot["produced_date"])).days
    if age < MIN_DISPATCH_AGE_DAYS:
        return 0
    fraction = min(1.0, 0.25 + age / 120) * rng.uniform(0.85, 1.0)
    return int(fraction * lot["qty_produced"])


def _chunk_sizes(rng, n: int, k: int) -> list[int]:
    """Split n deliveries into k shipments of 1..MAX_PER_SHIPMENT."""
    if not k <= n <= k * MAX_PER_SHIPMENT:
        raise ValueError(f"cannot split {n} deliveries into {k} shipments")
    sizes = [1] * k
    for _ in range(n - k):
        while True:
            i = rng.randrange(k)
            if sizes[i] < MAX_PER_SHIPMENT:
                sizes[i] += 1
                break
    return sizes


def generate_distribution(scale: Scale, master: dict[str, list[dict]],
                          production: dict[str, list[dict]], seed: int = SEED):
    customers = master["customer"]
    cust_by_id = {c["customer_id"]: c for c in customers}
    crng = stage_rng(seed, "dist.customers")
    cum = list(accumulate(TYPE_POPULARITY[c["customer_type"]] * crng.lognormvariate(0, 0.8)
                          for c in customers))

    rng = stage_rng(seed, "dist.deliveries")
    lots = sorted(production["finished_lot"], key=lambda l: l["finished_lot_id"])
    dispatched = {l["finished_lot_id"]: _dispatch_qty(rng, l) for l in lots}
    shipping = [l for l in lots if dispatched[l["finished_lot_id"]] >= 1]
    counts = allocate(scale.deliveries, {l["finished_lot_id"]: dispatched[l["finished_lot_id"]] ** FANOUT_EXPONENT
                                         for l in shipping})

    deliveries = []
    for lot in shipping:
        lot_id = lot["finished_lot_id"]
        total, n = dispatched[lot_id], counts[lot_id]
        if n > total:
            raise ValueError(f"{lot_id}: {n} deliveries for only {total} packs")
        produced = date.fromisoformat(lot["produced_date"])
        chosen, readies = [], []
        while len(chosen) < n:
            ready = min(produced + timedelta(days=rng.randint(*READY_LAG_DAYS)), AS_OF)
            c = rng.choices(customers, cum_weights=cum, k=1)[0]
            if c["customer_id"] in {x["customer_id"] for x in chosen}:
                continue
            if c["status"] == "INACTIVE" and ready > INACTIVE_CUSTOMER_CUTOFF:
                continue
            chosen.append(c)
            readies.append(ready)
        sizes = allocate(total, {str(i): TYPE_SIZE[c["customer_type"]] * rng.lognormvariate(0, 0.4)
                                 for i, c in enumerate(chosen)})
        for i, (c, ready) in enumerate(zip(chosen, readies)):
            deliveries.append({
                "finished_lot_id": lot_id, "customer_id": c["customer_id"],
                "qty": sizes[str(i)], "ready": ready,
                "warehouse": rng.choice(REGION_WAREHOUSES[c["region"]]),
            })

    # ---- group deliveries into shipments, one warehouse each ----
    by_wh = defaultdict(list)
    for dlv in deliveries:
        by_wh[dlv["warehouse"]].append(dlv)
    for group in by_wh.values():
        group.sort(key=lambda x: (x["ready"], x["finished_lot_id"], x["customer_id"]))
    ship_counts = allocate(scale.shipments, {w: len(g) for w, g in by_wh.items()})
    grng = stage_rng(seed, "dist.shipments")
    shipments = []
    for wh in sorted(by_wh):
        group, pos = by_wh[wh], 0
        for size in _chunk_sizes(grng, len(group), ship_counts[wh]):
            members = group[pos:pos + size]
            pos += size
            shipments.append({"warehouse": wh, "carrier": grng.choice(CARRIERS),
                              "ship": max(m["ready"] for m in members), "members": members})
    shipments.sort(key=lambda s: (s["ship"], s["warehouse"], s["members"][0]["finished_lot_id"],
                                  s["members"][0]["customer_id"]))

    ship_ids, del_ids = IdCounter("shipment_id"), IdCounter("delivery_id")
    drng = stage_rng(seed, "dist.status")
    ship_rows, del_rows = [], []
    stats = {"failed": 0, "in_transit": 0}
    for s in shipments:
        s["shipment_id"] = ship_ids.next()
        statuses = []
        for m in sorted(s["members"], key=lambda x: (x["finished_lot_id"], x["customer_id"])):
            delivered_on = s["ship"] + timedelta(days=drng.randint(*TRANSIT_DAYS))
            if delivered_on > AS_OF:
                status = "IN_TRANSIT"
            elif drng.random() < FAILED_SHARE:
                status = "FAILED"
            else:
                status = "DELIVERED"
            statuses.append(status)
            del_rows.append({
                "delivery_id": del_ids.next(), "shipment_id": s["shipment_id"],
                "finished_lot_id": m["finished_lot_id"], "customer_id": m["customer_id"],
                "qty_delivered": m["qty"], "delivery_date": delivered_on.isoformat(), "status": status,
            })
        stats["failed"] += statuses.count("FAILED")
        stats["in_transit"] += statuses.count("IN_TRANSIT")
        if all(x == "FAILED" for x in statuses):
            ship_status = "CANCELLED"
        elif "IN_TRANSIT" in statuses:
            ship_status = "IN_TRANSIT"
        else:
            ship_status = "DELIVERED"
        ship_rows.append({"shipment_id": s["shipment_id"], "warehouse_code": s["warehouse"],
                          "carrier_code": s["carrier"], "ship_date": s["ship"].isoformat(),
                          "status": ship_status})
    stats["lots_without_dispatch"] = len(lots) - len(shipping)
    stats["cancelled_shipments"] = sum(1 for r in ship_rows if r["status"] == "CANCELLED")
    return {"shipment": ship_rows, "delivery": del_rows}, stats
