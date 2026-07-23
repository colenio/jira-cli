# Jira CLI

**Think github-cli but for Jira.**

> Modular, class-based Jira command-line tool for issue listing, searching, and management.

## Features

- **List issues** by project with optional filtering (status, assignee, labels)
- **Search** with custom JQL queries
- **Find** issues by text in summary/description
- **View** issue details with comments
- **Assign** issues to users
- **Transition** issues to new status
- **Create** issues with title/body/labels/assignee
- **Comment** on issues (plain, markdown, or ADF JSON)
- **Edit** issues (title/body/labels/assignee/priority/type)
- **Close/Reopen** issues via workflow transitions
- **Multiple output formats**: table, JSON, CSV, Markdown
- **dotenv support**: Load credentials from `.env` or `local.env` in CWD or parent directories

## Installation

### Via uv (local development)

```bash
cd colenio/tools/jira-cli
uv sync
uv run colenio-jira-cli issue --help
```

### Via uvx (remote/published)

```bash
uvx colenio-jira-cli issue list --project PROJ
```

`jira-cli` remains available as a command alias for `colenio-jira-cli`.

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

Primary command model is `issue` (similar to `gh issue ...`).

### Issue group

```bash
colenio-jira-cli issue --help
```

### List issues

```bash
# Canonical
colenio-jira-cli issue list --project PROJ

# With filters
colenio-jira-cli issue list --project PROJ --status "In Progress" --assignee "john@example.com"

# With custom JQL
colenio-jira-cli issue list --project PROJ --jql 'priority = High'

# Different output formats
colenio-jira-cli issue list --project PROJ --format json
colenio-jira-cli issue list --project PROJ --format csv > issues.csv
colenio-jira-cli issue list --project PROJ --format md
```

### Search with JQL

```bash
colenio-jira-cli issue search 'project = PROJ AND status = "To Do" AND assignee is EMPTY'
colenio-jira-cli issue search 'text ~ "urgent"' --format json
```

### Find by text

```bash
colenio-jira-cli issue find --project PROJ "database migration"
colenio-jira-cli issue find --project PROJ "performance issue" --max-results 100
```

### View issue details

```bash
colenio-jira-cli issue view PROJ-123
colenio-jira-cli issue view PROJ-456 --comments
```

### Assign issue

```bash
colenio-jira-cli issue assign PROJ-789 john@example.com
```

### Transition issue

```bash
colenio-jira-cli issue transition PROJ-999 "In Progress" --comment "Starting work"
colenio-jira-cli issue transition PROJ-999 "Done"
```

### Create issue

```bash
# Similar to gh issue create
colenio-jira-cli issue create --project PROJ --title "Access governance ticket" --body "Please define access process"

# With labels and assignee
colenio-jira-cli issue create \
  --project PROJ \
  --title "[ORG] GitLab Access Governance" \
  --body-file ./ticket.md \
  --type Task \
  --label governance --label access,auditability \
  --assignee user@example.com \
  --priority High
```

### Comment on issue

```bash
# Similar to gh issue comment
colenio-jira-cli issue comment PROJ-123 --body "Reviewed. Access approved."

# Markdown and ADF JSON support
colenio-jira-cli issue comment PROJ-123 --format md --body "**Update:** done"
colenio-jira-cli issue comment PROJ-123 --format adf --body-file ./comment.adf.json
```

### Edit issue

```bash
colenio-jira-cli issue edit PROJ-123 --title "Updated title" --body "Updated description"
colenio-jira-cli issue edit PROJ-123 --add-label governance --remove-label old-label
colenio-jira-cli issue edit PROJ-123 --set-label governance,access --priority Highest
```

### Close / reopen issue

```bash
# Auto-resolve transition (Done/Closed/Resolved)
colenio-jira-cli issue close PROJ-123 --comment "Completed"

# Auto-resolve transition (Reopen/Reopened/Open/To Do)
colenio-jira-cli issue reopen PROJ-123 --comment "Need follow-up"

# Explicit transition override by name or id
colenio-jira-cli issue close PROJ-123 --transition "Done"
```

### Interactive TUI (Terminal User Interface)

Launch an interactive k9s-style interface for managing Jira issues:

```bash
# Basic TUI launch
colenio-jira-cli tui --project PROJ

# TUI will load default project from JIRA_PROJECT env if available
colenio-jira-cli tui
```

**Keyboard Shortcuts in TUI:**

| Key       | Action                             |
| --------- | ---------------------------------- |
| `↑` / `↓` | Navigate issues up/down            |
| `o`       | Open selected issue in browser     |
| `p`       | Reset source to project            |
| `f`       | Find by text (summary/description) |
| `j`       | Run custom JQL query               |
| `t`       | Transition selected issue          |
| `a`       | Assign selected issue              |
| `c`       | Add comment (plain/md/adf)         |
| `n`       | Next comment on selected issue     |
| `b`       | Previous comment on selected issue |
| `u`       | Drill up to parent issue           |
| `d`       | Drill down to child issues         |
| `Enter`   | Execute active query/input         |
| `r`       | Refresh issue list                 |
| `/`       | Focus live filter                  |
| `Esc`     | Close input or reset source        |
| `?`       | Show help                          |
| `q`       | Quit TUI                           |

Transition input format in TUI:

- `t` opens transition input for the selected issue.
- Enter either transition ID or transition name.
- Optional comment: `<transition> | <comment>`

Comment input format in TUI:

- `c` opens comment input for the selected issue.
- Supported formats:
  - `plain:<text>` or just `<text>`
  - `md:<markdown>` (lightweight markdown validation)
  - `adf:<json>` (ADF JSON parse + structure validation)

**Installation (TUI included by default):**

```bash
# Install dependencies
uv sync

# Then use
uv run colenio-jira-cli tui --project PROJ
```

Or via `uvx`:

```bash
uvx --python 3.11 colenio-jira-cli tui --project PROJ
```

## Running Without uvx

You can run the CLI and TUI without `uvx` in two common ways.

### Option 1: Local repo via uv run

```bash
cd colenio/tools/jira-cli
uv sync
uv run colenio-jira-cli tui --project PROJ
```

### Option 2: Virtualenv + pip (no uv required)

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install colenio-jira-cli
colenio-jira-cli tui --project PROJ
```

### Option 3: pip --user (no venv)

Useful for locked-down environments where virtual environments are not allowed.

```bash
python -m pip install --user -U pip
python -m pip install --user colenio-jira-cli
colenio-jira-cli tui --project PROJ
```

If the command is not found on Windows, ensure your user Scripts path is in `PATH`:

```powershell
$scripts = Join-Path (py -m site --user-base) "Scripts"
$env:PATH += ";$scripts"
# Or restart the terminal after updating PATH permanently
```

## Development

```bash
# Install dev dependencies
uv sync --extra dev --extra local-dev

# Run tests
uv run pytest

# Format and lint
uv run black jira_cli
uv run ruff check jira_cli

# Run standardized local QA scripts
uv run jira-cli-ruff
uv run jira-cli-radon
uv run jira-cli-pylint
uv run jira-cli-check
uv run jira-cli-qa
```

## Additional Docs

- [docs/architecture.md](docs/architecture.md)
- [docs/distribution.md](docs/distribution.md)

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
