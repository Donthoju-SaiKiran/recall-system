"""Single source of truth for the recall traceability data model.

Everything else (SQL DDL, data dictionary, validator, generator) reads this file.
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------- code lists (enums) ----------
MATERIAL_CODES = (
    "FLOUR", "SUGAR", "COCOA", "BUTTER", "MILK_POWDER", "EGG_POWDER",
    "PEANUT", "ALMOND", "VANILLA", "SALT", "PALM_OIL", "LECITHIN",
)
COUNTRIES = ("IN", "US", "DE", "VN", "BR", "ID", "NL", "TR", "GH", "CI")
SUPPLIER_TIERS = ("A", "B", "C")
SUPPLIER_STATUS = ("ACTIVE", "SUSPENDED", "INACTIVE")
PRODUCT_CATEGORIES = ("BISCUIT", "CHOCOLATE", "SNACK", "BAKERY_MIX")
PRODUCT_STATUS = ("ACTIVE", "DISCONTINUED")
WO_STATUS = ("PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED")
SHIPMENT_STATUS = ("PLANNED", "IN_TRANSIT", "DELIVERED", "CANCELLED")
DELIVERY_STATUS = ("IN_TRANSIT", "DELIVERED", "FAILED")
CUSTOMER_TYPES = ("RETAILER", "DISTRIBUTOR", "FOODSERVICE")
REGIONS = ("NORTH", "SOUTH", "EAST", "WEST", "CENTRAL")
CONTACT_CHANNELS = ("EMAIL", "PHONE", "PORTAL")
CUSTOMER_STATUS = ("ACTIVE", "INACTIVE")
LOT_TYPES = ("RAW", "FINISHED")
REASON_CODES = ("PATHOGEN", "ALLERGEN_UNDECLARED", "FOREIGN_MATTER", "CHEMICAL")
SEVERITIES = ("CLASS_I", "CLASS_II", "CLASS_III")
RECALL_STATUS = ("OPEN", "IN_PROGRESS", "CLOSED")
ACTION_TYPES = ("NOTIFY", "QUARANTINE", "RECOVER", "DISPOSE")
TARGET_TYPES = ("RAW_LOT", "FINISHED_LOT", "DELIVERY")
DISPOSITIONS = ("PENDING", "QUARANTINED", "RETURNED", "DESTROYED", "REWORKED")

# ---------- ID conventions (regex used by the validator) ----------
ID_PATTERNS = {
    "supplier_id": r"^S\d{4}$",
    "raw_lot_id": r"^RAWLOT-S\d{4}-2026-\d{6}$",
    "product_id": r"^P\d{3}$",
    "bom_line_id": r"^BOM-\d{6}$",
    "wo_id": r"^WO-2026-\d{6}$",
    "finished_lot_id": r"^FINLOT-2026-\d{6}$",
    "shipment_id": r"^SHP-2026-\d{6}$",
    "customer_id": r"^C\d{5}$",
    "delivery_id": r"^DEL-2026-\d{6}$",
    "recall_id": r"^REC-2026-\d{6}$",
    "action_id": r"^ACT-2026-\d{6}$",
}


@dataclass(frozen=True)
class Col:
    name: str
    type: str  # TEXT | INTEGER | REAL | DATE | TIMESTAMP
    desc: str
    required: bool = True
    unit: str | None = None
    allowed: tuple | None = None
    unique: bool = False
    minimum: float | None = None
    rule: str | None = None  # human-readable validation rule
    fk: tuple[str, str] | None = None  # (table, column)


@dataclass(frozen=True)
class Table:
    name: str
    desc: str
    pk: tuple[str, ...]
    cols: tuple[Col, ...]
    cardinality: str = ""
    lifecycle: str = ""


# small constructors keep the table definitions readable
def key(name, desc, **kw):
    """ID column that follows the documented pattern."""
    return Col(name, "TEXT", desc, rule=f"matches {ID_PATTERNS[name]}", **kw)


def txt(name, desc, **kw):
    return Col(name, "TEXT", desc, **kw)


def whole(name, desc, **kw):
    return Col(name, "INTEGER", desc, **kw)


def real(name, desc, **kw):
    return Col(name, "REAL", desc, **kw)


def day(name, desc, **kw):
    return Col(name, "DATE", desc, **kw)


def stamp(name, desc, **kw):
    return Col(name, "TIMESTAMP", desc, **kw)


def fk(name, desc, table, column=None, **kw):
    """Foreign key column. Pattern comes from the referenced key."""
    column = column or name
    pattern = f"matches {ID_PATTERNS[name]}; " if name in ID_PATTERNS else ""
    return Col(name, "TEXT", desc, fk=(table, column),
               rule=f"{pattern}must exist in {table}.{column}", **kw)


# Parents first, children after. The generator follows this order.
TABLES: tuple[Table, ...] = (
    Table(
        "supplier", "Company that sells raw materials.", ("supplier_id",),
        (
            key("supplier_id", "Supplier key, e.g. S0001.", unique=True),
            txt("supplier_name", "Synthetic company name.", rule="non-empty"),
            txt("country", "Supplier country code.", allowed=COUNTRIES),
            txt("tier", "Quality tier, A is best.", allowed=SUPPLIER_TIERS),
            txt("status", "Supplier lifecycle state.", allowed=SUPPLIER_STATUS),
            day("onboarded_date", "Date supplier was onboarded.",
                rule="on or before its first lot received_date"),
        ),
        cardinality="1 supplier : N material_lot",
        lifecycle="ACTIVE -> SUSPENDED -> INACTIVE",
    ),
    Table(
        "customer", "Shop, distributor or food-service buyer that receives goods.",
        ("customer_id",),
        (
            key("customer_id", "Customer key, e.g. C00001.", unique=True),
            txt("customer_name", "Synthetic business name.", rule="non-empty"),
            txt("customer_type", "Kind of buyer.", allowed=CUSTOMER_TYPES),
            txt("region", "Sales region.", allowed=REGIONS),
            txt("contact_channel", "How a recall notice reaches them.",
                allowed=CONTACT_CHANNELS),
            txt("status", "Customer lifecycle state.", allowed=CUSTOMER_STATUS),
        ),
        cardinality="1 customer : N delivery",
        lifecycle="ACTIVE -> INACTIVE",
    ),
    Table(
        "product", "Finished product we sell.", ("product_id",),
        (
            key("product_id", "Product key, e.g. P001.", unique=True),
            txt("product_name", "Synthetic product name.", rule="non-empty"),
            txt("category", "Product family.", allowed=PRODUCT_CATEGORIES),
            real("pack_size_kg", "Weight of one pack.", unit="kg", minimum=0.01),
            whole("shelf_life_days", "Days from production to expiry.",
                  unit="days", minimum=1),
            txt("status", "Product lifecycle state.", allowed=PRODUCT_STATUS),
        ),
        cardinality="1 product : N bom_line, 1 product : N production_order",
        lifecycle="ACTIVE -> DISCONTINUED",
    ),
    Table(
        "bom_line", "Bill of Materials line: kg of one material per pack.",
        ("bom_line_id",),
        (
            key("bom_line_id", "BOM line key.", unique=True),
            fk("product_id", "Product this recipe line belongs to.", "product"),
            txt("material_code", "Material required.", allowed=MATERIAL_CODES),
            real("qty_per_pack", "Material needed per finished pack.",
                 unit="kg", minimum=0.0001,
                 rule="sum of lines per product <= product.pack_size_kg"),
            day("effective_from", "First day this line applies."),
            day("effective_to", "Last day this line applies, empty = open.",
                required=False, rule="empty or >= effective_from"),
        ),
        cardinality="1 product : N bom_line",
        lifecycle="effective_from .. effective_to (versioned recipe)",
    ),
    Table(
        "material_lot", "One received batch of a raw material.", ("raw_lot_id",),
        (
            key("raw_lot_id", "Raw lot key, supplier id embedded.", unique=True),
            fk("supplier_id", "Supplier of this lot.", "supplier"),
            txt("material_code", "Material in the lot.", allowed=MATERIAL_CODES),
            real("qty_received", "Quantity received.", unit="kg", minimum=0.001),
            day("received_date", "Date received at the plant."),
            day("expiry_date", "Date material expires.",
                rule=">= received_date"),
        ),
        cardinality="1 supplier : N material_lot, N material_lot : N production_order",
        lifecycle="RECEIVED -> CONSUMED (derived from wo_input_lot) -> QUARANTINED (derived from recall_action)",
    ),
    Table(
        "production_order", "A factory job that makes one product.", ("wo_id",),
        (
            key("wo_id", "Work order key.", unique=True),
            fk("product_id", "Product being made.", "product"),
            whole("planned_qty", "Packs planned.", unit="pack", minimum=1),
            txt("line_code", "Production line, e.g. LINE-01."),
            day("start_date", "Job start date."),
            day("end_date", "Job end date, empty while running.", required=False,
                rule="empty or >= start_date"),
            txt("status", "Job state.", allowed=WO_STATUS),
        ),
        cardinality="1 product : N production_order, 1 production_order : N finished_lot",
        lifecycle="PLANNED -> IN_PROGRESS -> COMPLETED | CANCELLED",
    ),
    Table(
        "wo_input_lot", "Bridge: which raw lots a job consumed and how much.",
        ("wo_id", "raw_lot_id"),
        (
            fk("wo_id", "Production order.", "production_order"),
            fk("raw_lot_id", "Raw lot consumed.", "material_lot"),
            real("qty_consumed", "Quantity consumed from the lot.", unit="kg",
                 minimum=0.001,
                 rule="sum per raw lot <= material_lot.qty_received"),
            day("consumed_date", "Date of consumption.",
                rule=">= lot received_date and within job dates"),
        ),
        cardinality="N production_order : N material_lot (bridge)",
        lifecycle="insert-only",
    ),
    Table(
        "finished_lot", "Batch of packs produced by one job.", ("finished_lot_id",),
        (
            key("finished_lot_id", "Finished lot key.", unique=True),
            fk("wo_id", "Job that produced it.", "production_order"),
            whole("qty_produced", "Packs produced.", unit="pack", minimum=1,
                  rule="<= packs possible from consumed inputs"),
            day("produced_date", "Production date.",
                rule="within job start_date..end_date"),
            day("expiry_date", "Best-before date.", rule="> produced_date"),
        ),
        cardinality="1 production_order : N finished_lot, 1 finished_lot : N delivery",
        lifecycle="PRODUCED -> DELIVERED (derived) -> QUARANTINED (derived from recall_action)",
    ),
    Table(
        "shipment", "A truck leaving a warehouse.", ("shipment_id",),
        (
            key("shipment_id", "Shipment key.", unique=True),
            txt("warehouse_code", "Origin warehouse, e.g. WH-HYD."),
            txt("carrier_code", "Carrier, e.g. CAR-07."),
            day("ship_date", "Departure date."),
            txt("status", "Shipment state.", allowed=SHIPMENT_STATUS),
        ),
        cardinality="1 shipment : N delivery",
        lifecycle="PLANNED -> IN_TRANSIT -> DELIVERED | CANCELLED",
    ),
    Table(
        "delivery", "Bridge: quantity of one finished lot dropped to one customer on one shipment.",
        ("delivery_id",),
        (
            key("delivery_id", "Delivery key.", unique=True),
            fk("shipment_id", "Shipment carrying it.", "shipment"),
            fk("finished_lot_id", "Finished lot delivered.", "finished_lot"),
            fk("customer_id", "Receiving customer.", "customer"),
            whole("qty_delivered", "Packs delivered.", unit="pack", minimum=1,
                  rule="sum per finished lot <= finished_lot.qty_produced"),
            day("delivery_date", "Date delivered.", rule=">= shipment.ship_date and >= produced_date"),
            txt("status", "Delivery state.", allowed=DELIVERY_STATUS),
        ),
        cardinality="N finished_lot : N customer (bridge via shipment)",
        lifecycle="IN_TRANSIT -> DELIVERED | FAILED",
    ),
    Table(
        "recall_case", "One recall opened for one contaminated lot.", ("recall_id",),
        (
            key("recall_id", "Recall key.", unique=True),
            txt("trigger_lot_type", "Which kind of lot triggered it.",
                allowed=LOT_TYPES),
            txt("trigger_lot_id", "Lot id that triggered it.",
                rule="must exist in material_lot or finished_lot per trigger_lot_type "
                     "(no DB foreign key, checked by validator)"),
            txt("reason_code", "Why recalled.", allowed=REASON_CODES),
            txt("severity", "Regulatory class.", allowed=SEVERITIES),
            day("opened_date", "Date recall opened.",
                rule=">= trigger lot received/produced date"),
            day("closed_date", "Date recall closed, empty while open.",
                required=False, rule="empty or >= opened_date"),
            txt("status", "Recall state.", allowed=RECALL_STATUS),
        ),
        cardinality="1 recall_case : N recall_action",
        lifecycle="OPEN -> IN_PROGRESS -> CLOSED",
    ),
    Table(
        "recall_action", "Append-only event: one step taken during a recall.",
        ("action_id",),
        (
            key("action_id", "Action key.", unique=True),
            fk("recall_id", "Recall this action belongs to.", "recall_case"),
            txt("action_type", "What was done.", allowed=ACTION_TYPES),
            txt("target_type", "What kind of thing it was done to.",
                allowed=TARGET_TYPES),
            txt("target_id", "Id of that thing.",
                rule="must exist in table named by target_type (validator)"),
            fk("customer_id", "Customer notified or recovered from.", "customer",
               required=False),
            real("qty_affected", "Quantity in scope (kg for RAW_LOT, packs otherwise).",
                 minimum=0, unit="kg or pack"),
            real("qty_recovered", "Quantity physically recovered, RECOVER only.",
                 required=False, minimum=0, rule="<= qty_affected"),
            txt("disposition", "Outcome of the stock.", allowed=DISPOSITIONS),
            stamp("action_ts", "When the action happened.",
                  rule=">= recall_case.opened_date"),
        ),
        cardinality="1 recall_case : N recall_action",
        lifecycle="insert-only, never updated",
    ),
)

TABLE_BY_NAME = {t.name: t for t in TABLES}
