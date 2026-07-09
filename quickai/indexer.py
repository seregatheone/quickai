from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)

DEFAULT_DB_PATH = Path.home() / ".codex" / "quickai.db"
DEFAULT_ROOTS = (
    Path.home() / ".codex" / "sessions",
    Path.home() / ".codex" / "archived_sessions",
)
SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class IndexOptions:
    db_path: Path = DEFAULT_DB_PATH
    roots: list[Path] = field(default_factory=list)
    rebuild: bool = False


@dataclass
class TurnUsage:
    session_id: str
    ts: str | None
    model: str | None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0
    context_window: int | None = None
    primary_used_percent: float | None = None
    secondary_used_percent: float | None = None


@dataclass
class ParsedSession:
    session_id: str
    path: Path
    source: str = "codex"
    cwd: str | None = None
    project: str = "unknown"
    title: str | None = None
    model: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    wall_ms: int | None = None
    turns: list[TurnUsage] = field(default_factory=list)
    tools: dict[str, dict[str, int]] = field(default_factory=dict)
    context_window: int | None = None
    primary_used_percent: float | None = None
    secondary_used_percent: float | None = None

    @property
    def totals(self) -> dict[str, int]:
        values = dict.fromkeys(USAGE_FIELDS, 0)
        for turn in self.turns:
            values["input_tokens"] += turn.input_tokens
            values["cached_input_tokens"] += turn.cached_input_tokens
            values["output_tokens"] += turn.output_tokens
            values["reasoning_output_tokens"] += turn.reasoning_output_tokens
            values["total_tokens"] += turn.total_tokens
        return values


@dataclass
class IndexResult:
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    sessions: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def index_codex_logs(options: IndexOptions) -> IndexResult:
    db_path = options.db_path
    if options.rebuild and db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    paths = list(discover_jsonl(options.roots or list(DEFAULT_ROOTS)))
    result = IndexResult()

    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        ensure_schema(con)
        for path in paths:
            try:
                if is_unchanged(con, path):
                    result.skipped += 1
                    continue
                parsed = parse_session(path)
                upsert_session(con, parsed)
                result.indexed += 1
            except Exception as exc:  # keep indexing other local logs
                result.failed += 1
                result.errors.append((str(path), str(exc)))
        result.sessions = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    return result


