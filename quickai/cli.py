from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .indexer import DEFAULT_DB_PATH, IndexOptions, index_codex_logs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quickai",
        description="Profile local Codex sessions from ~/.codex JSONL logs.",
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite DB path (default: {DEFAULT_DB_PATH})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Build or refresh the Codex usage index")
    index_parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Codex log root or JSONL file. Can be passed more than once.",
    )
    index_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete and rebuild the derived SQLite index.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "index":
        options = IndexOptions(
            db_path=Path(args.db).expanduser(),
            roots=[Path(root).expanduser() for root in args.root],
            rebuild=args.rebuild,
        )
        result = index_codex_logs(options)
        print(
            "quickai index: "
            f"{result.indexed} indexed, {result.skipped} skipped, "
            f"{result.failed} failed, {result.sessions} sessions"
        )
        if result.errors:
            for path, error in result.errors[:5]:
                print(f"error: {path}: {error}")
        return 1 if result.failed else 0

    parser.error(f"unknown command: {args.command}")
    return 2
