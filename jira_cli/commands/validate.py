"""Provider configuration validation commands."""

import click

from jira_cli.providers.registry import ProviderRegistry


@click.command(name="validate")
@click.option("--provider", default="", help="Validate one provider (jira or github).")
@click.option("--project", "project", default="", help="Jira project key or GitHub Project target.")
@click.option("--repo", "repository", default="", help="GitHub repository target (owner/name).")
def validate_contexts(provider: str, project: str, repository: str) -> None:
    """Validate configured provider credentials before starting the TUI."""
    registry = ProviderRegistry()
    contexts = registry.available_contexts(project or None)
    if provider:
        context = registry.resolve_context(
            provider=provider,
            project=project or None,
            repository=repository or None,
            interactive=False,
        )
        contexts = [context]

    warnings: list[str] = []
    for context in contexts:
        if context.provider == "demo":
            continue
        try:
            warning = registry.validate_context(context)
        except Exception as error:
            warning = f"{context.label}: validation request failed: {error}"
        if warning:
            warnings.append(warning)
        else:
            click.echo(f"OK: {context.label}")

    for warning in warnings:
        click.echo(f"WARNING: {warning}")
    if warnings:
        raise click.exceptions.Exit(1)
    if not any(context.provider != "demo" for context in contexts):
        click.echo("WARNING: no configured provider context found")
        raise click.exceptions.Exit(1)
