<!-- markdownlint-disable MD041 -->

[![CI](https://github.com/colenio/jira-cli/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/colenio/jira-cli/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/colenio-jira-cli.svg)](https://pypi.org/project/colenio-jira-cli/)

# Jira CLI

**Think github-cli but for Jira.**

> Modular, class-based Jira command-line tool for issue listing, searching, and management.

There's a CLI (`jira issue ...`) and an interactive TUI (`jira tui --project PROJ`). Both are self-explanatory via `--help` / the in-app `?` help — see **[docs/features.md](docs/features.md)** for the full feature overview and TUI keyboard shortcuts.

## Installation

```powershell
# Editable install for local development
uv tool install --editable .
jira --help
```

```bash
# Remote/published, via uvx
uvx --from colenio-jira-cli jira-cli issue list --project PROJ
```

The PyPI/package name is `colenio-jira-cli`; the installed commands are `jira` and `jira-cli` (both run the same CLI). See [docs/distribution.md](docs/distribution.md) for other install options (pip, venv).

For screenshots, screencasts, or trying the TUI without Jira credentials, use synthetic demo data:

```bash
jira tui --demo
```

GitHub Issues can be browsed read-only in the TUI. Authentication uses `GH_TOKEN`
or your existing `gh auth login` session, and `-R` works like `gh -R owner/name`:

```bash
jira tui --provider github -R colenio/jira-cli
```

## Screenshots

The default issue table is optimized for quick triage: type, key, summary, status, assignee,
and priority stay visible while the detail pane follows the current selection.

![Jira CLI demo issue table](docs/img/tui/01-issues-table.png)

The board view groups the same issue source by workflow status, with Backlog on the left and
done states on the right.

![Jira CLI demo board view](docs/img/tui/02-issues-board.png)

## Setup

Start with the tracked [local.env.example](local.env.example): copy it to `local.env` or `.env`,
then replace the placeholder values. Never commit the copied file because it contains credentials.

The CLI searches the current directory and up to three parent directories. In each directory it
checks `local.env` before `.env` and loads the first matching file. Existing process environment
variables are used when no file is found.

```bash
# Required
JIRA_URL=https://company.atlassian.net
JIRA_EMAIL=user@example.com
JIRA_API_TOKEN=your_api_token_here

# Optional
JIRA_PROJECT=PROJ      # Default project for list/find/tui
```

Get your API token from Jira Cloud: Account Settings → Security → Create API Token.

For GitHub, set `GH_TOKEN`, configure `GH_REPO` or `GH_PROJECT` as needed, or use an existing
`gh auth login` session. Validate configured contexts before starting the TUI with:

```powershell
jira validate
jira validate --provider jira --project PROJ
jira validate --provider github --repo owner/repository
```

Use `jira tui --demo` for a credential-free local run.

## Development

```bash
uv sync --extra dev --extra local-dev
uv run pytest
uv run black jira_cli
uv run ruff check jira_cli
uv run jira-cli-qa   # runs ruff + radon + pylint
```

## Documentation Site

```bash
uv sync --extra docs
uv run jira-cli-docs        # strict MkDocs build
uv run jira-cli-docs-serve  # local preview
```

The docs are built with MkDocs Material and mkdocstrings. API pages render Python docstrings directly from `jira_cli`.

## Additional Docs

- [docs/features.md](docs/features.md) — feature overview + TUI keyboard shortcuts
- [docs/explanation/architecture.md](docs/explanation/architecture.md)
- [docs/distribution.md](docs/distribution.md)

## License

MIT
