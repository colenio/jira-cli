"""Provider context discovery and construction."""

from __future__ import annotations

import os
import re
import subprocess

import click

from jira_cli.demo import DEMO_PROJECT_KEY
from jira_cli.dotenv import DotEnv

from .base import IssueTrackerProvider, ProviderContext
from .demo import DemoProvider
from .github import GitHubProvider
from .github_project import GitHubProjectProvider
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


def github_context(repository: str) -> ProviderContext:
    """Build a GitHub context for owner/repository."""
    return ProviderContext(
        name=f"github:{repository}", provider="github", target=repository, label=f"GitHub / {repository}"
    )


def github_project_context(target: str) -> ProviderContext:
    """Build a GitHub Project V2 context for owner/number or target string."""
    return ProviderContext(
        name=f"github-project:{target}",
        provider="github-project",
        target=target,
        label=f"GitHub Project / {target}",
    )


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
            contexts.append(github_project_context(gh_project))
        github_repository = self.github_repository_from_context()
        if github_repository and self._has_github_token():
            contexts.append(github_context(github_repository))
        if self._has_jira_credentials():
            try:
                contexts.append(jira_context(project))
            except ValueError:
                pass
        return contexts

    def resolve_context(
        self,
        provider: str | None = None,
        project: str | None = None,
        repository: str | None = None,
        demo: bool = False,
    ) -> ProviderContext:
        """Resolve the requested provider context, defaulting to Jira when possible."""
        if demo or (provider or "").lower() == "demo":
            return demo_context(project or DEMO_PROJECT_KEY)
        requested = (provider or "").lower()
        if requested in ("github-project", "github_project", "gh-project"):
            target = project or repository or os.environ.get("GH_PROJECT") or os.environ.get("GITHUB_PROJECT")
            if not target:
                repo = self.github_repository_from_context()
                if repo and "/" in repo:
                    # Default owner if numeric project passed or missing
                    raise ValueError("Missing GitHub Project target. Pass --project owner/number (e.g. colenio/21) or set GH_PROJECT.")
                raise ValueError("Missing GitHub Project target. Pass --project owner/number or set GH_PROJECT.")
            return github_project_context(target)
        if requested == "github":
            target = repository or self.github_repository_from_context()
            if not target:
                raise ValueError("Missing GitHub repository. Use -R owner/name, set GH_REPO, or run inside a GitHub repo.")
            return github_context(target)
        if requested == "jira" or not requested:
            return jira_context(project)
        raise ValueError(f"Unknown provider '{provider}'. Available providers: demo, github, github-project, jira")

    def create_provider(self, context: ProviderContext) -> IssueTrackerProvider:
        """Instantiate a provider for the given context."""
        if context.provider == "demo":
            return DemoProvider()
        if context.provider == "github":
            token = self.github_token()
            if not token:
                raise ValueError("Missing GitHub token. Set GH_TOKEN/GITHUB_TOKEN or run: gh auth login")
            return GitHubProvider(repository=context.target, token=token)
        if context.provider in ("github-project", "github_project"):
            token = self.github_token()
            if not token:
                raise ValueError("Missing GitHub token. Set GH_TOKEN/GITHUB_TOKEN or run: gh auth login")
            default_owner = ""
            repo = self.github_repository_from_context()
            if repo and "/" in repo:
                default_owner = repo.split("/")[0]
            return GitHubProjectProvider(target=context.target, token=token, default_owner=default_owner)
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
            click.echo("Configure Jira in .env/local.env, GitHub via gh auth/GH_TOKEN, or use --provider demo / --demo.", err=True)
            raise SystemExit(1) from value_error

    @staticmethod
    def github_token() -> str:
        """Resolve GitHub token from environment or gh CLI auth."""
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            return token
        try:
            result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""

    @classmethod
    def github_repository_from_context(cls) -> str:
        """Infer owner/repository from env, git remote, or gh CLI."""
        configured = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY")
        if configured:
            return configured
        remote = cls._git_remote_url()
        parsed = cls.parse_github_remote(remote)
        if parsed:
            return parsed
        return cls._gh_repo_view()

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
    def _git_remote_url() -> str:
        try:
            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True, check=False
            )
        except FileNotFoundError:
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""

    @staticmethod
    def _gh_repo_view() -> str:
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

    @staticmethod
    def _has_jira_credentials() -> bool:
        return bool(
            (os.environ.get("JIRA_URL") or os.environ.get("JIRA_BASE_URL"))
            and (os.environ.get("JIRA_EMAIL") or os.environ.get("JIRA_USER"))
            and (os.environ.get("JIRA_API_TOKEN") or os.environ.get("JIRA_TOKEN"))
        )

    @classmethod
    def _has_github_token(cls) -> bool:
        return bool(cls.github_token())
