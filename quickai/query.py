from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .indexer import ensure_schema


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    ensure_schema(con)
    return con


def stats(db_path: Path, project: str | None = None) -> dict[str, Any]:
    with connect(db_path) as con:
        where, params = project_filter(project)
        row = con.execute(
            f"""
            SELECT
              COUNT(*) AS sessions,
              COALESCE(COUNT(DISTINCT project), 0) AS projects,
              COALESCE(SUM(turn_count), 0) AS turns,
              COALESCE(SUM(tool_call_count), 0) AS tool_calls,
              COALESCE(SUM(input_tokens), 0) AS input_tokens,
              COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
              COALESCE(SUM(output_tokens), 0) AS output_tokens,
              COALESCE(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
              COALESCE(SUM(total_tokens), 0) AS total_tokens,
              COALESCE(SUM(wall_ms), 0) AS wall_ms,
              MAX(primary_used_percent) AS primary_used_percent,
              MAX(secondary_used_percent) AS secondary_used_percent
            FROM sessions
            {where}
            """,
            params,
        ).fetchone()
        return dict(row)


def list_sessions(
    db_path: Path,
    *,
    project: str | None = None,
    by: str = "tokens",
    limit: int = 20,
) -> list[dict[str, Any]]:
    order_by = {
        "tokens": "total_tokens",
        "time": "wall_ms",
        "tools": "tool_call_count",
        "recent": "started_at",
    }.get(by, "total_tokens")
    with connect(db_path) as con:
        where, params = project_filter(project)
        rows = con.execute(
            f"""
            SELECT session_id, project, title, model, started_at, ended_at, wall_ms,
                   turn_count, tool_call_count, input_tokens, cached_input_tokens,
                   output_tokens, reasoning_output_tokens, total_tokens,
                   primary_used_percent, secondary_used_percent
            FROM sessions
            {where}
            ORDER BY {order_by} DESC, started_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def session_detail(db_path: Path, session_id: str) -> dict[str, Any] | None:
    with connect(db_path) as con:
        row = con.execute(
            """
            SELECT *
            FROM sessions
            WHERE session_id = ?
               OR session_id LIKE ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (session_id, f"{session_id}%"),
        ).fetchone()
        if not row:
            return None
        session = dict(row)
        session["turns"] = [
            dict(turn)
            for turn in con.execute(
                """
                SELECT ts, model, input_tokens, cached_input_tokens, output_tokens,
                       reasoning_output_tokens, total_tokens, context_window,
                       primary_used_percent, secondary_used_percent
                FROM turns
                WHERE session_id = ?
                ORDER BY ts ASC, id ASC
                """,
                (session["session_id"],),
            ).fetchall()
        ]
        session["tools"] = [
            dict(tool)
            for tool in con.execute(
                """
                SELECT name, calls, errors
                FROM tools
                WHERE session_id = ?
                ORDER BY calls DESC, name ASC
                """,
                (session["session_id"],),
            ).fetchall()
        ]
        return session


def top(
    db_path: Path,
    *,
    group: str,
    by: str = "tokens",
    project: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    group_expr = {
        "project": "project",
        "model": "COALESCE(model, 'unknown')",
        "session": "session_id",
    }.get(group)
    if not group_expr:
        raise ValueError(f"unsupported group: {group}")
    metric = {
        "tokens": "SUM(total_tokens)",
        "time": "SUM(wall_ms)",
        "tools": "SUM(tool_call_count)",
    }.get(by, "SUM(total_tokens)")
    with connect(db_path) as con:
        where, params = project_filter(project)
        rows = con.execute(
            f"""
            SELECT {group_expr} AS name,
                   COUNT(*) AS sessions,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens,
                   COALESCE(SUM(wall_ms), 0) AS wall_ms,
                   COALESCE(SUM(tool_call_count), 0) AS tool_calls
            FROM sessions
            {where}
            GROUP BY {group_expr}
            ORDER BY {metric} DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def tools(db_path: Path, *, project: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    with connect(db_path) as con:
        where = ""
        params: tuple[Any, ...] = ()
        if project:
            where = "WHERE s.project = ?"
            params = (project,)
        rows = con.execute(
            f"""
            SELECT t.name,
                   COALESCE(SUM(t.calls), 0) AS calls,
                   COALESCE(SUM(t.errors), 0) AS errors,
                   COUNT(DISTINCT t.session_id) AS sessions
            FROM tools t
            JOIN sessions s ON s.session_id = t.session_id
            {where}
            GROUP BY t.name
            ORDER BY calls DESC, errors DESC, t.name ASC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def projects(db_path: Path, limit: int = 50) -> list[dict[str, Any]]:
    return top(db_path, group="project", limit=limit)


def models(db_path: Path, limit: int = 50) -> list[dict[str, Any]]:
    return top(db_path, group="model", limit=limit)


def project_filter(project: str | None) -> tuple[str, tuple[Any, ...]]:
    if not project:
        return "", ()
    return "WHERE project = ?", (project,)
