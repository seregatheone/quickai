## Why

Codex writes local JSONL session logs with token-count events, but there is no quick way to see where Codex tokens, time, tools, and rate-limit pressure went across projects and sessions.

This change builds a quickai-style local profiler for Codex: zero telemetry, no provider proxy, and reports generated from files already present under `~/.codex`.

## What Changes

- Add a standalone `quickai` Python CLI for indexing Codex sessions into SQLite.
- Add summary, task/session, top, tools, HTML report, and MCP stdio commands.
- Parse `~/.codex/sessions/**/rollout-*.jsonl` and `~/.codex/archived_sessions/rollout-*.jsonl`.
- Store only derived profiling data by default: truncated title, cwd/project, model, timing, token deltas, tool counts, and rate-limit snapshots.
- Add docs, architecture notes, tests, and sample fixture coverage.

## Capabilities

### New Capabilities

- `codex-session-profiling`: Index Codex JSONL sessions and query local usage/time/tool metrics.
- `codex-html-reporting`: Generate a self-contained HTML report over indexed Codex data.
- `codex-mcp-access`: Expose profiler summaries through a minimal MCP-compatible stdio server.

### Modified Capabilities

- None.

## Impact

- New Python package under `quickai/`.
- New SQLite schema generated at `~/.codex/quickai.db` unless overridden.
- New CLI entry point via `python -m quickai` and editable package install.
- No external runtime dependencies beyond Python 3.10+ standard library.
