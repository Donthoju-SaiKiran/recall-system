"""Phase 1: master data (supplier, customer, product, bom_line).

No hidden labels live here. Contamination is chosen in a later phase.
"""
from __future__ import annotations

import itertools
import math
from datetime import date, timedelta

from ..config import SEED, Scale
from ..ids import IdCounter
from ..rng import stage_rng
from ..schema import (
    CONTACT_CHANNELS, COUNTRIES, CUSTOMER_TYPES, PRODUCT_CATEGORIES, REGIONS,
    SUPPLIER_STATUS, SUPPLIER_TIERS,
)

# ---- distributions (weights follow the order of the schema enums) ----
TIER_WEIGHTS = dict(zip(SUPPLIER_TIERS, (20, 50, 30)))
SUPPLIER_STATUS_WEIGHTS = dict(zip(SUPPLIER_STATUS, (90, 7, 3)))
COUNTRY_WEIGHTS = dict(zip(COUNTRIES, (30, 10, 8, 10, 10, 10, 6, 6, 5, 5)))
CUSTOMER_TYPE_WEIGHTS = {"RETAILER": 60, "FOODSERVICE": 25, "DISTRIBUTOR": 15}
REGION_WEIGHTS = dict(zip(REGIONS, (20, 30, 15, 25, 10)))
CHANNEL_WEIGHTS = dict(zip(CONTACT_CHANNELS, (55, 20, 25)))
CATEGORY_WEIGHTS = dict(zip(PRODUCT_CATEGORIES, (40, 25, 20, 15)))

# category -> (pack size range kg, shelf life range days, core materials, optional pool)
CATEGORY_SPEC = {
    "BISCUIT": ((0.10, 0.40), (180, 270), ("FLOUR", "SUGAR"),
                ("BUTTER", "PALM_OIL", "MILK_POWDER", "SALT", "VANILLA", "EGG_POWDER", "LECITHIN")),
    "CHOCOLATE": ((0.05, 0.25), (270, 365), ("COCOA", "SUGAR"),
                  ("MILK_POWDER", "BUTTER", "LECITHIN", "VANILLA", "ALMOND", "PEANUT")),
    "SNACK": ((0.05, 0.30), (120, 210), ("FLOUR", "PALM_OIL"),
              ("SALT", "PEANUT", "ALMOND")),
    "BAKERY_MIX": ((0.50, 2.00), (270, 365), ("FLOUR", "SUGAR"),
                   ("EGG_POWDER", "MILK_POWDER", "SALT", "VANILLA", "LECITHIN")),
}

SUPPLIER_WORDS = (
    ("Northern", "Golden", "Blue", "Evergreen", "Summit", "Harbor", "Prairie", "Sunrise",
     "Riverbend", "Oakline", "Crestview", "Lakeside", "Ironwood", "Maple", "Silverleaf",
     "Redstone", "Clearwater", "Stonebridge", "Highland", "Meadow"),
    ("Agro", "Mills", "Farms", "Harvest", "Grain", "Foods", "Commodities", "Ingredients",
     "Growers", "Traders", "Refinery", "Estates", "Naturals", "Supply", "Cooperative"),
    ("Ltd", "Inc", "GmbH", "Co", "Pvt Ltd", "SA"),
)
CUSTOMER_WORDS = (
    ("Greenfield", "Lakeview", "Hilltop", "Riverside", "Sunnyside", "Central", "Park",
     "Orchard", "Westgate", "Eastside", "Bayview", "Fairmont", "Brookside", "Cedar",
     "Elmwood", "Fernhill", "Garden", "Highpoint", "Kingsway", "Linden", "Millbrook",
     "Northgate", "Oakridge", "Pinecrest", "Queens", "Rosewood", "Southpoint", "Tanglewood",
     "Union", "Valley"),
    ("Mart", "Stores", "Grocers", "Bazaar", "Foods", "Supermarket", "Cafe", "Canteen",
     "Wholesale", "Provisions", "Kitchen", "Market"),
    ("North", "South", "East", "West"),
)
FLAVORS = ("Classic", "Choco Chip", "Butter", "Honey Oat", "Almond Crunch", "Peanut Crunch",
           "Vanilla Cream", "Salted Caramel", "Dark Cocoa", "Milk Cocoa", "Coconut", "Ginger",
           "Cardamom", "Fruit Mix", "Multigrain", "Sesame", "Masala", "Cheese", "Hazelnut",
           "Mocha")
FORMS = {
    "BISCUIT": ("Biscuits", "Cookies", "Rusks", "Wafers"),
    "CHOCOLATE": ("Bar", "Bites", "Truffles", "Slab"),
    "SNACK": ("Crisps", "Sticks", "Puffs", "Clusters"),
    "BAKERY_MIX": ("Cake Mix", "Muffin Mix", "Bread Mix", "Pancake Mix"),
}

# Some products change recipe on a date inside this window (shows effective dating).
RECIPE_V1_START = date(2025, 1, 1)
RECIPE_CHANGE_WINDOW = (date(2026, 4, 1), date(2026, 8, 31))
RECIPE_CHANGE_SHARE = 0.20


