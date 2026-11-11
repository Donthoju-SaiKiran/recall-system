"""Phase 2: raw lots, production orders, consumption bridge, finished lots.

Generation is demand driven so quantities reconcile by construction:
  1. plan work orders and the kg of each material they need
  2. size raw lot supply from that demand
  3. consume lots first-expiry-first-out with a running balance per lot
  4. split each job's output into finished lots
"""
from __future__ import annotations

import heapq
import math
from collections import defaultdict
from datetime import date, timedelta

from ..config import AS_OF, SEED, Scale
from ..ids import IdCounter
from ..rng import stage_rng
from ..schema import MATERIAL_CODES
from ..util import allocate

# ---- tunables (documented in README later) ----
SUPPLY_FACTOR = 1.25                      # total raw supply = demand x this
STATUS_SHARE = {"CANCELLED": 0.04, "IN_PROGRESS": 0.04, "PLANNED": 0.02}
JOB_WINDOW = (date(2026, 2, 1), date(2026, 10, 15))   # start dates of completed jobs
IN_PROGRESS_WINDOW = (date(2026, 10, 27), date(2026, 10, 31))
PLANNED_WINDOW = (date(2026, 11, 2), date(2026, 11, 20))
LOT_EARLIEST = date(2026, 1, 2)
LOT_LEAD_DAYS = (3, 45)                   # lot arrives this many days before the job
INACTIVE_CUTOFF = date(2026, 6, 30)       # inactive suppliers only supply before this
PLANNED_QTY = {                            # packs per job, by category
    "BISCUIT": (3000, 20000), "CHOCOLATE": (2000, 12000),
    "SNACK": (3000, 18000), "BAKERY_MIX": (1000, 6000),
}
YIELD_RANGE = (0.92, 1.0)
LOSS_RANGE = (0.01, 0.04)                 # extra material lost in production
LOTS_PER_JOB = {1: 40, 2: 42, 3: 18}
MAX_LOTS_PER_JOB = 4
MATERIALS_PER_SUPPLIER = {1: 50, 2: 35, 3: 15}
TIER_VOLUME = {"A": 3.0, "B": 2.0, "C": 1.0}
SHELF_DAYS = {                              # raw material shelf life range, days
    "FLOUR": (240, 365), "SUGAR": (540, 720), "COCOA": (365, 540), "BUTTER": (90, 150),
    "MILK_POWDER": (270, 365), "EGG_POWDER": (180, 300), "PEANUT": (180, 270),
    "ALMOND": (270, 365), "VANILLA": (540, 720), "SALT": (720, 1095),
    "PALM_OIL": (270, 365), "LECITHIN": (365, 540),
}
LINE_CODES = tuple(f"LINE-{i:02d}" for i in range(1, 7))


