"""Provider context discovery and construction."""

from __future__ import annotations

import os

import click

from jira_cli.demo import DEMO_PROJECT_KEY
from jira_cli.dotenv import DotEnv

from .base import IssueTrackerProvider, ProviderContext
from .demo import DemoProvider
from .jira import JiraProvider


def demo_context(target: str = DEMO_PROJECT_KEY) -> ProviderContext:
    """Build the built-in demo context."""
    return ProviderContext(name="demo", provider="demo", target=target, label=f"Demo / {target}")


def jira_context(project: str | None = None) -> ProviderContext:
    """Build a Jira context from explicit project or environment."""
    target = project or os.environ.get("JIRA_PROJECT") or os.environ.get("JIRA_PROJECT_KEY")
    if not target:
        raise ValueError("Missing Jira project key. Use --project or set JIRA_PROJECT in local.env/.env")
    return ProviderContext(name=f"jira:{target}", provider="jira", target=target, label=f"Jira / {target}")


class ProviderRegistry:
    """Discover and instantiate configured provider contexts."""

    def __init__(self, load_env: bool = True) -> None:
        if load_env:
            DotEnv(verbose=False).load()

    def available_contexts(self, project: str | None = None) -> list[ProviderContext]:
        """Return contexts that can be selected without prompting for extra data."""
        contexts = [demo_context()]
        if self._has_jira_credentials():
            try:
                contexts.append(jira_context(project))
            except ValueError:
                pass
        return contexts

    def resolve_context(self, provider: str | None = None, project: str | None = None, demo: bool = False) -> ProviderContext:
        """Resolve the requested provider context, defaulting to Jira when possible."""
        if demo or (provider or "").lower() == "demo":
            return demo_context(project or DEMO_PROJECT_KEY)
        requested = (provider or "jira").lower()
        if requested == "jira":
            return jira_context(project)
        raise ValueError(f"Unknown provider '{provider}'. Available providers: demo, jira")

    def create_provider(self, context: ProviderContext) -> IssueTrackerProvider:
        """Instantiate a provider for the given context."""
        if context.provider == "demo":
            return DemoProvider()
        if context.provider == "jira":
            base_url = os.environ.get("JIRA_URL") or os.environ.get("JIRA_BASE_URL")
            email = os.environ.get("JIRA_EMAIL") or os.environ.get("JIRA_USER")
            api_token = os.environ.get("JIRA_API_TOKEN") or os.environ.get("JIRA_TOKEN")
            missing = []
            if not base_url:
                missing.append("JIRA_URL or JIRA_BASE_URL")
            if not email:
                missing.append("JIRA_EMAIL or JIRA_USER")
            if not api_token:
                missing.append("JIRA_API_TOKEN or JIRA_TOKEN")
            if missing:
                raise ValueError(f"Missing: {', '.join(missing)}")
            return JiraProvider(base_url=base_url, email=email, api_token=api_token)
        raise ValueError(f"Unknown provider context '{context.provider}'")

    def create_or_exit(self, context: ProviderContext) -> IssueTrackerProvider:
        """Instantiate a provider, translating configuration errors to Click output."""
        try:
            return self.create_provider(context)
        except ValueError as value_error:
            click.echo(str(value_error), err=True)
            click.echo("Configure Jira in .env or local.env, or use --provider demo / --demo.", err=True)
            raise SystemExit(1) from value_error

    @staticmethod
    def _has_jira_credentials() -> bool:
        return bool(
            (os.environ.get("JIRA_URL") or os.environ.get("JIRA_BASE_URL"))
            and (os.environ.get("JIRA_EMAIL") or os.environ.get("JIRA_USER"))
            and (os.environ.get("JIRA_API_TOKEN") or os.environ.get("JIRA_TOKEN"))
        )
