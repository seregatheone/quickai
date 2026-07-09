# quickai for Codex

Local profiler for Codex sessions. It shows where Codex tokens, time, tool calls, and rate-limit pressure went per project and session, using the JSONL logs Codex already writes to disk.

Inspired by [AlexGladkov/quickai](https://github.com/AlexGladkov/quickai), but this implementation targets Codex logs directly and stays dependency-free.

## Install

Requires Python 3.10+.

```sh
python -m pip install -e .
```

You can also run without installing:

```sh
python -m quickai --help
```

## First Run

Build the local derived index:

```sh
quickai index
```

By default quickai reads:

- `~/.codex/sessions/**/rollout-*.jsonl`
- `~/.codex/archived_sessions/rollout-*.jsonl`

The SQLite cache is written to `~/.codex/quickai.db`. It is derived data; delete it any time and rebuild.

## Examples

```sh
quickai stats
quickai tasks --by tokens --limit 20
quickai top --group project
quickai top --group model
quickai tools
quickai task rollout-2026-07
quickai report
quickai report --project my-app --output /tmp/quickai.html
```

Fixture smoke check:

```sh
python -m quickai --db /tmp/quickai.db index --root tests/fixtures/codex
python -m quickai --db /tmp/quickai.db stats
python -m quickai --db /tmp/quickai.db report --output /tmp/quickai.html
```

## MCP

Run a stdio JSON-RPC server:

```sh
quickai mcp
```

Tools:

- `quickai_stats`
- `quickai_tasks`
- `quickai_report`

## Privacy

- Source Codex JSONL files are never modified.
- The database stores derived profiling data plus a truncated title.
- No telemetry or network calls are used by the app.
- Token totals are usage/volume signals, not a bill or subscription-capacity percentage.

## Commands

| Command | What it shows |
|---|---|
| `quickai index [--rebuild] [--root PATH]` | Build or refresh the local index |
| `quickai stats [--project X]` | Summary: sessions, projects, tokens, time, tools |
| `quickai tasks [--by tokens\|time\|tools\|recent]` | Top sessions/tasks |
| `quickai task <sessionIdPrefix>` | One session with tools |
| `quickai top --group project\|model\|session` | Top consumers |
| `quickai tools` | Tool calls and detected errors |
| `quickai report [--output file.html]` | Self-contained HTML report |
| `quickai mcp` | MCP-compatible stdio server |

## Development

```sh
python -m unittest discover
openspec validate --specs
```