def discover_jsonl(roots: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for root in roots:
        root = root.expanduser()
        candidates: Iterable[Path]
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = root.rglob("rollout-*.jsonl")
        else:
            continue
        for path in candidates:
            resolved = path.resolve()
            if resolved.suffix == ".jsonl" and resolved not in seen:
                seen.add(resolved)
                yield resolved


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS files (
          path TEXT PRIMARY KEY,
          size INTEGER NOT NULL,
          mtime_ns INTEGER NOT NULL,
          sha256 TEXT NOT NULL,
          indexed_at TEXT NOT NULL,
          session_id TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
          session_id TEXT PRIMARY KEY,
          path TEXT NOT NULL UNIQUE,
          source TEXT NOT NULL,
          project TEXT NOT NULL,
          cwd TEXT,
          title TEXT,
          model TEXT,
          started_at TEXT,
          ended_at TEXT,
          wall_ms INTEGER,
          turn_count INTEGER NOT NULL,
          tool_call_count INTEGER NOT NULL,
          input_tokens INTEGER NOT NULL,
          cached_input_tokens INTEGER NOT NULL,
          output_tokens INTEGER NOT NULL,
          reasoning_output_tokens INTEGER NOT NULL,
          total_tokens INTEGER NOT NULL,
          context_window INTEGER,
          primary_used_percent REAL,
          secondary_used_percent REAL
        );

        CREATE TABLE IF NOT EXISTS turns (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT NOT NULL,
          ts TEXT,
          model TEXT,
          input_tokens INTEGER NOT NULL,
          cached_input_tokens INTEGER NOT NULL,
          output_tokens INTEGER NOT NULL,
          reasoning_output_tokens INTEGER NOT NULL,
          total_tokens INTEGER NOT NULL,
          context_window INTEGER,
          primary_used_percent REAL,
          secondary_used_percent REAL,
          FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tools (
          session_id TEXT NOT NULL,
          name TEXT NOT NULL,
          calls INTEGER NOT NULL,
          errors INTEGER NOT NULL,
          PRIMARY KEY(session_id, name),
          FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
        CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at);
        CREATE INDEX IF NOT EXISTS idx_turns_session_id ON turns(session_id);
        CREATE INDEX IF NOT EXISTS idx_tools_name ON tools(name);
        """
    )
    con.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
        (SCHEMA_VERSION,),
    )


def is_unchanged(con: sqlite3.Connection, path: Path) -> bool:
    stat = path.stat()
    row = con.execute(
        "SELECT size, mtime_ns FROM files WHERE path = ?",
        (str(path),),
    ).fetchone()
    return bool(row and row["size"] == stat.st_size and row["mtime_ns"] == stat.st_mtime_ns)


def parse_session(path: Path) -> ParsedSession:
    session = ParsedSession(session_id=path.stem, path=path)
    call_names: dict[str, str] = {}
    previous_total: dict[str, int] | None = None
    previous_signature: tuple[int, ...] | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            timestamp = normalize_ts(event.get("timestamp"))
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            event_type = event.get("type")
            payload_type = payload.get("type")

            if timestamp:
                session.started_at = min_ts(session.started_at, timestamp)
                session.ended_at = max_ts(session.ended_at, timestamp)

            if event_type == "session_meta":
                apply_session_meta(session, payload)
            elif event_type == "turn_context":
                apply_turn_context(session, payload)
            elif payload_type == "task_started":
                session.started_at = normalize_ts(payload.get("started_at")) or session.started_at
                session.context_window = int_or_none(payload.get("model_context_window")) or session.context_window
            elif payload_type == "task_complete":
                session.ended_at = normalize_ts(payload.get("completed_at")) or session.ended_at
                session.wall_ms = int_or_none(payload.get("duration_ms")) or session.wall_ms
            elif payload_type == "user_message" and not session.title:
                session.title = summarize_text(payload.get("message") or payload.get("text_elements"))
            elif event_type == "response_item" and payload_type in {"function_call", "custom_tool_call"}:
                name = str(payload.get("name") or "unknown")
                call_id = str(payload.get("call_id") or "")
                if call_id:
                    call_names[call_id] = name
                bump_tool(session, name, "calls")
            elif event_type == "response_item" and payload_type in {"function_call_output", "custom_tool_call_output"}:
                call_id = str(payload.get("call_id") or "")
                name = call_names.get(call_id)
                if name and output_is_error(payload.get("output")):
                    bump_tool(session, name, "errors")
            elif payload_type == "token_count":
                info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
                total = usage_dict(info.get("total_token_usage"))
                if not total:
                    continue
                signature = tuple(total[field] for field in USAGE_FIELDS)
                if signature == previous_signature:
                    update_rate_limit_snapshot(session, payload)
                    continue
                delta = usage_delta(previous_total, total, usage_dict(info.get("last_token_usage")))
                previous_total = total
                previous_signature = signature
                if not any(delta.values()):
                    update_rate_limit_snapshot(session, payload)
                    continue
                usage = TurnUsage(
                    session_id=session.session_id,
                    ts=timestamp,
                    model=session.model,
                    input_tokens=delta["input_tokens"],
                    cached_input_tokens=delta["cached_input_tokens"],
                    output_tokens=delta["output_tokens"],
                    reasoning_output_tokens=delta["reasoning_output_tokens"],
                    total_tokens=delta["total_tokens"],
                    context_window=int_or_none(info.get("model_context_window")) or session.context_window,
                )
                apply_rate_limits(usage, payload)
                session.turns.append(usage)
                session.context_window = usage.context_window or session.context_window
                session.primary_used_percent = usage.primary_used_percent
                session.secondary_used_percent = usage.secondary_used_percent

    if not session.title:
        session.title = path.stem
    if not session.project:
        session.project = project_from_cwd(session.cwd)
    if session.wall_ms is None:
        session.wall_ms = wall_ms(session.started_at, session.ended_at)
    return session


def apply_session_meta(session: ParsedSession, payload: dict[str, Any]) -> None:
    session.session_id = str(payload.get("id") or session.session_id)
    session.source = str(payload.get("source") or session.source or "codex")
    session.cwd = payload.get("cwd") or session.cwd
    session.project = project_from_cwd(session.cwd)
    if not session.model:
        provider = payload.get("model_provider")
        session.model = str(provider) if provider else session.model


def apply_turn_context(session: ParsedSession, payload: dict[str, Any]) -> None:
    session.cwd = payload.get("cwd") or session.cwd
    session.project = project_from_cwd(session.cwd)
    session.model = str(payload.get("model") or session.model or "")


def upsert_session(con: sqlite3.Connection, session: ParsedSession) -> None:
    stat = session.path.stat()
    digest = file_sha256(session.path)
    totals = session.totals
    tool_call_count = sum(item["calls"] for item in session.tools.values())

    with con:
        old = con.execute(
            "SELECT session_id FROM files WHERE path = ?",
            (str(session.path),),
        ).fetchone()
        if old:
            delete_session(con, old["session_id"])
        delete_session(con, session.session_id)

        con.execute(
            """
            INSERT INTO sessions (
              session_id, path, source, project, cwd, title, model, started_at, ended_at,
              wall_ms, turn_count, tool_call_count, input_tokens, cached_input_tokens,
              output_tokens, reasoning_output_tokens, total_tokens, context_window,
              primary_used_percent, secondary_used_percent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.session_id,
                str(session.path),
                session.source or "codex",
                session.project or "unknown",
                session.cwd,
                session.title,
                session.model,
                session.started_at,
                session.ended_at,
                session.wall_ms,
                len(session.turns),
                tool_call_count,
                totals["input_tokens"],
                totals["cached_input_tokens"],
                totals["output_tokens"],
                totals["reasoning_output_tokens"],
                totals["total_tokens"],
                session.context_window,
                session.primary_used_percent,
                session.secondary_used_percent,
            ),
        )
        con.executemany(
            """
            INSERT INTO turns (
              session_id, ts, model, input_tokens, cached_input_tokens, output_tokens,
              reasoning_output_tokens, total_tokens, context_window,
              primary_used_percent, secondary_used_percent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    turn.session_id,
                    turn.ts,
                    turn.model,
                    turn.input_tokens,
                    turn.cached_input_tokens,
                    turn.output_tokens,
                    turn.reasoning_output_tokens,
                    turn.total_tokens,
                    turn.context_window,
                    turn.primary_used_percent,
                    turn.secondary_used_percent,
                )
                for turn in session.turns
            ],
        )
        con.executemany(
            "INSERT INTO tools(session_id, name, calls, errors) VALUES (?, ?, ?, ?)",
            [
                (session.session_id, name, values["calls"], values["errors"])
                for name, values in sorted(session.tools.items())
            ],
        )
        con.execute(
            """
            INSERT INTO files(path, size, mtime_ns, sha256, indexed_at, session_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(session.path),
                stat.st_size,
                stat.st_mtime_ns,
                digest,
                datetime.now(timezone.utc).isoformat(),
                session.session_id,
            ),
        )


def delete_session(con: sqlite3.Connection, session_id: str) -> None:
    con.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
    con.execute("DELETE FROM tools WHERE session_id = ?", (session_id,))
    con.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    con.execute("DELETE FROM files WHERE session_id = ?", (session_id,))


def usage_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {field: int_or_none(value.get(field)) or 0 for field in USAGE_FIELDS}


def usage_delta(
    previous: dict[str, int] | None,
    total: dict[str, int],
    last: dict[str, int],
) -> dict[str, int]:
    if not previous:
        return last or total
    if total["total_tokens"] >= previous.get("total_tokens", 0):
        return {field: max(total[field] - previous.get(field, 0), 0) for field in USAGE_FIELDS}
    return last or total


def apply_rate_limits(turn: TurnUsage, payload: dict[str, Any]) -> None:
    limits = payload.get("rate_limits") if isinstance(payload.get("rate_limits"), dict) else {}
    turn.primary_used_percent = rate_percent(limits.get("primary"))
    turn.secondary_used_percent = rate_percent(limits.get("secondary"))


def update_rate_limit_snapshot(session: ParsedSession, payload: dict[str, Any]) -> None:
    limits = payload.get("rate_limits") if isinstance(payload.get("rate_limits"), dict) else {}
    session.primary_used_percent = rate_percent(limits.get("primary")) or session.primary_used_percent
    session.secondary_used_percent = rate_percent(limits.get("secondary")) or session.secondary_used_percent


def rate_percent(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("used_percent")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def bump_tool(session: ParsedSession, name: str, field_name: str) -> None:
    values = session.tools.setdefault(name, {"calls": 0, "errors": 0})
    values[field_name] += 1


def output_is_error(output: Any) -> bool:
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=True, default=str)
    lower = text.lower()
    return '"exit_code":1' in lower or '"exit_code": 1' in lower or "error" in lower


def summarize_text(value: Any, limit: int = 240) -> str:
    if isinstance(value, list):
        text = " ".join(str(item) for item in value)
    else:
        text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def project_from_cwd(cwd: str | None) -> str:
    if not cwd:
        return "unknown"
    name = Path(cwd).name
    return name or "unknown"


def min_ts(left: str | None, right: str) -> str:
    return right if left is None or right < left else left


def max_ts(left: str | None, right: str) -> str:
    return right if left is None or right > left else left


def wall_ms(started_at: str | None, ended_at: str | None) -> int | None:
    if not started_at or not ended_at:
        return None
    start = parse_ts(started_at)
    end = parse_ts(ended_at)
    if not start or not end:
        return None
    return max(int((end - start).total_seconds() * 1000), 0)


def normalize_ts(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if value > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        return value
    return None


def parse_ts(value: str) -> datetime | None:
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
