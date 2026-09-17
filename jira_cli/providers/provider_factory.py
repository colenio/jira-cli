"""Provider construction and authentication lifecycle."""

from __future__ import annotations

import os
import subprocess

import click

from .base import IssueTrackerProvider, ProviderContext
from .demo import DemoProvider
from .github import GITHUB_PROVIDER_DESCRIPTOR, GitHubProvider
from .jira import JIRA_PROVIDER_DESCRIPTOR, JiraProvider


def github_token() -> str:
    """Resolve GH_TOKEN or an existing gh CLI session."""
    token = os.environ.get("GH_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def github_repository_from_context() -> str:
    """Infer a GitHub repository from environment, git remote, or gh CLI."""
    configured = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY")
    if configured:
        return configured
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        result = None
    remote = result.stdout.strip() if result and result.returncode == 0 else ""
    if remote:
        from .registry import ProviderRegistry

        parsed = ProviderRegistry.parse_github_remote(remote)
        if parsed:
            return parsed
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def create_provider(
    context: ProviderContext,
    token_resolver=github_token,
    repository_resolver=github_repository_from_context,
) -> IssueTrackerProvider:
    """Construct the provider selected by a context."""
    if context.provider == "demo":
        return DemoProvider()
    if context.provider in ("github", "gh", "github-project", "github_project"):
        token = token_resolver()
        if not token:
            raise ValueError("Missing GitHub token. Set GH_TOKEN or run: gh auth login")
        default_owner = ""
        repo = repository_resolver()
        if repo and "/" in repo:
            default_owner = repo.split("/", 1)[0]
        return GitHubProvider(target=context.target, token=token, default_owner=default_owner)
    if context.provider == "jira":
        base_url = os.environ.get("JIRA_URL") or os.environ.get("JIRA_BASE_URL")
        email = os.environ.get("JIRA_EMAIL") or os.environ.get("JIRA_USER")
        api_token = os.environ.get("JIRA_API_TOKEN")
        missing = []
        if not base_url:
            missing.append("JIRA_URL or JIRA_BASE_URL")
        if not email:
            missing.append("JIRA_EMAIL or JIRA_USER")
        if not api_token:
            missing.append("JIRA_API_TOKEN")
        if missing:
            raise ValueError(f"Missing: {', '.join(missing)}")
        return JiraProvider(base_url=base_url, email=email, api_token=api_token)
    raise ValueError(f"Unknown provider context '{context.provider}'")


def format_validation_failure(context: ProviderContext, reason: str) -> str:
    """Format a provider validation failure with actionable token guidance."""
    descriptors = {"jira": JIRA_PROVIDER_DESCRIPTOR, "github": GITHUB_PROVIDER_DESCRIPTOR}
    descriptor = descriptors.get(context.provider)
    if not descriptor:
        return f"{context.label} validation failed: {reason}"
    return (
        f"{context.label} validation failed: {reason}. "
        f"Set {descriptor.token_env}; create a token at {descriptor.token_url}"
    )


def validate_context(
    context: ProviderContext,
    token_resolver=github_token,
    repository_resolver=github_repository_from_context,
) -> str | None:
    """Validate provider credentials and return an actionable warning, if any."""
    if context.provider != "jira":
        try:
            client = create_provider(context, token_resolver, repository_resolver)
            client.get_current_user()
        except Exception as error:
            if context.provider == "github":
                return format_validation_failure(
                    context,
                    "could not access this target; the token may be invalid, expired, or missing required permissions",
                )
            return format_validation_failure(context, str(error))
        return None

    base_url = os.environ.get("JIRA_URL") or os.environ.get("JIRA_BASE_URL") or ""
    email = os.environ.get("JIRA_EMAIL") or os.environ.get("JIRA_USER") or ""
    token = os.environ.get("JIRA_API_TOKEN") or ""
    missing = []
    if not base_url:
        missing.append("JIRA_URL or JIRA_BASE_URL")
    if not email:
        missing.append("JIRA_EMAIL or JIRA_USER")
    if not token:
        missing.append("JIRA_API_TOKEN")
    if missing:
        return format_validation_failure(context, f"missing {', '.join(missing)}")

    client = JiraProvider(base_url=base_url, email=email, api_token=token)
    try:
        client.get_current_user()
    except Exception as error:
        status_code = getattr(error, "status_code", None) or getattr(error, "status", None)
        text = str(error).casefold()
        if status_code in (401, 403) or any(
            marker in text for marker in ("unauthorized", "authentication", "invalid token", "token expired")
        ):
            return format_validation_failure(context, "token rejected or expired")
        raise
    return None


def create_or_exit(
    context: ProviderContext,
    token_resolver=github_token,
    repository_resolver=github_repository_from_context,
) -> IssueTrackerProvider:
    """Construct a provider, translating configuration errors to Click output."""
    try:
        return create_provider(context, token_resolver, repository_resolver)
    except ValueError as error:
        click.echo(str(error), err=True)
        click.echo(
            "Configure Jira in .env/local.env, GitHub via GH_TOKEN/gh auth, or use --provider demo / --demo.",
            err=True,
        )
        raise SystemExit(1) from error
