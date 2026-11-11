# Data dictionary

Generated from `recallsim/schema.py`. Do not edit by hand.

## ID conventions

| Field | Pattern |
|---|---|
| supplier_id | `^S\d{4}$` |
| raw_lot_id | `^RAWLOT-S\d{4}-2026-\d{6}$` |
| product_id | `^P\d{3}$` |
| bom_line_id | `^BOM-\d{6}$` |
| wo_id | `^WO-2026-\d{6}$` |
| finished_lot_id | `^FINLOT-2026-\d{6}$` |
| shipment_id | `^SHP-2026-\d{6}$` |
| customer_id | `^C\d{5}$` |
| delivery_id | `^DEL-2026-\d{6}$` |
| recall_id | `^REC-2026-\d{6}$` |
| action_id | `^ACT-2026-\d{6}$` |

Counters are zero padded, IDs are immutable, and every referenced ID is copied exactly from its parent.

## Units

Raw material quantities are in kg. Finished goods quantities are in packs. Dates are ISO text (YYYY-MM-DD), timestamps are ISO text.

## supplier

Company that sells raw materials.

- Primary key: `supplier_id`
- Cardinality: 1 supplier : N material_lot
- Lifecycle: ACTIVE -> SUSPENDED -> INACTIVE

| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |
|---|---|---|---|---|---|---|---|---|
| supplier_id | text | required |  |  | yes | PK | matches ^S\d{4}$ | Supplier key, e.g. S0001. |
| supplier_name | text | required |  |  |  |  | non-empty | Synthetic company name. |
| country | text | required |  | IN, US, DE, VN, BR, ID, NL, TR, GH, CI |  |  |  | Supplier country code. |
| tier | text | required |  | A, B, C |  |  |  | Quality tier, A is best. |
| status | text | required |  | ACTIVE, SUSPENDED, INACTIVE |  |  |  | Supplier lifecycle state. |
| onboarded_date | date (ISO) | required |  |  |  |  | on or before its first lot received_date | Date supplier was onboarded. |

## customer

Shop, distributor or food-service buyer that receives goods.

- Primary key: `customer_id`
- Cardinality: 1 customer : N delivery
- Lifecycle: ACTIVE -> INACTIVE

| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |
|---|---|---|---|---|---|---|---|---|
| customer_id | text | required |  |  | yes | PK | matches ^C\d{5}$ | Customer key, e.g. C00001. |
| customer_name | text | required |  |  |  |  | non-empty | Synthetic business name. |
| customer_type | text | required |  | RETAILER, DISTRIBUTOR, FOODSERVICE |  |  |  | Kind of buyer. |
| region | text | required |  | NORTH, SOUTH, EAST, WEST, CENTRAL |  |  |  | Sales region. |
| contact_channel | text | required |  | EMAIL, PHONE, PORTAL |  |  |  | How a recall notice reaches them. |
| status | text | required |  | ACTIVE, INACTIVE |  |  |  | Customer lifecycle state. |

## product

Finished product we sell.

- Primary key: `product_id`
- Cardinality: 1 product : N bom_line, 1 product : N production_order
- Lifecycle: ACTIVE -> DISCONTINUED

| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |
|---|---|---|---|---|---|---|---|---|
| product_id | text | required |  |  | yes | PK | matches ^P\d{3}$ | Product key, e.g. P001. |
| product_name | text | required |  |  |  |  | non-empty | Synthetic product name. |
| category | text | required |  | BISCUIT, CHOCOLATE, SNACK, BAKERY_MIX |  |  |  | Product family. |
| pack_size_kg | decimal | required | kg |  |  |  | >= 0.01 | Weight of one pack. |
| shelf_life_days | integer | required | days |  |  |  | >= 1 | Days from production to expiry. |
| status | text | required |  | ACTIVE, DISCONTINUED |  |  |  | Product lifecycle state. |

## bom_line

Bill of Materials line: kg of one material per pack.

- Primary key: `bom_line_id`
- Cardinality: 1 product : N bom_line
- Lifecycle: effective_from .. effective_to (versioned recipe)

| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |
|---|---|---|---|---|---|---|---|---|
| bom_line_id | text | required |  |  | yes | PK | matches ^BOM-\d{6}$ | BOM line key. |
| product_id | text | required |  |  |  | FK -> product.product_id | matches ^P\d{3}$; must exist in product.product_id | Product this recipe line belongs to. |
| material_code | text | required |  | FLOUR, SUGAR, COCOA, BUTTER, MILK_POWDER, EGG_POWDER, PEANUT, ALMOND, VANILLA, SALT, PALM_OIL, LECITHIN |  |  |  | Material required. |
| qty_per_pack | decimal | required | kg |  |  |  | >= 0.0001; sum of lines per product <= product.pack_size_kg | Material needed per finished pack. |
| effective_from | date (ISO) | required |  |  |  |  |  | First day this line applies. |
| effective_to | date (ISO) | optional |  |  |  |  | empty or >= effective_from | Last day this line applies, empty = open. |

