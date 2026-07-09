## 1. Planning And Repository Setup

- [x] 1.1 Capture upstream README/issues/architecture findings in project docs.
- [x] 1.2 Create OpenSpec proposal, design, specs, and implementation task list.
- [x] 1.3 Connect the local repository to GitHub and enable issue tracking.

## 2. Core Indexer

- [x] 2.1 Create Python package and CLI entry point.
- [x] 2.2 Implement SQLite schema for files, sessions, turns, tools, and metadata.
- [x] 2.3 Implement tolerant Codex JSONL parsing with cumulative token delta handling.
- [x] 2.4 Implement incremental indexing and rebuild mode.

## 3. Query And Reports

- [x] 3.1 Implement stats, tasks/sessions, top, task, and tools CLI commands.
- [x] 3.2 Implement self-contained HTML report generation.
- [ ] 3.3 Implement minimal MCP stdio tools for stats, tasks, and report creation.

## 4. Documentation And Verification

- [ ] 4.1 Add README, architecture, and usage examples.
- [ ] 4.2 Add unit tests with Codex JSONL fixtures, including duplicate/empty token-count events.
- [ ] 4.3 Run local checks and validate OpenSpec artifacts.

## 5. Issue Workflow

- [x] 5.1 Create GitHub epics/tasks through issue-creator.
- [ ] 5.2 Execute ready issues through issue-manager.
- [ ] 5.3 Close or link completed issues and leave the repo in a working state.
