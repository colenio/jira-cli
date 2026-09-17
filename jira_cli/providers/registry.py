"""Provider context discovery and construction."""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import urlparse

import click

from jira_cli.demo import DEMO_PROJECT_KEY
from jira_cli.dotenv import DotEnv

from .base import IssueTrackerProvider, ProviderContext
from .github import is_project_target
from .provider_factory import (
    create_or_exit,
    create_provider,
    github_repository_from_context as resolve_github_repository,
    github_token as resolve_github_token,
    validate_context,
)


def demo_context(target: str = DEMO_PROJECT_KEY) -> ProviderContext:
    """Build the built-in demo context."""
    return ProviderContext(name="demo", provider="demo", target=target, label=f"Demo / {target}")


def jira_context(project: str | None = None) -> ProviderContext:
    """Build a Jira context from explicit project or environment."""
    target = project or os.environ.get("JIRA_PROJECT") or os.environ.get("JIRA_PROJECT_KEY")
    if not target:
        raise ValueError("Missing Jira project key. Use --project or set JIRA_PROJECT in local.env/.env")
    base_url = os.environ.get("JIRA_URL") or os.environ.get("JIRA_BASE_URL") or ""
    hostname = urlparse(base_url).hostname or ""
    site = hostname.split(".", 1)[0] if hostname else ""
    suffix = f" ({site})" if site else ""
    return ProviderContext(
        name=f"jira:{target}", provider="jira", target=target, label=f"Jira / {target}{suffix}"
    )


def github_context(target: str) -> ProviderContext:
    """Build a unified GitHub context for a repository or Project V2 target."""
    if is_project_target(target):
        return ProviderContext(
            name=f"github:{target}",
            provider="github",
            target=target,
            label=f"GitHub Project / {target}",
        )
    return ProviderContext(
        name=f"github:{target}",
        provider="github",
        target=target,
        label=f"GitHub / {target}",
    )


def github_project_context(target: str) -> ProviderContext:
    """Alias for github_context for backwards compatibility."""
    return github_context(target)


