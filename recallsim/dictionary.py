"""Turn schema.py into docs/DATA_DICTIONARY.md."""
from __future__ import annotations

from .schema import ID_PATTERNS, TABLES, Col

TYPE_LABEL = {"TEXT": "text", "DATE": "date (ISO)", "TIMESTAMP": "timestamp (ISO)",
              "INTEGER": "integer", "REAL": "decimal"}


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _row(table_pk: tuple, col: Col) -> str:
    allowed = ", ".join(col.allowed) if col.allowed else ""
    is_pk = col.name in table_pk
    flags = []
    if is_pk:
        flags.append("PK")
    if col.fk:
        flags.append(f"FK -> {col.fk[0]}.{col.fk[1]}")
    unique = "yes" if (col.unique or (is_pk and len(table_pk) == 1)) else ""
    rule_parts = []
    if col.minimum is not None:
        rule_parts.append(f">= {col.minimum:g}")
    if col.rule:
        rule_parts.append(col.rule)
    return "| " + " | ".join(_cell(x) for x in (
        col.name,
        TYPE_LABEL[col.type],
        "required" if col.required else "optional",
        col.unit or "",
        allowed,
        unique,
        "; ".join(flags),
        "; ".join(rule_parts),
        col.desc,
    )) + " |"


def build_markdown() -> str:
    out = [
        "# Data dictionary",
        "",
        "Generated from `recallsim/schema.py`. Do not edit by hand.",
        "",
        "## ID conventions",
        "",
        "| Field | Pattern |",
        "|---|---|",
    ]
    out += [f"| {k} | `{v}` |" for k, v in ID_PATTERNS.items()]
    out += [
        "",
        "Counters are zero padded, IDs are immutable, and every referenced ID is copied "
        "exactly from its parent.",
        "",
        "## Units",
        "",
        "Raw material quantities are in kg. Finished goods quantities are in packs. "
        "Dates are ISO text (YYYY-MM-DD), timestamps are ISO text.",
        "",
    ]
    for table in TABLES:
        out += [
            f"## {table.name}",
            "",
            table.desc,
            "",
            f"- Primary key: `{', '.join(table.pk)}`",
            f"- Cardinality: {table.cardinality}",
            f"- Lifecycle: {table.lifecycle}",
            "",
            "| Field | Type | Required | Unit | Allowed values | Unique | Key | Rule | Description |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        out += [_row(table.pk, c) for c in table.cols]
        out.append("")
    return "\n".join(out)
