## Context

The upstream quickai project profiles Claude Code from transcript files. Its open Codex-related issues show two useful constraints: Codex may not expose Claude-style per-turn transcript usage everywhere, and a live LLM proxy is a fallback with more operational risk. Current Codex Desktop/CLI logs do include `event_msg/token_count` events in local JSONL files, so a first useful Codex analog can stay file-based and local.

## Goals / Non-Goals

**Goals:**

- Build a working local CLI app that indexes Codex JSONL logs incrementally.
- Keep data local and derived from existing files.
- Make the first screen useful: stats, top projects/sessions, tool profile, rate-limit pressure, and HTML report.
- Provide a small MCP stdio facade for chat-driven queries.
- Keep the app dependency-free so it runs in this workspace without Cargo or package installs.

**Non-Goals:**

- No reverse proxy or provider base-url modification in v1.
- No exact billing claim; Codex subscription limits and provider prices are not treated as a bill.
- No parsing of private message bodies beyond a truncated user-facing title.
- No web dashboard server in v1.

## Decisions

1. **Python stdlib over Rust.** The source project is Rust, but this workspace does not have Cargo on PATH. Python 3.12 is available and can deliver a working app with `sqlite3`, `argparse`, and `html`.

2. **Cumulative token events become deltas.** Codex `token_count` events carry `total_token_usage` and `last_token_usage`. The indexer stores deltas from monotonically increasing totals and skips repeated totals, avoiding double-counting repeated rate-limit snapshots.

3. **Session is the task boundary.** Codex logs do not expose a stable Claude-style `promptId`. The app treats each rollout file/session as the primary task and derives title/project/model from session metadata and turn context.

4. **Incremental index is file-level.** The schema tracks path, size, mtime, and content hash. Changed files are re-indexed transactionally; unchanged files are skipped.

5. **MCP is minimal JSON-RPC.** `quickai mcp` exposes stats/tasks/report through stdio and reuses the same SQLite queries.

## Risks / Trade-offs

- **Codex log format drift** -> Parser is tolerant, ignores unknown events, and tests cover older empty `token_count.info`.
- **Large local logs** -> Parser streams line-by-line and stores aggregates plus token rows only.
- **Privacy** -> Database stores derived data and truncated titles; docs explain paths and deletion.
- **Cost accuracy** -> v1 reports tokens/time/rate limits, not subscription utilization or exact bills.

## Migration Plan

1. Ship CLI and docs.
2. Run `quickai index` to create `~/.codex/quickai.db`.
3. Regenerate by deleting the DB or running `quickai index --rebuild`.
4. Rollback is deleting the generated DB/report; source logs are untouched.

## Open Questions

- Should a later version add the upstream proxy fallback for agents without usable local `token_count` events?
- Should Codex subagent/tool call semantics become a separate task hierarchy when a stable identifier is available?
