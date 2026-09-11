# TODO / Issue Backlog: Jira Client Hardening

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
- Relates to the current "expired token → silent empty result" issue: Jira Cloud API tokens don't expose expiry via a simple REST call today, so this needs research into what's available (Atlassian API token management API, or documenting a manual "last known expiry" config value).
