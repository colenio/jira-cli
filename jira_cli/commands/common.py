"""Shared helpers for command modules."""

import json
import os
from typing import Optional

import click

from jira_cli.dotenv import DotEnv
from jira_cli.providers import IssueTrackerProvider
from jira_cli.providers.jira import JiraProvider
from jira_cli.validation import validate_adf_doc, validate_markdown_text


class OrderedGroup(click.Group):
    """Click Group that lists subcommands in registration order (gh-style curated grouping)
    instead of Click's default alphabetical sort, so `--help` reads read-commands-first,
    then write-commands, rather than a-z."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(self.commands)


def get_jira_client(
    base_url: Optional[str] = None,
    email: Optional[str] = None,
    api_token: Optional[str] = None,
) -> IssueTrackerProvider:
    """Load Jira credentials from env/dotenv and create client."""
    env = DotEnv(verbose=False)
    env.load()

    base_url = base_url or os.environ.get("JIRA_URL") or os.environ.get("JIRA_BASE_URL")
    email = email or os.environ.get("JIRA_EMAIL") or os.environ.get("JIRA_USER")
    api_token = api_token or os.environ.get("JIRA_API_TOKEN")

    if not all([base_url, email, api_token]):
        missing = []
        if not base_url:
            missing.append("JIRA_URL or JIRA_BASE_URL")
        if not email:
            missing.append("JIRA_EMAIL or JIRA_USER")
        if not api_token:
            missing.append("JIRA_API_TOKEN")

        click.echo(f"Missing: {', '.join(missing)}", err=True)
        click.echo("Configure in .env or local.env in CWD or parent directories:", err=True)
        click.echo("  JIRA_URL=https://company.atlassian.net", err=True)
        click.echo("  JIRA_EMAIL=user@example.com", err=True)
        click.echo("  JIRA_API_TOKEN=your_api_token", err=True)
        raise SystemExit(1)

    return JiraProvider(base_url=base_url, email=email, api_token=api_token)


def resolve_project(project: Optional[str]) -> str:
    """Resolve project key from option or env (JIRA_PROJECT/JIRA_PROJECT_KEY)."""
    resolved = project or os.environ.get("JIRA_PROJECT") or os.environ.get("JIRA_PROJECT_KEY")
    if not resolved:
        click.echo("Missing project key. Use --project or set JIRA_PROJECT in local.env/.env", err=True)
        raise SystemExit(1)
    return resolved


def load_body(body: str, body_file: str) -> str:
    """Resolve issue/comment body from inline text or file path."""
    if body and body_file:
        click.echo("Use either --body or --body-file, not both.", err=True)
        raise SystemExit(1)

    if body_file:
        try:
            with open(body_file, "r", encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError as exc:
            click.echo(f"Could not read --body-file '{body_file}': {exc}", err=True)
            raise SystemExit(1) from exc

    return body.strip() if body else ""


def parse_labels(labels: tuple[str, ...]) -> list[str]:
    """Parse repeated and comma-separated label input."""
    parsed: list[str] = []
    for raw in labels:
        for token in raw.split(","):
            value = token.strip()
            if value:
                parsed.append(value)
    return list(dict.fromkeys(parsed))


def split_label_values(raw_values: tuple[str, ...]) -> list[str]:
    """Split repeated/comma-separated labels into normalized list."""
    labels: list[str] = []
    for raw in raw_values:
        for token in raw.split(","):
            value = token.strip()
            if value:
                labels.append(value)
    return labels


def parse_text_payload(mode: str, payload: str) -> str | dict:
    """Parse plain/markdown/adf payload and return Jira-ready value."""
    if mode == "adf":
        try:
            adf_doc = json.loads(payload)
        except json.JSONDecodeError as decode_error:
            raise ValueError(f"Invalid ADF JSON: {decode_error}") from decode_error
        valid, error = validate_adf_doc(adf_doc)
        if not valid:
            raise ValueError(f"Invalid ADF: {error}")
        return adf_doc

    if mode == "md":
        valid, error = validate_markdown_text(payload)
        if not valid:
            raise ValueError(f"Invalid Markdown: {error}")

    if not payload.strip():
        raise ValueError("Body is empty")

    return payload


def resolve_transition_id(client: IssueTrackerProvider, key: str, requested: str, fallback_names: list[str]) -> str:
    """Resolve transition id by explicit id/name or fallback names."""
    transitions = client.get_transitions(key)
    if not transitions:
        raise ValueError(f"No transitions available for {key}")

    def _name(item: dict) -> str:
        return str(item.get("name", "")).strip()

    def _id(item: dict) -> str:
        return str(item.get("id", "")).strip()

    if requested:
        for item in transitions:
            if _id(item) == requested:
                return _id(item)
        for item in transitions:
            if _name(item).casefold() == requested.casefold():
                return _id(item)
        for item in transitions:
            if requested.casefold() in _name(item).casefold():
                return _id(item)
        available = ", ".join([f"{_id(t)}:{_name(t)}" for t in transitions])
        raise ValueError(f"Transition '{requested}' not found. Available: {available}")

    for candidate in fallback_names:
        for item in transitions:
            if _name(item).casefold() == candidate.casefold():
                return _id(item)
    for candidate in fallback_names:
        for item in transitions:
            if candidate.casefold() in _name(item).casefold():
                return _id(item)

    available = ", ".join([f"{_id(t)}:{_name(t)}" for t in transitions])
    raise ValueError(f"Could not resolve transition automatically for {key}. Available: {available}")
