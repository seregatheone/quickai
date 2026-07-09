from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .indexer import DEFAULT_DB_PATH, IndexOptions, index_codex_logs
from . import query
from .report import write_html_report


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

    stats_parser = subparsers.add_parser("stats", help="Show aggregate Codex usage")
    stats_parser.add_argument("--project", help="Filter by project name")

    tasks_parser = subparsers.add_parser("tasks", help="List Codex sessions/tasks")
    tasks_parser.add_argument("--project", help="Filter by project name")
    tasks_parser.add_argument("--by", choices=["tokens", "time", "tools", "recent"], default="tokens")
    tasks_parser.add_argument("--limit", type=int, default=20)

    task_parser = subparsers.add_parser("task", help="Show one session/task")
    task_parser.add_argument("session_id", help="Full session id or prefix")

    top_parser = subparsers.add_parser("top", help="Show top consumers")
    top_parser.add_argument("--group", choices=["project", "model", "session"], default="project")
    top_parser.add_argument("--by", choices=["tokens", "time", "tools"], default="tokens")
    top_parser.add_argument("--project", help="Filter by project name")
    top_parser.add_argument("--limit", type=int, default=20)

    tools_parser = subparsers.add_parser("tools", help="Show tool usage")
    tools_parser.add_argument("--project", help="Filter by project name")
    tools_parser.add_argument("--limit", type=int, default=30)

    report_parser = subparsers.add_parser("report", help="Generate a self-contained HTML report")
    report_parser.add_argument("--project", help="Filter by project name")
    report_parser.add_argument("--output", help="Output HTML path")

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

    db_path = Path(args.db).expanduser()

    if args.command == "stats":
        print_stats(query.stats(db_path, project=args.project))
        return 0

    if args.command == "tasks":
        rows = query.list_sessions(db_path, project=args.project, by=args.by, limit=args.limit)
        print_table(rows, ["session_id", "project", "total_tokens", "wall_ms", "tool_call_count", "title"])
        return 0

    if args.command == "task":
        session = query.session_detail(db_path, args.session_id)
        if not session:
            print(f"task not found: {args.session_id}")
            return 1
        print_task(session)
        return 0

    if args.command == "top":
        rows = query.top(db_path, group=args.group, by=args.by, project=args.project, limit=args.limit)
        print_table(rows, ["name", "sessions", "total_tokens", "wall_ms", "tool_calls"])
        return 0

    if args.command == "tools":
        rows = query.tools(db_path, project=args.project, limit=args.limit)
        print_table(rows, ["name", "calls", "errors", "sessions"])
        return 0

    if args.command == "report":
        output = Path(args.output).expanduser() if args.output else None
        path = write_html_report(db_path, output=output, project=args.project)
        print(path)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def print_stats(values: dict[str, object]) -> None:
    if not values.get("sessions"):
        print("quickai — no indexed Codex sessions. Run `quickai index` first.")
        return
    print("quickai — Codex index summary")
    print(f"  projects:   {values['projects']}")
    print(f"  sessions:   {values['sessions']}")
    print(f"  turns:      {values['turns']}")
    print(f"  tool calls: {values['tool_calls']}")
    print("  -- tokens --")
    print(f"  total:      {fmt_int(values['total_tokens'])}")
    print(f"    input:    {fmt_int(values['input_tokens'])}")
    print(f"    cache:    {fmt_int(values['cached_input_tokens'])}")
    print(f"    output:   {fmt_int(values['output_tokens'])}")
    print(f"    reasoning:{fmt_int(values['reasoning_output_tokens'])}")
    print(f"  wall time:  {fmt_duration(values['wall_ms'])}")
    rate = rate_text(values)
    if rate:
        print(f"  rate limit: {rate}")


def print_task(session: dict[str, object]) -> None:
    print(f"task {session['session_id']}")
    print(f"  project: {session['project']}")
    print(f"  title:   {session.get('title') or ''}")
    print(f"  model:   {session.get('model') or 'unknown'}")
    print(f"  tokens:  {fmt_int(session['total_tokens'])}")
    print(f"  time:    {fmt_duration(session.get('wall_ms'))}")
    print(f"  tools:   {session.get('tool_call_count', 0)}")
    if session.get("tools"):
        print("  -- tools --")
        for tool in session["tools"]:
            print(f"  {tool['name']}: {tool['calls']} calls, {tool['errors']} errors")


def print_table(rows: list[dict[str, object]], columns: list[str]) -> None:
    if not rows:
        print("No data.")
        return
    widths = {
        column: max(len(label(column)), *(len(format_value(column, row.get(column))) for row in rows))
        for column in columns
    }
    print("  ".join(label(column).ljust(widths[column]) for column in columns))
    print("  ".join("-" * widths[column] for column in columns))
    for row in rows:
        print("  ".join(format_value(column, row.get(column)).ljust(widths[column]) for column in columns))


def label(column: str) -> str:
    return column.replace("_", " ")


def format_value(column: str, value: object) -> str:
    if value is None:
        return ""
    if column.endswith("tokens"):
        return fmt_int(value)
    if column == "wall_ms":
        return fmt_duration(value)
    text = str(value).replace("\n", " ")
    return text if len(text) <= 72 else text[:69].rstrip() + "..."


def fmt_int(value: object) -> str:
    return f"{int(value or 0):,}"


def fmt_duration(value: object) -> str:
    seconds = int((value or 0) / 1000)
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def rate_text(values: dict[str, object]) -> str:
    parts = []
    if values.get("primary_used_percent") is not None:
        parts.append(f"primary {values['primary_used_percent']:g}%")
    if values.get("secondary_used_percent") is not None:
        parts.append(f"secondary {values['secondary_used_percent']:g}%")
    return ", ".join(parts)
