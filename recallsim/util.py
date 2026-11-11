"""Small shared helpers."""
from __future__ import annotations

import math


def allocate(total: int, weights: dict[str, float]) -> dict[str, int]:
    """Split `total` into integer counts proportional to weights, at least 1 each."""
    s = sum(weights.values())
    raw = {k: total * w / s for k, w in weights.items()}
    counts = {k: max(1, math.floor(v)) for k, v in raw.items()}
    order = sorted(raw, key=lambda k: (raw[k] - math.floor(raw[k]), k), reverse=True)
    diff = total - sum(counts.values())
    i = 0
    while diff != 0:
        key = order[i % len(order)] if diff > 0 else max(counts, key=lambda k: (counts[k], k))
        if diff > 0:
            counts[key] += 1
            diff -= 1
        elif counts[key] > 1:
            counts[key] -= 1
            diff += 1
        else:
            raise ValueError("cannot allocate: total smaller than number of groups")
        i += 1
    return counts
