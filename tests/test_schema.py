import re
import sqlite3

import pytest

from recallsim.ddl import build_ddl
from recallsim.dictionary import build_markdown
from recallsim.schema import ID_PATTERNS, TABLE_BY_NAME, TABLES


@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(build_ddl())
    yield conn
    conn.close()


def test_all_tables_created(db):
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert names == {t.name for t in TABLES}
    assert len(TABLES) == 12  # 11 required entities + wo_input_lot bridge


def test_pk_columns_exist_and_are_required():
    for t in TABLES:
        cols = {c.name: c for c in t.cols}
        for k in t.pk:
            assert k in cols and cols[k].required, (t.name, k)


def test_foreign_keys_point_to_real_columns_and_parents_come_first():
    order = {t.name: i for i, t in enumerate(TABLES)}
    for t in TABLES:
        for c in t.cols:
            if c.fk:
                parent, pcol = c.fk
                assert parent in TABLE_BY_NAME, (t.name, c.name)
                assert pcol in {x.name for x in TABLE_BY_NAME[parent].cols}
                assert order[parent] < order[t.name], f"{parent} must precede {t.name}"


def test_every_key_column_has_id_pattern():
    for t in TABLES:
        for c in t.cols:
            if c.name in ID_PATTERNS:
                assert c.rule and ID_PATTERNS[c.name] in c.rule


def test_fk_integrity_enforced(db):
    db.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO material_lot (raw_lot_id, supplier_id, material_code, qty_received, "
            "received_date, expiry_date) VALUES "
            "('RAWLOT-S0001-2026-000001','S9999','COCOA',10,'2026-01-01','2026-12-01')"
        )


def test_enum_check_rejects_bad_value(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO supplier VALUES ('S0001','Acme','IN','Z','ACTIVE','2025-01-01')"
        )


def test_bad_date_rejected(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO supplier VALUES ('S0001','Acme','IN','A','ACTIVE','not-a-date')"
        )


def test_negative_quantity_rejected(db):
    db.execute("INSERT INTO supplier VALUES ('S0001','Acme','IN','A','ACTIVE','2025-01-01')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO material_lot VALUES "
            "('RAWLOT-S0001-2026-000001','S0001','COCOA',-5,'2026-01-01','2026-12-01')"
        )


def test_optional_column_may_be_null(db):
    db.execute("INSERT INTO supplier VALUES ('S0001','Acme','IN','A','ACTIVE','2025-01-01')")
    db.execute("INSERT INTO product VALUES ('P001','Choco','BISCUIT',0.2,180,'ACTIVE')")
    db.execute("INSERT INTO bom_line VALUES ('BOM-000001','P001','COCOA',0.04,'2026-01-01',NULL)")


def test_dictionary_mentions_every_column():
    md = build_markdown()
    for t in TABLES:
        assert f"## {t.name}" in md
        for c in t.cols:
            assert re.search(rf"^\| {c.name} \|", md, re.M), (t.name, c.name)
