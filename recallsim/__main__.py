"""Command line entry: python -m recallsim docs"""
from __future__ import annotations

import argparse
from pathlib import Path

from .ddl import build_ddl
from .dictionary import build_markdown


def write_docs(root: Path) -> None:
    (root / "sql").mkdir(exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    (root / "sql" / "schema.sql").write_text(build_ddl() + "\n", encoding="utf-8")
    (root / "docs" / "DATA_DICTIONARY.md").write_text(build_markdown() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(prog="recallsim")
    sub = parser.add_subparsers(dest="command", required=True)
    docs = sub.add_parser("docs", help="regenerate sql/schema.sql and docs/DATA_DICTIONARY.md")
    docs.add_argument("--root", default=".", help="project root (default: current dir)")
    args = parser.parse_args()
    if args.command == "docs":
        write_docs(Path(args.root))
        print("wrote sql/schema.sql and docs/DATA_DICTIONARY.md")


if __name__ == "__main__":
    main()