## material_lot

One received batch of a raw material.

- Primary key: `raw_lot_id`
- Cardinality: 1 supplier : N material_lot, N material_lot : N production_order
- Lifecycle: RECEIVED -> CONSUMED (derived from wo_input_lot) -> QUARANTINED (derived from recall_action)

| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |
|---|---|---|---|---|---|---|---|---|
| raw_lot_id | text | required |  |  | yes | PK | matches ^RAWLOT-S\d{4}-2026-\d{6}$ | Raw lot key, supplier id embedded. |
| supplier_id | text | required |  |  |  | FK -> supplier.supplier_id | matches ^S\d{4}$; must exist in supplier.supplier_id | Supplier of this lot. |
| material_code | text | required |  | FLOUR, SUGAR, COCOA, BUTTER, MILK_POWDER, EGG_POWDER, PEANUT, ALMOND, VANILLA, SALT, PALM_OIL, LECITHIN |  |  |  | Material in the lot. |
| qty_received | decimal | required | kg |  |  |  | >= 0.001 | Quantity received. |
| received_date | date (ISO) | required |  |  |  |  |  | Date received at the plant. |
| expiry_date | date (ISO) | required |  |  |  |  | >= received_date | Date material expires. |

## production_order

A factory job that makes one product.

- Primary key: `wo_id`
- Cardinality: 1 product : N production_order, 1 production_order : N finished_lot
- Lifecycle: PLANNED -> IN_PROGRESS -> COMPLETED | CANCELLED

| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |
|---|---|---|---|---|---|---|---|---|
| wo_id | text | required |  |  | yes | PK | matches ^WO-2026-\d{6}$ | Work order key. |
| product_id | text | required |  |  |  | FK -> product.product_id | matches ^P\d{3}$; must exist in product.product_id | Product being made. |
| planned_qty | integer | required | pack |  |  |  | >= 1 | Packs planned. |
| line_code | text | required |  |  |  |  |  | Production line, e.g. LINE-01. |
| start_date | date (ISO) | required |  |  |  |  |  | Job start date. |
| end_date | date (ISO) | optional |  |  |  |  | empty or >= start_date | Job end date, empty while running. |
| status | text | required |  | PLANNED, IN_PROGRESS, COMPLETED, CANCELLED |  |  |  | Job state. |

## wo_input_lot

Bridge: which raw lots a job consumed and how much.

- Primary key: `wo_id, raw_lot_id`
- Cardinality: N production_order : N material_lot (bridge)
- Lifecycle: insert-only

| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |
|---|---|---|---|---|---|---|---|---|
| wo_id | text | required |  |  |  | PK; FK -> production_order.wo_id | matches ^WO-2026-\d{6}$; must exist in production_order.wo_id | Production order. |
| raw_lot_id | text | required |  |  |  | PK; FK -> material_lot.raw_lot_id | matches ^RAWLOT-S\d{4}-2026-\d{6}$; must exist in material_lot.raw_lot_id | Raw lot consumed. |
| qty_consumed | decimal | required | kg |  |  |  | >= 0.001; sum per raw lot <= material_lot.qty_received | Quantity consumed from the lot. |
| consumed_date | date (ISO) | required |  |  |  |  | >= lot received_date and within job dates | Date of consumption. |

## finished_lot

Batch of packs produced by one job.

- Primary key: `finished_lot_id`
- Cardinality: 1 production_order : N finished_lot, 1 finished_lot : N delivery
- Lifecycle: PRODUCED -> DELIVERED (derived) -> QUARANTINED (derived from recall_action)

| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |
|---|---|---|---|---|---|---|---|---|
| finished_lot_id | text | required |  |  | yes | PK | matches ^FINLOT-2026-\d{6}$ | Finished lot key. |
| wo_id | text | required |  |  |  | FK -> production_order.wo_id | matches ^WO-2026-\d{6}$; must exist in production_order.wo_id | Job that produced it. |
| qty_produced | integer | required | pack |  |  |  | >= 1; <= packs possible from consumed inputs | Packs produced. |
| produced_date | date (ISO) | required |  |  |  |  | within job start_date..end_date | Production date. |
| expiry_date | date (ISO) | required |  |  |  |  | > produced_date | Best-before date. |
| sale_status | text | required |  | AVAILABLE, RECALLED |  |  | RECALLED if the lot is in any recall scope, else AVAILABLE; a lot with a QUARANTINE action must not be AVAILABLE | Whether the lot may be sold. |

## shipment

A truck leaving a warehouse.

- Primary key: `shipment_id`
- Cardinality: 1 shipment : N delivery
- Lifecycle: PLANNED -> IN_TRANSIT -> DELIVERED | CANCELLED

| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |
|---|---|---|---|---|---|---|---|---|
| shipment_id | text | required |  |  | yes | PK | matches ^SHP-2026-\d{6}$ | Shipment key. |
| warehouse_code | text | required |  |  |  |  |  | Origin warehouse, e.g. WH-HYD. |
| carrier_code | text | required |  |  |  |  |  | Carrier, e.g. CAR-07. |
| ship_date | date (ISO) | required |  |  |  |  |  | Departure date. |
| status | text | required |  | PLANNED, IN_TRANSIT, DELIVERED, CANCELLED |  |  |  | Shipment state. |

## delivery

Bridge: quantity of one finished lot dropped to one customer on one shipment.

- Primary key: `delivery_id`
- Cardinality: N finished_lot : N customer (bridge via shipment)
- Lifecycle: IN_TRANSIT -> DELIVERED | FAILED

| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |
|---|---|---|---|---|---|---|---|---|
| delivery_id | text | required |  |  | yes | PK | matches ^DEL-2026-\d{6}$ | Delivery key. |
| shipment_id | text | required |  |  |  | FK -> shipment.shipment_id | matches ^SHP-2026-\d{6}$; must exist in shipment.shipment_id | Shipment carrying it. |
| finished_lot_id | text | required |  |  |  | FK -> finished_lot.finished_lot_id | matches ^FINLOT-2026-\d{6}$; must exist in finished_lot.finished_lot_id | Finished lot delivered. |
| customer_id | text | required |  |  |  | FK -> customer.customer_id | matches ^C\d{5}$; must exist in customer.customer_id | Receiving customer. |
| qty_delivered | integer | required | pack |  |  |  | >= 1; sum per finished lot <= finished_lot.qty_produced | Packs delivered. |
| delivery_date | date (ISO) | required |  |  |  |  | >= shipment.ship_date and >= produced_date; <= as-of date unless IN_TRANSIT | Date delivered, or expected arrival while IN_TRANSIT. |
| status | text | required |  | IN_TRANSIT, DELIVERED, FAILED |  |  |  | Delivery state. |

## recall_case

One recall opened for one contaminated lot.

- Primary key: `recall_id`
- Cardinality: 1 recall_case : N recall_action
- Lifecycle: OPEN -> IN_PROGRESS -> CLOSED

| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |
|---|---|---|---|---|---|---|---|---|
| recall_id | text | required |  |  | yes | PK | matches ^REC-2026-\d{6}$ | Recall key. |
| trigger_lot_type | text | required |  | RAW, FINISHED |  |  |  | Which kind of lot triggered it. |
| trigger_lot_id | text | required |  |  |  |  | must exist in material_lot or finished_lot per trigger_lot_type (no DB foreign key, checked by validator) | Lot id that triggered it. |
| reason_code | text | required |  | PATHOGEN, ALLERGEN_UNDECLARED, FOREIGN_MATTER, CHEMICAL |  |  |  | Why recalled. |
| severity | text | required |  | CLASS_I, CLASS_II, CLASS_III |  |  |  | Regulatory class. |
| opened_date | date (ISO) | required |  |  |  |  | >= trigger lot received/produced date | Date recall opened. |
| closed_date | date (ISO) | optional |  |  |  |  | empty or >= opened_date | Date recall closed, empty while open. |
| status | text | required |  | OPEN, IN_PROGRESS, CLOSED |  |  |  | Recall state. |

## recall_action

Append-only event: one step taken during a recall.

- Primary key: `action_id`
- Cardinality: 1 recall_case : N recall_action
- Lifecycle: insert-only, never updated

| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |
|---|---|---|---|---|---|---|---|---|
| action_id | text | required |  |  | yes | PK | matches ^ACT-2026-\d{6}$ | Action key. |
| recall_id | text | required |  |  |  | FK -> recall_case.recall_id | matches ^REC-2026-\d{6}$; must exist in recall_case.recall_id | Recall this action belongs to. |
| action_type | text | required |  | NOTIFY, QUARANTINE, RECOVER, DISPOSE |  |  |  | What was done. |
| target_type | text | required |  | RAW_LOT, FINISHED_LOT, DELIVERY |  |  |  | What kind of thing it was done to. |
| target_id | text | required |  |  |  |  | must exist in table named by target_type (validator) | Id of that thing. |
| customer_id | text | optional |  |  |  | FK -> customer.customer_id | matches ^C\d{5}$; must exist in customer.customer_id | Customer notified or recovered from. |
| qty_affected | decimal | required | kg or pack |  |  |  | >= 0 | Quantity in scope (kg for RAW_LOT, packs otherwise). |
| qty_recovered | decimal | optional |  |  |  |  | >= 0; <= qty_affected | Quantity physically recovered, RECOVER only. |
| disposition | text | required |  | PENDING, QUARANTINED, RETURNED, DESTROYED, REWORKED |  |  |  | Outcome of the stock. |
| action_ts | timestamp (ISO) | required |  |  |  |  | >= recall_case.opened_date | When the action happened. |

