# codex-html-reporting Specification

## Purpose
TBD - created by archiving change build-codex-quickai-profiler. Update Purpose after archive.
## Requirements
### Requirement: Generate HTML Report

The app SHALL generate a self-contained HTML report from indexed Codex data.

#### Scenario: Report command

- **WHEN** the user runs `quickai report`
- **THEN** the app writes an HTML file
- **AND** prints the report path.

### Requirement: Include Key Profiling Views

The report SHALL include total sessions, tokens, wall time, projects, models, tools, slow sessions, and latest rate-limit pressure when available.

#### Scenario: Indexed database has data

- **WHEN** indexed sessions exist
- **THEN** the report includes summary cards and tables for projects, models, tools, and sessions.

