# codex-mcp-access Specification

## Purpose
TBD - created by archiving change build-codex-quickai-profiler. Update Purpose after archive.
## Requirements
### Requirement: Expose MCP Stdio Server

The app SHALL provide `quickai mcp` for JSON-RPC stdio access to profiler queries.

#### Scenario: List tools

- **WHEN** an MCP client sends `tools/list`
- **THEN** the server returns tools for stats, tasks, and report generation.

#### Scenario: Call stats tool

- **WHEN** an MCP client calls `quickai_stats`
- **THEN** the server returns the same aggregate data used by the CLI stats command.

