"""Deterministic, zero padded, immutable ID formats."""
from __future__ import annotations

FORMATS = {
    "supplier_id": "S{n:04d}",
    "raw_lot_id": "RAWLOT-{supplier_id}-2026-{n:06d}",
    "product_id": "P{n:03d}",
    "bom_line_id": "BOM-{n:06d}",
    "wo_id": "WO-2026-{n:06d}",
    "finished_lot_id": "FINLOT-2026-{n:06d}",
    "shipment_id": "SHP-2026-{n:06d}",
    "customer_id": "C{n:05d}",
    "delivery_id": "DEL-2026-{n:06d}",
    "recall_id": "REC-2026-{n:06d}",
    "action_id": "ACT-2026-{n:06d}",
}


def make_id(kind: str, n: int, **parts: str) -> str:
    return FORMATS[kind].format(n=n, **parts)


class IdCounter:
    """Hands out 1, 2, 3 ... for one kind of ID. Never reuses a number."""

    def __init__(self, kind: str):
        self.kind = kind
        self._n = 0

    def next(self, **parts: str) -> str:
        self._n += 1
        return make_id(self.kind, self._n, **parts)
