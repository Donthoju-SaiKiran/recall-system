"""Command line entry: python -m recallsim docs"""
from __future__ import annotations

import argparse
from pathlib import Path

from .config import SCALES, SEED
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
    gen = sub.add_parser("generate", help="generate the dataset into a folder")
    gen.add_argument("--seed", type=int, default=SEED)
    gen.add_argument("--scale", default="full", choices=sorted(SCALES))
    gen.add_argument("--out", default="out")
    ver = sub.add_parser("verify", help="generate twice in separate processes and compare checksums")
    ver.add_argument("--seed", type=int, default=SEED)
    ver.add_argument("--scale", default="full", choices=sorted(SCALES))
    args = parser.parse_args()
    if args.command == "docs":
        write_docs(Path(args.root))
        print("wrote sql/schema.sql and docs/DATA_DICTIONARY.md")
    elif args.command == "generate":
        from .export import generate
        cmd = f"python -m recallsim generate --seed {args.seed} --scale {args.scale} --out <output-dir>"
        m = generate(args.scale, args.seed, Path(args.out), cmd)
        print(f"wrote {len(m['files'])} files to {args.out}, scale={args.scale}, seed={args.seed}")
    elif args.command == "verify":
        from .export import verify
        r = verify(args.scale, args.seed)
        print(f"files compared: {r['files']}, tree sha256: {r['tree_sha256']}")
        print("REPRODUCIBLE: PASS" if r["identical"] else f"REPRODUCIBLE: FAIL {r['differences']}")
        raise SystemExit(0 if r["identical"] else 1)


if __name__ == "__main__":
    main()
