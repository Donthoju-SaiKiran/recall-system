"""Turn schema.py into SQLite DDL."""
from __future__ import annotations

from .schema import TABLES, Col, Table

SQL_TYPE = {"TEXT": "TEXT", "DATE": "TEXT", "TIMESTAMP": "TEXT",
            "INTEGER": "INTEGER", "REAL": "REAL"}


def _quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _column_sql(table: Table, col: Col) -> list[str]:
    parts = [f"{col.name} {SQL_TYPE[col.type]}"]
    if col.required:
        parts[0] += " NOT NULL"
    if col.unique and table.pk != (col.name,):
        parts[0] += " UNIQUE"
    checks = []
    if col.allowed:
        checks.append(f"{col.name} IN ({', '.join(_quote(v) for v in col.allowed)})")
    if col.minimum is not None:
        checks.append(f"{col.name} >= {col.minimum}")
    if col.type == "DATE":
        checks.append(f"date({col.name}) IS NOT NULL")
    if col.type == "TIMESTAMP":
        checks.append(f"datetime({col.name}) IS NOT NULL")
    out = []
    for check in checks:
        # optional columns may be NULL, so the check only applies when a value exists
        guard = "" if col.required else f"{col.name} IS NULL OR "
        out.append(f"CHECK ({guard}{check})")
    return [parts[0], *out]


def table_ddl(table: Table) -> str:
    lines: list[str] = []
    for col in table.cols:
        sql = _column_sql(table, col)
        lines.append("    " + " ".join(sql))
    lines.append(f"    PRIMARY KEY ({', '.join(table.pk)})")
    for col in table.cols:
        if col.fk:
            ref_table, ref_col = col.fk
            lines.append(f"    FOREIGN KEY ({col.name}) REFERENCES {ref_table}({ref_col})")
    body = ",\n".join(lines)
    return f"CREATE TABLE {table.name} (\n{body}\n);"


def index_ddl(table: Table) -> list[str]:
    """Index every foreign key column so downstream traversal stays fast."""
    return [
        f"CREATE INDEX idx_{table.name}_{col.name} ON {table.name}({col.name});"
        for col in table.cols
        if col.fk and table.pk != (col.name,)
    ]


def build_ddl() -> str:
    blocks = ["-- Generated from recallsim/schema.py. Do not edit by hand.",
              "PRAGMA foreign_keys = ON;", ""]
    for table in TABLES:
        blocks.append(f"-- {table.desc}")
        blocks.append(table_ddl(table))
        blocks.extend(index_ddl(table))
        blocks.append("")
    return "\n".join(blocks)