def _day(rng, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _supplier_materials(rng, suppliers: list[dict]) -> dict[str, list[str]]:
    """Which materials each supplier sells (derived, no table)."""
    mapping = {}
    for s in suppliers:
        k = rng.choices(list(MATERIALS_PER_SUPPLIER), weights=list(MATERIALS_PER_SUPPLIER.values()))[0]
        mapping[s["supplier_id"]] = rng.sample(MATERIAL_CODES, k)
    # every material needs at least one active supplier
    active = [s["supplier_id"] for s in suppliers if s["status"] == "ACTIVE"] or \
             [s["supplier_id"] for s in suppliers]
    for m in MATERIAL_CODES:
        has = any(m in mats and sid in set(active) for sid, mats in mapping.items())
        if not has:
            sid = rng.choice(active)
            mapping[sid].append(m)
    return mapping


def _bom_lookup(bom_lines: list[dict]):
    by_product = defaultdict(list)
    for line in bom_lines:
        by_product[line["product_id"]].append(line)

    def at(product_id: str, day: date) -> dict[str, float]:
        d = day.isoformat()
        return {l["material_code"]: l["qty_per_pack"] for l in by_product[product_id]
                if l["effective_from"] <= d and (l["effective_to"] is None or l["effective_to"] >= d)}
    return at


def _plan_work_orders(rng, scale: Scale, products: list[dict], bom_at) -> list[dict]:
    n = scale.work_orders
    statuses = []
    for status, share in STATUS_SHARE.items():
        statuses += [status] * round(n * share)
    statuses += ["COMPLETED"] * (n - len(statuses))
    rng.shuffle(statuses)
    usable = [p for p in products if p["status"] == "ACTIVE"] or products
    popularity = [rng.lognormvariate(0, 0.6) for _ in usable]
    plans = []
    for i, status in enumerate(statuses):
        product = rng.choices(usable, weights=popularity)[0]
        lo, hi = PLANNED_QTY[product["category"]]
        planned = round(rng.randint(lo, hi) / 100) * 100
        if status in ("COMPLETED", "CANCELLED"):
            start = _day(rng, *JOB_WINDOW)
            end = start + timedelta(days=rng.randint(1, 5) if status == "COMPLETED" else rng.randint(0, 1))
        elif status == "IN_PROGRESS":
            start, end = _day(rng, *IN_PROGRESS_WINDOW), None
        else:
            start, end = _day(rng, *PLANNED_WINDOW), None
        plan = {"_i": i, "product": product, "planned": planned, "status": status,
                "start": start, "end": end, "line": rng.choice(LINE_CODES)}
        if status == "COMPLETED":
            plan["packs"] = int(planned * rng.uniform(*YIELD_RANGE))
            loss = rng.uniform(*LOSS_RANGE)
            recipe = bom_at(product["product_id"], start)
            plan["unit_g"] = {m: q * (1 + loss) * 1000 for m, q in recipe.items()}
            plan["need_g"] = {m: round(plan["packs"] * g) for m, g in plan["unit_g"].items()}
        plans.append(plan)
    plans.sort(key=lambda p: (p["start"], p["_i"]))
    return plans


def _make_lots(rng, scale: Scale, suppliers: list[dict], sup_mats: dict[str, list[str]],
               plans: list[dict]) -> list[dict]:
    sup_by_id = {s["supplier_id"]: s for s in suppliers}

    def eligible(material: str, late: bool):
        out = []
        for sid, mats in sup_mats.items():
            if material not in mats:
                continue
            s = sup_by_id[sid]
            w = TIER_VOLUME[s["tier"]]
            if s["status"] == "INACTIVE":
                if late:
                    continue
                w *= 0.5
            elif s["status"] == "SUSPENDED":
                w *= 0.3
            out.append((sid, w))
        return out

    demand = defaultdict(int)
    events = defaultdict(list)
    for p in plans:
        if p["status"] == "COMPLETED":
            for m, g in p["need_g"].items():
                demand[m] += g
                events[m].append((p["start"], g))
    materials = [m for m in MATERIAL_CODES if demand[m] > 0]
    counts = allocate(scale.raw_lots, {m: demand[m] for m in materials})

    lots = []
    for m in materials:
        early, late = eligible(m, False), eligible(m, True) or eligible(m, False)
        weights = [rng.lognormvariate(0, 0.5) for _ in range(counts[m])]
        supply_g = SUPPLY_FACTOR * demand[m]
        starts = [e[0] for e in events[m]]
        start_weights = [e[1] for e in events[m]]
        targets = rng.choices(starts, weights=start_weights, k=counts[m])
        for w, target in zip(weights, targets):
            received = max(LOT_EARLIEST, target - timedelta(days=rng.randint(*LOT_LEAD_DAYS)))
            pool = early if received <= INACTIVE_CUTOFF else late
            sid = rng.choices([x[0] for x in pool], weights=[x[1] for x in pool])[0]
            lots.append({
                "supplier_id": sid, "material_code": m,
                "qty_g": max(1000, round(supply_g * w / sum(weights))),
                "received": received,
                "expiry": received + timedelta(days=rng.randint(*SHELF_DAYS[m])),
            })
    lots.sort(key=lambda l: (l["received"], l["material_code"], l["supplier_id"], l["qty_g"]))
    ids = IdCounter("raw_lot_id")
    for lot in lots:
        lot["raw_lot_id"] = ids.next(supplier_id=lot["supplier_id"])
    return lots



def _consume(rng, plans: list[dict], lots: list[dict]):
    """FEFO consumption with a running balance. Returns bridge rows, stats."""
    remaining = {l["raw_lot_id"]: l["qty_g"] for l in lots}
    pending = defaultdict(list)           # material -> lots not yet received, by received date
    for l in lots:
        pending[l["material_code"]].append(l)
    pointer = defaultdict(int)
    heaps = defaultdict(list)             # material -> heap of (expiry, received, id)
    rows = []
    stats = {"reduced_wos": 0, "cancelled_for_shortage": 0, "packs_lost_to_shortage": 0}

    for plan in plans:
        if plan["status"] != "COMPLETED":
            continue
        start, end = plan["start"], plan["end"]
        avail = {}
        for m in plan["need_g"]:
            lst, ptr = pending[m], pointer[m]
            while ptr < len(lst) and lst[ptr]["received"] <= start:
                l = lst[ptr]
                heapq.heappush(heaps[m], (l["expiry"].isoformat(), l["received"].isoformat(), l["raw_lot_id"]))
                ptr += 1
            pointer[m] = ptr
            avail[m] = sum(remaining[i] for exp, _r, i in heaps[m] if exp >= end.isoformat())

        packs = plan["packs"]
        for m, g in plan["unit_g"].items():
            packs = min(packs, int(avail[m] / g))
        while packs > 0 and any(round(packs * g) > avail[m] for m, g in plan["unit_g"].items()):
            packs -= 1
        if packs < plan["packs"]:
            stats["reduced_wos"] += 1
            stats["packs_lost_to_shortage"] += plan["packs"] - packs
        if packs < 1:
            plan.update(status="CANCELLED", end=start, packs=0, need_g={})
            stats["cancelled_for_shortage"] += 1
            continue
        plan["packs"] = packs

        for m, g in plan["unit_g"].items():
            need = round(packs * g)
            plan["need_g"][m] = need
            heap = heaps[m]
            while need > 0:
                exp, rec, lot_id = heapq.heappop(heap)
                if exp < end.isoformat():
                    continue                       # expired lot is dropped for good
                take = min(remaining[lot_id], need)
                remaining[lot_id] -= take
                need -= take
                rows.append({"wo": plan, "raw_lot_id": lot_id, "g": take,
                             "consumed": _day(rng, start, end)})
                if remaining[lot_id] > 0:
                    heapq.heappush(heap, (exp, rec, lot_id))
    return rows, remaining, stats


def _split(rng, packs: int, n: int) -> list[int]:
    """Split packs into n lots, each at least 10 percent of the job output."""
    if n == 1:
        return [packs]
    floor = max(1, packs // 10)
    spare = packs - n * floor
    cuts = sorted(rng.randint(0, spare) for _ in range(n - 1))
    extra = [b - a for a, b in zip([0] + cuts, cuts + [spare])]
    return [floor + e for e in extra]


def _lot_counts(rng, plans: list[dict], target: int) -> dict[int, int]:
    done = [p for p in plans if p["status"] == "COMPLETED" and p["packs"] > 0]
    counts = {p["_i"]: min(rng.choices(list(LOTS_PER_JOB), weights=list(LOTS_PER_JOB.values()))[0],
                           p["packs"]) for p in done}
    by_i = {p["_i"]: p for p in done}
    diff = target - sum(counts.values())
    for _ in range(100 * len(done) + 1000):
        if diff == 0:
            return counts
        i = rng.choice(list(counts))
        if diff > 0 and counts[i] < MAX_LOTS_PER_JOB and counts[i] < by_i[i]["packs"]:
            counts[i] += 1
            diff -= 1
        elif diff < 0 and counts[i] > 1:
            counts[i] -= 1
            diff += 1
    raise ValueError(f"cannot reach {target} finished lots from {len(done)} completed jobs")


def generate_production(scale: Scale, master: dict[str, list[dict]], seed: int = SEED):
    bom_at = _bom_lookup(master["bom_line"])
    plans = _plan_work_orders(stage_rng(seed, "prod.plan"), scale, master["product"], bom_at)
    sup_mats = _supplier_materials(stage_rng(seed, "prod.supplier_materials"), master["supplier"])
    lots = _make_lots(stage_rng(seed, "prod.lots"), scale, master["supplier"], sup_mats, plans)
    bridge, remaining, stats = _consume(stage_rng(seed, "prod.consume"), plans, lots)

    wo_ids = IdCounter("wo_id")
    for plan in plans:
        plan["wo_id"] = wo_ids.next()

    rng = stage_rng(seed, "prod.finished")
    counts = _lot_counts(rng, plans, scale.finished_lots)
    finished = []
    for plan in plans:
        if plan["_i"] not in counts:
            continue
        shelf = plan["product"]["shelf_life_days"]
        for qty in _split(rng, plan["packs"], counts[plan["_i"]]):
            produced = _day(rng, plan["start"], plan["end"])
            finished.append({"wo_id": plan["wo_id"], "qty_produced": qty,
                             "produced_date": produced.isoformat(),
                             "expiry_date": (produced + timedelta(days=shelf)).isoformat()})
    finished.sort(key=lambda f: (f["produced_date"], f["wo_id"], f["qty_produced"]))
    fl_ids = IdCounter("finished_lot_id")
    for f in finished:
        f["finished_lot_id"] = fl_ids.next()

    rows = {
        "material_lot": [{
            "raw_lot_id": l["raw_lot_id"], "supplier_id": l["supplier_id"],
            "material_code": l["material_code"], "qty_received": l["qty_g"] / 1000,
            "received_date": l["received"].isoformat(), "expiry_date": l["expiry"].isoformat(),
        } for l in lots],
        "production_order": [{
            "wo_id": p["wo_id"], "product_id": p["product"]["product_id"],
            "planned_qty": p["planned"], "line_code": p["line"],
            "start_date": p["start"].isoformat(),
            "end_date": p["end"].isoformat() if p["end"] else None, "status": p["status"],
        } for p in plans],
        "wo_input_lot": sorted(({
            "wo_id": r["wo"]["wo_id"], "raw_lot_id": r["raw_lot_id"], "qty_consumed": r["g"] / 1000,
            "consumed_date": r["consumed"].isoformat(),
        } for r in bridge), key=lambda r: (r["wo_id"], r["raw_lot_id"])),
        "finished_lot": finished,
    }
    stats["unused_lots"] = sum(1 for l in lots if remaining[l["raw_lot_id"]] == l["qty_g"])
    stats["lots"] = len(lots)
    return rows, stats
