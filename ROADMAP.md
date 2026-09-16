# Roadmap / Issue Backlog

Date: 2026-09-14

## Active Next: Dogfooding & Workflow Validation

- [ ] **Deferred TUI UX Design:**
  - Implement provider-aware internal Markdown links for in-TUI issue navigation.
  - Decide between a compact issue-context action bar and an action modal without duplicating global shortcuts.
  - Design multi-selection and confirmation semantics for batch assignment and batch transitions.
  - Complete parent/child drill-up and drill-down navigation across Jira, GitHub, and GitLab.
  - Add a provider-neutral `New child` workflow: use the selected issue as parent, create the child with the provider-specific type/repository, then link it. Jira needs Epic -> Story or Story -> Sub-task semantics; GitHub uses issue creation followed by the Sub-Issues add operation.

- [ ] **Roadmap Transfer & Dogfooding:**
  - Transfer this roadmap into GitHub Issues within `colenio/jira-cli` / `colenio/21` using CLI/TUI.
  - Use `colenio/21` Project Board as the primary real-world testbed for daily transition and assignment workflows.
- [ ] **GitHub Issue Creation & Write Expansion:**
  - Implement `create_issue` for GitHub provider via CLI/TUI.
  - Map parent/child sub-issue relationships for GitHub issues. GitHub REST exposes parent, list, add, remove, and reprioritize sub-issue endpoints.
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
