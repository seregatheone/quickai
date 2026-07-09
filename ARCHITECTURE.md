# Architecture

quickai for Codex is a local file-based profiler. It mirrors the useful shape of the upstream quickai project while using Codex's own rollout JSONL format.

## Source Data

Codex writes JSONL sessions under:

```text
~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
~/.codex/archived_sessions/rollout-*.jsonl
```

Relevant event types:

| Event | Use |
|---|---|
| `session_meta` | session id, cwd, source |
| `turn_context` | model, cwd, turn id |
| `event_msg/user_message` | truncated session title |
| `event_msg/token_count` | cumulative and last token usage, context window, rate limits |
| `response_item/function_call` | tool call count |
| `response_item/function_call_output` | best-effort tool error detection |
| `event_msg/task_started` / `task_complete` | timing |

Older logs can contain empty `token_count.info`; those events are skipped.

## Pipeline

```text
DISCOVER  ~/.codex rollout JSONL files
  -> PARSE line-by-line into session/tool/token events
  -> DELTA cumulative token totals, skipping repeated snapshots
  -> STORE derived rows in SQLite
  -> QUERY CLI, HTML report, MCP tools
```

## SQLite Cache

Default path: `~/.codex/quickai.db`.

Tables:

| Table | Purpose |
|---|---|
| `metadata` | schema version |
| `files` | path, size, mtime, sha, indexed session |
| `sessions` | per-rollout aggregate |
| `turns` | token delta rows |
| `tools` | per-session tool call/error counts |

The index is file-incremental: unchanged files are skipped; changed files are re-parsed transactionally.

## Task Boundary

Codex logs do not expose a Claude-style stable `promptId`, so v1 treats one rollout file as one task/session. Session prefix lookup is supported for `quickai task`.

## Reports

The HTML report is self-contained and generated from SQLite only. It includes:

- summary cards
- project/model breakdowns
- tool profile
- slow sessions
- top sessions
- latest observed rate-limit pressure

## MCP

`quickai mcp` is a stdio JSON-RPC server with Content-Length framing and JSON-line fallback for smoke tests. It exposes:

- `quickai_stats`
- `quickai_tasks`
- `quickai_report`

## Non-Goals

- No LLM proxy in v1.
- No exact bill calculation.
- No claim about subscription capacity.
- No mutation of Codex source logs.
