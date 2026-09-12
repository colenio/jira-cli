# Roadmap / Issue Backlog

Date: 2026-07-01

## 1) Project Capability Detection Layer

- Add helper to detect project capabilities before write operations:
  - fixVersions available?
  - Epic link style (parent vs customfield)
  - issue type availability (Epic/Story/Sub-task)
- Expose result as reusable capability object for all commands.

## 2) Search API Compatibility Wrapper

- Centralize JQL search in one wrapper with fallbacks for Cloud/API drift.
- Prefer official client search path with `use_post=True`.
- Add robust error translation for 410/404/405 responses.

## 3) Version (Fix Version) Upsert

- Implement create/update version helper with idempotent behavior:
  - lookup by name
  - create if missing
  - update due date/description if existing
- On permission errors, return actionable hint instead of stacktrace.

## 4) Field-Safe Issue Update

- Fetch createmeta/editmeta and send only fields available in project context.
- Avoid hard failures when a field (e.g. fixVersions) is hidden/not configured.

## 5) Label Harmonization Strategy

- Add optional `--label-mode`:
  - `merge` (preserve existing labels + add new)
  - `replace` (strict desired set)
- Add optional label alias mapping file to normalize legacy label variants.

## 6) Migration & Tests

- Add integration tests for business/company-managed project variants.
- Add tests for search fallback + version permissions + label merge mode.
- Document behavior matrix in docs (Cloud project type vs supported features).

## 7) Token Metadata Display (TUI/CLI)

- Show API token metadata (e.g. expiration date) on TUI startup / status bar.
- If expiration is within 2 weeks, show a warning (or on CLI startup as stderr hint).
- Relates to the current "expired token -> silent empty result" issue: Jira Cloud API tokens don't expose expiry via a simple REST call today, so this needs research into what's available (Atlassian API token management API, or documenting a manual "last known expiry" config value).

## 8) Provider-Driven Resource Model (post-0.5.0)

- Introduce provider descriptors instead of hard-coding Jira-like filters/actions in CLI/TUI:
  - resources: issues, users, milestones/versions
  - fields: provider-native fields such as priority, labels, status, weight, epic
  - filters/sorts: data-driven per provider and per resource
  - actions: capability-driven per provider and selected item
- Keep Jira and demo mode as the first two providers behind the same abstraction.
- Add GitHub Issues as the first external read-only provider after Jira/demo are cleanly adapted.
- Prefer an official Python GitHub client for the GitHub provider.
- Make GitHub provider CWD-aware like `gh`:
  - infer `owner/repo` from the current Git remote when possible
  - consider reusing `gh` authentication or token discovery instead of asking for duplicate credentials
- Keep GitLab Issues as a later provider; account for GitLab-specific concepts such as epics and weights.
- Revisit project/package naming once a second real provider exists; `jira-cli` is appropriate until then, but a future generalized tool likely wants a name like `tracker-cli` or `issue-cli`.

Suggested sequence:

1. Extract a clean `IssueProvider`/resource-provider abstraction and adapt Jira + demo mode to it.
2. Add a GitHub Issues read-only provider.
3. Validate day-to-day transition ergonomics in the TUI before expanding write support.
4. Dogfood the GitHub provider by transferring this roadmap into GitHub Issues from the TUI.

Research notes:

- GitHub now has sub-issues/parent-child-style relationships; verify current API/client support before declaring parent/child unsupported.
- Board transition UX should support "move selected issue to next column + mandatory comment" and "transition to \<state\> + mandatory comment". This likely belongs in provider data/config: available transitions/actions should come from the provider, not from hard-coded Jira assumptions.
