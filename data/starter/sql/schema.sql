-- Generated from recallsim/schema.py. Do not edit by hand.
PRAGMA foreign_keys = ON;

-- Company that sells raw materials.
CREATE TABLE supplier (
    supplier_id TEXT NOT NULL,
    supplier_name TEXT NOT NULL,
    country TEXT NOT NULL CHECK (country IN ('IN', 'US', 'DE', 'VN', 'BR', 'ID', 'NL', 'TR', 'GH', 'CI')),
    tier TEXT NOT NULL CHECK (tier IN ('A', 'B', 'C')),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'SUSPENDED', 'INACTIVE')),
    onboarded_date TEXT NOT NULL CHECK (date(onboarded_date) IS NOT NULL),
    PRIMARY KEY (supplier_id)
);

-- Shop, distributor or food-service buyer that receives goods.
CREATE TABLE customer (
    customer_id TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    customer_type TEXT NOT NULL CHECK (customer_type IN ('RETAILER', 'DISTRIBUTOR', 'FOODSERVICE')),
    region TEXT NOT NULL CHECK (region IN ('NORTH', 'SOUTH', 'EAST', 'WEST', 'CENTRAL')),
    contact_channel TEXT NOT NULL CHECK (contact_channel IN ('EMAIL', 'PHONE', 'PORTAL')),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE')),
    PRIMARY KEY (customer_id)
);

-- Finished product we sell.
CREATE TABLE product (
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('BISCUIT', 'CHOCOLATE', 'SNACK', 'BAKERY_MIX')),
    pack_size_kg REAL NOT NULL CHECK (pack_size_kg >= 0.01),
    shelf_life_days INTEGER NOT NULL CHECK (shelf_life_days >= 1),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'DISCONTINUED')),
    PRIMARY KEY (product_id)
);

-- Bill of Materials line: kg of one material per pack.
CREATE TABLE bom_line (
    bom_line_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    material_code TEXT NOT NULL CHECK (material_code IN ('FLOUR', 'SUGAR', 'COCOA', 'BUTTER', 'MILK_POWDER', 'EGG_POWDER', 'PEANUT', 'ALMOND', 'VANILLA', 'SALT', 'PALM_OIL', 'LECITHIN')),
    qty_per_pack REAL NOT NULL CHECK (qty_per_pack >= 0.0001),
    effective_from TEXT NOT NULL CHECK (date(effective_from) IS NOT NULL),
    effective_to TEXT CHECK (effective_to IS NULL OR date(effective_to) IS NOT NULL),
    PRIMARY KEY (bom_line_id),
    FOREIGN KEY (product_id) REFERENCES product(product_id)
);
CREATE INDEX idx_bom_line_product_id ON bom_line(product_id);

-- One received batch of a raw material.
CREATE TABLE material_lot (
    raw_lot_id TEXT NOT NULL,
    supplier_id TEXT NOT NULL,
    material_code TEXT NOT NULL CHECK (material_code IN ('FLOUR', 'SUGAR', 'COCOA', 'BUTTER', 'MILK_POWDER', 'EGG_POWDER', 'PEANUT', 'ALMOND', 'VANILLA', 'SALT', 'PALM_OIL', 'LECITHIN')),
    qty_received REAL NOT NULL CHECK (qty_received >= 0.001),
    received_date TEXT NOT NULL CHECK (date(received_date) IS NOT NULL),
    expiry_date TEXT NOT NULL CHECK (date(expiry_date) IS NOT NULL),
    PRIMARY KEY (raw_lot_id),
    FOREIGN KEY (supplier_id) REFERENCES supplier(supplier_id)
);
CREATE INDEX idx_material_lot_supplier_id ON material_lot(supplier_id);

