from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from . import __version__, query
from .report import write_html_report


TOOLS = [
    {
        "name": "quickai_stats",
        "description": "Return aggregate Codex profiler stats.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "quickai_tasks",
        "description": "Return top Codex sessions/tasks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "by": {"type": "string", "enum": ["tokens", "time", "tools", "recent"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "quickai_report",
        "description": "Generate a self-contained HTML Codex profiler report.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "output": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
]


def run_stdio_server(db_path: Path, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout

    while True:
        message = read_message(stdin)
        if message is None:
            break
        response = handle_message(message, db_path)
        if response is not None:
            write_message(stdout, response)
    return 0


def handle_message(message: dict[str, Any], db_path: Path) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "quickai-codex", "version": __version__},
            }
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = call_tool(db_path, params)
        elif method == "shutdown":
            result = None
        else:
            return error_response(request_id, -32601, f"method not found: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return error_response(request_id, -32603, str(exc))


def call_tool(db_path: Path, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}

    if name == "quickai_stats":
        payload = query.stats(db_path, project=args.get("project"))
    elif name == "quickai_tasks":
        payload = query.list_sessions(
            db_path,
            project=args.get("project"),
            by=str(args.get("by") or "tokens"),
            limit=int(args.get("limit") or 20),
        )
    elif name == "quickai_report":
        output = Path(args["output"]).expanduser() if args.get("output") else None
        path = write_html_report(db_path, output=output, project=args.get("project"))
        payload = {"path": str(path)}
    else:
        raise ValueError(f"unknown tool: {name}")

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ]
    }


def read_message(stdin: TextIO) -> dict[str, Any] | None:
    first = stdin.readline()
    if not first:
        return None
    first = first.rstrip("\r\n")

    if first.lower().startswith("content-length:"):
        length = int(first.split(":", 1)[1].strip())
        while True:
            line = stdin.readline()
            if line in {"\r\n", "\n", ""}:
                break
        body = stdin.read(length)
        if not body:
            return None
        return json.loads(body)

    return json.loads(first)


def write_message(stdout: TextIO, message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    encoded = body.encode("utf-8")
    stdout.write(f"Content-Length: {len(encoded)}\r\n\r\n{body}")
    stdout.flush()


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