class ProviderRegistry:
    """Discover and instantiate configured provider contexts."""

    def __init__(self, load_env: bool = True) -> None:
        if load_env:
            DotEnv(verbose=False).load()

    def available_contexts(self, project: str | None = None) -> list[ProviderContext]:
        """Return contexts that can be selected without prompting for extra data."""
        contexts = [demo_context()]
        gh_project = os.environ.get("GH_PROJECT") or os.environ.get("GITHUB_PROJECT")
        if gh_project and self._has_github_token():
            contexts.append(github_context(gh_project))
        else:
            github_repository = self.github_repository_from_context()
            if github_repository and self._has_github_token():
                contexts.append(github_context(github_repository))

        if self._has_jira_connection_settings():
            try:
                contexts.append(jira_context(project))
            except ValueError:
                pass

        # Deduplicate contexts by target
        seen_targets = set()
        unique_contexts = []
        for ctx in contexts:
            if ctx.target not in seen_targets:
                seen_targets.add(ctx.target)
                unique_contexts.append(ctx)

        return unique_contexts

    def resolve_context(
        self,
        provider: str | None = None,
        project: str | None = None,
        repository: str | None = None,
        demo: bool = False,
        interactive: bool = True,
    ) -> ProviderContext:
        """Resolve requested or auto-detected provider context."""
        if demo or (provider or "").lower() == "demo":
            return demo_context(project or DEMO_PROJECT_KEY)

        requested = (provider or "").lower()
        if requested in ("github", "gh", "github-project", "github_project", "gh-project"):
            target = (
                project
                or repository
                or os.environ.get("GH_PROJECT")
                or os.environ.get("GITHUB_PROJECT")
                or os.environ.get("GH_REPO")
                or os.environ.get("GITHUB_REPOSITORY")
                or self.github_repository_from_context()
            )
            if not target:
                raise ValueError("Missing GitHub target. Pass -p/--project owner/number, -R owner/repo, set GH_PROJECT, or set GH_REPO.")
            return github_context(target)
        if requested == "jira":
            return jira_context(project)

        if not requested:
            real_contexts = [c for c in self.available_contexts(project) if c.provider != "demo"]

            if len(real_contexts) > 1 and interactive:
                valid_contexts = []
                for context in real_contexts:
                    try:
                        warning = self.validate_context(context)
                    except Exception as error:
                        warning = f"{context.label} validation request failed: {error}"
                    if warning:
                        click.echo(f"WARNING: {warning}")
                    else:
                        valid_contexts.append(context)
                if valid_contexts:
                    real_contexts = valid_contexts
                else:
                    raise ValueError("No configured provider context passed validation")

            if len(real_contexts) == 1:
                return real_contexts[0]

            if len(real_contexts) > 1:
                if interactive and sys.stdin.isatty():
                    click.echo("Multiple provider contexts detected:", err=True)
                    for idx, ctx in enumerate(real_contexts, 1):
                        click.echo(f"  [{idx}] {ctx.label}", err=True)
                    choice = click.prompt(
                        "Select provider context",
                        type=click.IntRange(1, len(real_contexts)),
                        default=1,
                        err=True,
                    )
                    return real_contexts[choice - 1]

                # Priority order for non-interactive resolution
                for ctx in real_contexts:
                    if is_project_target(ctx.target) and (os.environ.get("GH_PROJECT") or os.environ.get("GITHUB_PROJECT")):
                        return ctx
                for ctx in real_contexts:
                    if ctx.provider == "jira":
                        return ctx
                return real_contexts[0]

            return jira_context(project)

        raise ValueError(f"Unknown provider '{provider}'. Available providers: demo, github, jira")

    def create_provider(self, context: ProviderContext) -> IssueTrackerProvider:
        """Instantiate a provider through the shared provider lifecycle."""
        return create_provider(context, self.github_token, self.github_repository_from_context)

    def create_or_exit(self, context: ProviderContext) -> IssueTrackerProvider:
        """Instantiate a provider, translating configuration errors to Click output."""
        return create_or_exit(context, self.github_token, self.github_repository_from_context)

    def validate_context(self, context: ProviderContext) -> str | None:
        """Validate provider credentials through the shared provider lifecycle."""
        return validate_context(context, self.github_token, self.github_repository_from_context)

    @staticmethod
    def github_token() -> str:
        """Resolve GitHub token from environment or gh CLI auth."""
        return resolve_github_token()

    @classmethod
    def github_repository_from_context(cls) -> str:
        """Infer owner/repository from env, git remote, or gh CLI."""
        return resolve_github_repository()

    @staticmethod
    def parse_github_remote(remote_url: str) -> str:
        """Parse owner/repo from common GitHub remote URL forms."""
        if not remote_url:
            return ""
        patterns = [
            r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>.+?)(?:\.git)?$",
            r"github\.com/(?P<owner>[^/]+)/(?P<repo>.+?)(?:\.git)?$",
        ]
        for pattern in patterns:
            match = re.search(pattern, remote_url)
            if match:
                return f"{match.group('owner')}/{match.group('repo')}"
        return ""

    @staticmethod
    def _has_jira_credentials() -> bool:
        return bool(
            (os.environ.get("JIRA_URL") or os.environ.get("JIRA_BASE_URL"))
            and (os.environ.get("JIRA_EMAIL") or os.environ.get("JIRA_USER"))
            and os.environ.get("JIRA_API_TOKEN")
        )

    @staticmethod
    def _has_jira_connection_settings() -> bool:
        return bool(
            (os.environ.get("JIRA_URL") or os.environ.get("JIRA_BASE_URL"))
            and (os.environ.get("JIRA_EMAIL") or os.environ.get("JIRA_USER"))
            and (os.environ.get("JIRA_PROJECT") or os.environ.get("JIRA_PROJECT_KEY"))
        )

    @classmethod
    def _has_github_token(cls) -> bool:
        return bool(cls.github_token())