-- A factory job that makes one product.
CREATE TABLE production_order (
    wo_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    planned_qty INTEGER NOT NULL CHECK (planned_qty >= 1),
    line_code TEXT NOT NULL,
    start_date TEXT NOT NULL CHECK (date(start_date) IS NOT NULL),
    end_date TEXT CHECK (end_date IS NULL OR date(end_date) IS NOT NULL),
    status TEXT NOT NULL CHECK (status IN ('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
    PRIMARY KEY (wo_id),
    FOREIGN KEY (product_id) REFERENCES product(product_id)
);
CREATE INDEX idx_production_order_product_id ON production_order(product_id);

-- Bridge: which raw lots a job consumed and how much.
CREATE TABLE wo_input_lot (
    wo_id TEXT NOT NULL,
    raw_lot_id TEXT NOT NULL,
    qty_consumed REAL NOT NULL CHECK (qty_consumed >= 0.001),
    consumed_date TEXT NOT NULL CHECK (date(consumed_date) IS NOT NULL),
    PRIMARY KEY (wo_id, raw_lot_id),
    FOREIGN KEY (wo_id) REFERENCES production_order(wo_id),
    FOREIGN KEY (raw_lot_id) REFERENCES material_lot(raw_lot_id)
);
CREATE INDEX idx_wo_input_lot_wo_id ON wo_input_lot(wo_id);
CREATE INDEX idx_wo_input_lot_raw_lot_id ON wo_input_lot(raw_lot_id);

-- Batch of packs produced by one job.
CREATE TABLE finished_lot (
    finished_lot_id TEXT NOT NULL,
    wo_id TEXT NOT NULL,
    qty_produced INTEGER NOT NULL CHECK (qty_produced >= 1),
    produced_date TEXT NOT NULL CHECK (date(produced_date) IS NOT NULL),
    expiry_date TEXT NOT NULL CHECK (date(expiry_date) IS NOT NULL),
    sale_status TEXT NOT NULL CHECK (sale_status IN ('AVAILABLE', 'RECALLED')),
    PRIMARY KEY (finished_lot_id),
    FOREIGN KEY (wo_id) REFERENCES production_order(wo_id)
);
CREATE INDEX idx_finished_lot_wo_id ON finished_lot(wo_id);

-- A truck leaving a warehouse.
CREATE TABLE shipment (
    shipment_id TEXT NOT NULL,
    warehouse_code TEXT NOT NULL,
    carrier_code TEXT NOT NULL,
    ship_date TEXT NOT NULL CHECK (date(ship_date) IS NOT NULL),
    status TEXT NOT NULL CHECK (status IN ('PLANNED', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED')),
    PRIMARY KEY (shipment_id)
);

-- Bridge: quantity of one finished lot dropped to one customer on one shipment.
CREATE TABLE delivery (
    delivery_id TEXT NOT NULL,
    shipment_id TEXT NOT NULL,
    finished_lot_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    qty_delivered INTEGER NOT NULL CHECK (qty_delivered >= 1),
    delivery_date TEXT NOT NULL CHECK (date(delivery_date) IS NOT NULL),
    status TEXT NOT NULL CHECK (status IN ('IN_TRANSIT', 'DELIVERED', 'FAILED')),
    PRIMARY KEY (delivery_id),
    FOREIGN KEY (shipment_id) REFERENCES shipment(shipment_id),
    FOREIGN KEY (finished_lot_id) REFERENCES finished_lot(finished_lot_id),
    FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
);
CREATE INDEX idx_delivery_shipment_id ON delivery(shipment_id);
CREATE INDEX idx_delivery_finished_lot_id ON delivery(finished_lot_id);
CREATE INDEX idx_delivery_customer_id ON delivery(customer_id);

-- One recall opened for one contaminated lot.
CREATE TABLE recall_case (
    recall_id TEXT NOT NULL,
    trigger_lot_type TEXT NOT NULL CHECK (trigger_lot_type IN ('RAW', 'FINISHED')),
    trigger_lot_id TEXT NOT NULL,
    reason_code TEXT NOT NULL CHECK (reason_code IN ('PATHOGEN', 'ALLERGEN_UNDECLARED', 'FOREIGN_MATTER', 'CHEMICAL')),
    severity TEXT NOT NULL CHECK (severity IN ('CLASS_I', 'CLASS_II', 'CLASS_III')),
    opened_date TEXT NOT NULL CHECK (date(opened_date) IS NOT NULL),
    closed_date TEXT CHECK (closed_date IS NULL OR date(closed_date) IS NOT NULL),
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'IN_PROGRESS', 'CLOSED')),
    PRIMARY KEY (recall_id)
);

-- Append-only event: one step taken during a recall.
CREATE TABLE recall_action (
    action_id TEXT NOT NULL,
    recall_id TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('NOTIFY', 'QUARANTINE', 'RECOVER', 'DISPOSE')),
    target_type TEXT NOT NULL CHECK (target_type IN ('RAW_LOT', 'FINISHED_LOT', 'DELIVERY')),
    target_id TEXT NOT NULL,
    customer_id TEXT,
    qty_affected REAL NOT NULL CHECK (qty_affected >= 0),
    qty_recovered REAL CHECK (qty_recovered IS NULL OR qty_recovered >= 0),
    disposition TEXT NOT NULL CHECK (disposition IN ('PENDING', 'QUARANTINED', 'RETURNED', 'DESTROYED', 'REWORKED')),
    action_ts TEXT NOT NULL CHECK (datetime(action_ts) IS NOT NULL),
    PRIMARY KEY (action_id),
    FOREIGN KEY (recall_id) REFERENCES recall_case(recall_id),
    FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
);
CREATE INDEX idx_recall_action_recall_id ON recall_action(recall_id);
CREATE INDEX idx_recall_action_customer_id ON recall_action(customer_id);

