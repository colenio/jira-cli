# Jira CLI

> Modular, class-based Jira command-line tool for issue listing, searching, and management.

## Features

- **List issues** by project with optional filtering (status, assignee, labels)
- **Search** with custom JQL queries
- **Find** issues by text in summary/description
- **View** issue details with comments
- **Assign** issues to users
- **Transition** issues to new status
- **Multiple output formats**: table, JSON, CSV, Markdown
- **dotenv support**: Load credentials from `.env` or `local.env` in CWD or parent directories

## Installation

### Via uv (local development)

```bash
cd colenio/tools/jira-cli
uv sync
uv run colenio-jira-cli list --help
```

### Via uvx (remote/published)

```bash
uvx colenio-jira-cli list --project PROJ
```

`jira-cli` remains available as a compatibility alias.

## Setup

Create a `.env` or `local.env` file in your working directory:

```bash
# Required
JIRA_URL=https://company.atlassian.net
JIRA_EMAIL=user@example.com
JIRA_API_TOKEN=your_api_token_here

# Optional
JIRA_PROJECT=PROJ      # Default project for list/find
JIRA_PROJECT_KEY=PROJ  # Backward-compatible fallback
```

### Getting your Jira API Token

1. Log in to your Jira Cloud instance
2. Go to Account Settings → Security
3. Click "Create API Token"
4. Copy the token and save to `.env`

## Usage

### List issues

```bash
# Basic listing
colenio-jira-cli list --project PROJ

# With filters
colenio-jira-cli list --project PROJ --status "In Progress" --assignee "john@example.com"

# With custom JQL
colenio-jira-cli list --project PROJ --jql 'priority = High'

# Different output formats
colenio-jira-cli list --project PROJ --format json
colenio-jira-cli list --project PROJ --format csv > issues.csv
colenio-jira-cli list --project PROJ --format md
```

### Search with JQL

```bash
colenio-jira-cli search 'project = PROJ AND status = "To Do" AND assignee is EMPTY'
colenio-jira-cli search 'text ~ "urgent"' --format json
```

### Find by text

```bash
colenio-jira-cli find --project PROJ "database migration"
colenio-jira-cli find --project PROJ "performance issue" --max-results 100
```

### View issue details

```bash
colenio-jira-cli view PROJ-123
colenio-jira-cli view PROJ-456 --comments
```

### Assign issue

```bash
colenio-jira-cli assign PROJ-789 john@example.com
```

### Transition issue

```bash
colenio-jira-cli transition PROJ-999 "In Progress" --comment "Starting work"
colenio-jira-cli transition PROJ-999 "Done"
```

## Architecture

- **`client.py`**: `JiraClient` class for REST API calls, auth, and endpoints
- **`query.py`**: `JiraQuery` class for JQL building and search logic
- **`render.py`**: `JiraRenderer` class for output formatting (table, JSON, CSV, Markdown)
- **`models.py`**: Pydantic models for Jira structures (`JiraIssue`, `JiraSearchResult`, `IssueRow`)
- **`dotenv.py`**: `DotEnv` class for robust `.env`/`local.env` loading
- **`cli.py`**: Click CLI commands (list, search, find, view, assign, transition)

All code uses proper classes, no helper functions. Follows informix-migration patterns.

## Development

```bash
# Install dev dependencies
uv sync --all-groups

# Run tests
uv run pytest

# Format and lint
uv run black jira_cli
uv run ruff check jira_cli
```

## Distribution

This tool is designed for publishing via uvx (like `helmrelease-verifier`):

1. Push to GitHub at `colenio/jira-cli`
2. Configure PyPI Trusted Publisher for this repository
3. Tag with version: `git tag v0.1.0` and push tag (`git push origin v0.1.0`)
4. GitHub Action `.github/workflows/release.yml` builds, tests, and publishes to PyPI
5. Package can be invoked anywhere with: `uvx colenio-jira-cli list --project PROJ`

## PowerShell Integration

Add to `$PROFILE` (e.g., via dotfiles/aliases.ps1):

```powershell
function jira-cli {
    uvx colenio-jira-cli @args
}

# Or use directly
alias jira = 'uvx colenio-jira-cli'
```

Then:

```powershell
jira list --project PROJ
```

## License

MIT
