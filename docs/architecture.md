# Architecture

## Modules

- client.py: JiraClient for REST API calls, auth, and endpoints.
- query.py: JiraQuery for JQL composition and search logic.
- render.py: JiraRenderer for table/json/csv/markdown output.
- models.py: Pydantic models for Jira structures.
- dotenv.py: DotEnv loader for .env/local.env discovery.
- cli.py: Click command surface (list, search, find, view, assign, transition, tui).

## TUI Layer

- tui/app.py: Textual application and screen composition.
- tui/colors.py: Theme constants.
- tui/widgets/: Reusable UI components for table/panels.

## Design Notes

- Keep transport concerns in JiraClient.
- Keep query assembly in JiraQuery.
- Keep output formatting in JiraRenderer.
- Keep TUI orchestration in tui/app.py.
- Keep CLI commands thin and delegating.
