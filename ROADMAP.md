# Roadmap / Issue Backlog

Date: 2026-09-14

## Active Next: Dogfooding & Workflow Validation

- [ ] **Roadmap Transfer & Dogfooding:**
  - Transfer this roadmap into GitHub Issues within `colenio/jira-cli` / `colenio/21` using CLI/TUI.
  - Use `colenio/21` Project Board as the primary real-world testbed for daily transition and assignment workflows.
- [ ] **GitHub Issue Creation & Write Expansion:**
  - Implement `create_issue` for GitHub provider via CLI/TUI.
  - Map parent/child sub-issue relationships for GitHub issues.
- [ ] **GitLab Provider Adapter:**
  - Design GitLab provider adapter supporting GitLab Issues, Epics, Weights, and Scoped Labels.
- [ ] **Project Name & Re-branding (Rule of Three):**
  - Rename project (e.g. `jira-cli` ➔ `tracker-cli` / `task-cli`) once 3 providers exist (Jira + GitHub + GitLab) and dogfooding is complete.

## Backlog / Enhancements

### 1) Project Capability Detection Layer

- Helper to detect project capabilities before write operations (fixVersions, Epic link style, issue types).

### 2) Search API Compatibility Wrapper

- Fallbacks for Jira Cloud/API drift with POST search and 410/404/405 translation.

### 3) Version (Fix Version) Upsert

- Idempotent create/update version helper (lookup by name, due date, description).

### 4) Field-Safe Issue Update

- Fetch editmeta and update only fields configured in project context.

### 5) Label Harmonization Strategy

- Optional `--label-mode` (`merge` vs `replace`) and label alias mapping file.

### 6) Token Metadata Display

- Display API token expiration metadata and early warnings in TUI status bar.
