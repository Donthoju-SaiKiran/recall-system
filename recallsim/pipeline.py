"""Run the clean generation stages in order. Returns all 12 tables and the recall answer key."""
from __future__ import annotations

from .config import SEED, Scale
from .generate.distribution import generate_distribution
from .generate.master import generate_master
from .generate.production import generate_production
from .recall import apply_sale_status, generate_recalls


def build_clean(scale: Scale, seed: int = SEED):
    master = generate_master(scale, seed)
    production, _ = generate_production(scale, master, seed)
    dist, _ = generate_distribution(scale, master, production, seed)
    rows = {**master, **production, **dist}
    recall, answer_key, _ = generate_recalls(scale, rows, seed)
    rows.update(recall)
    rows["finished_lot"] = apply_sale_status(rows, recall)
    return rows, answer_key
