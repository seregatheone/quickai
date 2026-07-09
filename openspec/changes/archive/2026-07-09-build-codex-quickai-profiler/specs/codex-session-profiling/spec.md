## ADDED Requirements

### Requirement: Index Codex Session Logs

The app SHALL discover Codex JSONL session files from `~/.codex/sessions/**/rollout-*.jsonl` and `~/.codex/archived_sessions/rollout-*.jsonl` by default.

#### Scenario: Default indexing

- **WHEN** the user runs `quickai index`
- **THEN** the app creates or updates `~/.codex/quickai.db`
- **AND** stores one session row per parsed rollout file.

#### Scenario: Empty or old token-count event

- **WHEN** a `token_count` event has no `info.total_token_usage`
- **THEN** the app skips that usage event without failing the file.

### Requirement: Avoid Double Counting

The app SHALL derive token usage from monotonically increasing cumulative totals and skip repeated totals.

#### Scenario: Repeated rate-limit snapshot

- **WHEN** two adjacent `token_count` events have identical cumulative totals
- **THEN** only the first contributes token delta rows.

### Requirement: Preserve Local Privacy

The app SHALL keep source logs untouched and SHALL store only derived profiling fields plus a truncated session title.

#### Scenario: Rebuild

- **WHEN** the user runs `quickai index --rebuild`
- **THEN** the app replaces its derived SQLite cache
- **AND** does not modify Codex JSONL source files.
