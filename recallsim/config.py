"""Seed and scale presets. Starter and full datasets use the same generator."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

SEED = 20261022
# The generated world is "as of" this date. Later phases never create events after it,
# except planned work orders that start in the future.
AS_OF = date(2026, 11, 1)


@dataclass(frozen=True)
class Scale:
    name: str
    suppliers: int
    customers: int
    products: int
    raw_lots: int
    work_orders: int
    finished_lots: int
    shipments: int
    deliveries: int


FULL = Scale("full", suppliers=500, customers=1500, products=40, raw_lots=10_000,
             work_orders=5_000, finished_lots=8_000, shipments=12_000, deliveries=20_000)


def _scaled(name: str, factor: float) -> Scale:
    def n(x: int, minimum: int = 1) -> int:
        return max(minimum, round(x * factor))
    return Scale(name, n(FULL.suppliers), n(FULL.customers), n(FULL.products, 10),
                 n(FULL.raw_lots), n(FULL.work_orders), n(FULL.finished_lots),
                 n(FULL.shipments), n(FULL.deliveries))


STARTER = _scaled("starter", 0.05)
SCALES = {"full": FULL, "starter": STARTER}


def get_scale(name: str) -> Scale:
    try:
        return SCALES[name]
    except KeyError:
        raise ValueError(f"unknown scale {name!r}, choose from {sorted(SCALES)}") from None
