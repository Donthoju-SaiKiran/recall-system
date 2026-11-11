"""Stage-isolated random number generators.

Each generation stage gets its own Random seeded from (seed, stage name).
Adding or changing one stage never shifts the numbers drawn by another.
"""
from __future__ import annotations

import hashlib
import random


def stage_rng(seed: int, stage: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{stage}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))