def _pick(rng, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def _random_date(rng, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _unique_names(rng, n: int, a, b, c) -> list[str]:
    combos = list(itertools.product(a, b, c))
    rng.shuffle(combos)
    names = [" ".join(x) for x in combos[:n]]
    # pool smaller than n: number the extras so every name stays unique
    names += [f"{' '.join(combos[i % len(combos)])} {i // len(combos) + 1}"
              for i in range(len(names), n)]
    return names


def generate_suppliers(seed: int, scale: Scale) -> list[dict]:
    rng = stage_rng(seed, "master.supplier")
    ids = IdCounter("supplier_id")
    names = _unique_names(rng, scale.suppliers, *SUPPLIER_WORDS)
    return [
        {
            "supplier_id": ids.next(),
            "supplier_name": name,
            "country": _pick(rng, COUNTRY_WEIGHTS),
            "tier": _pick(rng, TIER_WEIGHTS),
            "status": _pick(rng, SUPPLIER_STATUS_WEIGHTS),
            "onboarded_date": _random_date(rng, date(2018, 1, 1), date(2025, 6, 30)).isoformat(),
        }
        for name in names
    ]


def generate_customers(seed: int, scale: Scale) -> list[dict]:
    rng = stage_rng(seed, "master.customer")
    ids = IdCounter("customer_id")
    names = _unique_names(rng, scale.customers, *CUSTOMER_WORDS)
    return [
        {
            "customer_id": ids.next(),
            "customer_name": name,
            "customer_type": _pick(rng, CUSTOMER_TYPE_WEIGHTS),
            "region": _pick(rng, REGION_WEIGHTS),
            "contact_channel": _pick(rng, CHANNEL_WEIGHTS),
            "status": "ACTIVE" if rng.random() < 0.95 else "INACTIVE",
        }
        for name in names
    ]


def generate_products(seed: int, scale: Scale) -> list[dict]:
    rng = stage_rng(seed, "master.product")
    ids = IdCounter("product_id")
    used: set[str] = set()
    products = []
    for _ in range(scale.products):
        category = _pick(rng, CATEGORY_WEIGHTS)
        (size_lo, size_hi), (life_lo, life_hi), _core, _pool = CATEGORY_SPEC[category]
        for attempt in range(100):
            name = f"{rng.choice(FLAVORS)} {rng.choice(FORMS[category])}"
            if attempt >= 50:
                name += f" {attempt}"
            if name not in used:
                break
        used.add(name)
        pack = round(rng.uniform(size_lo, size_hi) / 0.05) * 0.05
        products.append({
            "product_id": ids.next(),
            "product_name": name,
            "category": category,
            "pack_size_kg": round(max(pack, 0.05), 2),
            "shelf_life_days": rng.randint(life_lo, life_hi),
            "status": "ACTIVE" if rng.random() < 0.95 else "DISCONTINUED",
        })
    return products


def _recipe(rng, pack_size_kg: float, materials: list[str], core: tuple) -> dict[str, float]:
    """kg per pack for each material. Total is 85 to 98 percent of pack weight."""
    fraction = rng.uniform(0.85, 0.98)
    weights = {m: (rng.uniform(3, 6) if m in core else rng.uniform(0.3, 1.5)) for m in materials}
    total = sum(weights.values())
    # floor to 4 decimals so rounding can never push the sum above the pack size
    return {m: math.floor(pack_size_kg * fraction * w / total * 1e4) / 1e4
            for m, w in weights.items()}


def generate_bom(seed: int, products: list[dict]) -> list[dict]:
    rng = stage_rng(seed, "master.bom")
    ids = IdCounter("bom_line_id")
    lines = []
    for product in products:
        _size, _life, core, pool = CATEGORY_SPEC[product["category"]]
        n_lines = min(rng.randint(3, 6), len(core) + len(pool))
        extras = rng.sample(pool, n_lines - len(core))
        materials = list(core) + extras
        v1 = _recipe(rng, product["pack_size_kg"], materials, core)
        changes = rng.random() < RECIPE_CHANGE_SHARE
        change_day = _random_date(rng, *RECIPE_CHANGE_WINDOW) if changes else None
        for material, qty in v1.items():
            lines.append({
                "bom_line_id": ids.next(), "product_id": product["product_id"],
                "material_code": material, "qty_per_pack": qty,
                "effective_from": RECIPE_V1_START.isoformat(),
                "effective_to": (change_day - timedelta(days=1)).isoformat() if changes else None,
            })
        if changes:
            v2 = _recipe(rng, product["pack_size_kg"], materials, core)
            for material, qty in v2.items():
                lines.append({
                    "bom_line_id": ids.next(), "product_id": product["product_id"],
                    "material_code": material, "qty_per_pack": qty,
                    "effective_from": change_day.isoformat(), "effective_to": None,
                })
    return lines


def generate_master(scale: Scale, seed: int = SEED) -> dict[str, list[dict]]:
    products = generate_products(seed, scale)
    return {
        "supplier": generate_suppliers(seed, scale),
        "customer": generate_customers(seed, scale),
        "product": products,
        "bom_line": generate_bom(seed, products),
    }
