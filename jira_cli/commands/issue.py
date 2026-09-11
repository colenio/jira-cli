"""Issue command group and subcommands."""

import webbrowser

import click

from jira_cli.commands.common import (
    OrderedGroup,
    get_jira_client,
    load_body,
    parse_labels,
    parse_text_payload,
    resolve_project,
    resolve_transition_id,
    split_label_values,
)


@click.group(name="issue", cls=OrderedGroup)
def issue_group() -> None:
    """Create, edit, comment and transition Jira issues."""


@click.command(name="create")
@click.option("--project", "project", "-p", default="", help="Jira project key; defaults to JIRA_PROJECT/JIRA_PROJECT_KEY")
@click.option("--title", "title", "-t", required=True, help="Issue title/summary")
@click.option("--body", "body", default="", help="Issue description text")
@click.option("--body-file", "body_file", default="", help="Read issue description from file")
@click.option(
    "--type",
    "issue_type",
    default="Task",
    show_default=True,
    help="Issue type name (e.g. Task, Story, Bug)",
)
@click.option("--label", "labels", multiple=True, help="Issue label (repeatable or comma-separated)")
@click.option("--assignee", default="", help="Assignee (email/accountId depending on Jira setup)")
@click.option("--priority", default="", help="Priority name (e.g. Highest, High, Medium)")
@click.option("--parent", default="", help="Parent issue key")
@click.option(
    "--body-format",
    "body_format",
    type=click.Choice(["plain", "md", "adf"]),
    default="plain",
    show_default=True,
    help="Description format",
)
@click.option("--web", "open_web", is_flag=True, help="Open created issue in browser")
def issue_create(
    project: str,
    title: str,
    body: str,
    body_file: str,
    issue_type: str,
    labels: tuple[str, ...],
    assignee: str,
    priority: str,
    parent: str,
    body_format: str,
    open_web: bool,
) -> None:
    """Create a Jira issue (similar to gh issue create)."""
    try:
        client = get_jira_client()
        project_key = resolve_project(project)
        raw_body = load_body(body, body_file)
        parsed_body = parse_text_payload(body_format, raw_body)
        parsed_labels = parse_labels(labels)

        issue = client.create_issue(
            project_key=project_key,
            title=title,
            body=parsed_body,
            issue_type=issue_type,
            labels=parsed_labels or None,
            assignee=assignee or None,
            priority=priority or None,
            parent=parent or None,
        )

        key = issue.get("key", "<unknown>")
        issue_url = f"{client.base_url.rstrip('/')}/browse/{key}"
        click.echo(f"Created {key}")
        click.echo(issue_url)

        if open_web:
            opened = webbrowser.open(issue_url)
            if not opened:
                click.echo("Browser could not be opened automatically")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@click.command(name="comment")
@click.argument("key")
@click.option("--body", "body", default="", help="Comment body")
@click.option("--body-file", "body_file", default="", help="Read comment body from file")
@click.option(
    "--format",
    "body_format",
    type=click.Choice(["plain", "md", "adf"]),
    default="plain",
    show_default=True,
    help="Comment format",
)
def issue_comment(key: str, body: str, body_file: str, body_format: str) -> None:
    """Add a comment to a Jira issue (similar to gh issue comment)."""
    try:
        client = get_jira_client()
        raw_body = load_body(body, body_file)
        parsed = parse_text_payload(body_format, raw_body)

        if body_format == "adf":
            client.add_comment(key, parsed, use_adf=True)
        else:
            client.add_comment(key, parsed, use_adf=False)

        click.echo(f"Comment added to {key}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@click.command(name="edit")
@click.argument("key")
@click.option("--title", "title", default="", help="New issue title/summary")
@click.option("--body", "body", default="", help="New issue description")
@click.option("--body-file", "body_file", default="", help="Read new description from file")
@click.option(
    "--body-format",
    "body_format",
    type=click.Choice(["plain", "md", "adf"]),
    default="plain",
    show_default=True,
    help="Description format",
)
@click.option("--add-label", "add_labels", multiple=True, help="Add label(s), repeatable or comma-separated")
@click.option("--remove-label", "remove_labels", multiple=True, help="Remove label(s), repeatable or comma-separated")
@click.option("--set-label", "set_labels", multiple=True, help="Replace all labels, repeatable or comma-separated")
@click.option("--assignee", default="", help="Set assignee (email/accountId depending on Jira setup)")
@click.option("--clear-assignee", is_flag=True, help="Clear assignee")
@click.option("--priority", default="", help="Set priority name")
@click.option("--type", "issue_type", default="", help="Set issue type name")
def issue_edit(
    key: str,
    title: str,
    body: str,
    body_file: str,
    body_format: str,
    add_labels: tuple[str, ...],
    remove_labels: tuple[str, ...],
    set_labels: tuple[str, ...],
    assignee: str,
    clear_assignee: bool,
    priority: str,
    issue_type: str,
) -> None:
    """Edit a Jira issue (similar to gh issue edit)."""
    try:
        if clear_assignee and assignee:
            raise ValueError("Use either --assignee or --clear-assignee, not both")

        client = get_jira_client()
        fields: dict = {}

        if title:
            fields["summary"] = title

        if body or body_file:
            raw_body = load_body(body, body_file)
            fields["description"] = parse_text_payload(body_format, raw_body)

        if issue_type:
            fields["issuetype"] = {"name": issue_type}

        if priority:
            fields["priority"] = {"name": priority}

        if assignee:
            fields["assignee"] = {"name": assignee}
        elif clear_assignee:
            fields["assignee"] = None

        if set_labels:
            fields["labels"] = list(dict.fromkeys(split_label_values(set_labels)))
        elif add_labels or remove_labels:
            issue = client.get_issue(key, fields=["labels"])
            current_labels = issue.get("fields", {}).get("labels", []) or []
            new_labels = list(current_labels)

            for label in split_label_values(add_labels):
                if label not in new_labels:
                    new_labels.append(label)

            remove_set = set(split_label_values(remove_labels))
            if remove_set:
                new_labels = [label for label in new_labels if label not in remove_set]

            fields["labels"] = new_labels

        if not fields:
            raise ValueError("No changes requested. Provide at least one edit option.")

        client.update_issue(key, fields)
        click.echo(f"Updated {key}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@click.command(name="close")
@click.argument("key")
@click.option("--transition", "requested_transition", default="", help="Transition name or id override")
@click.option("--comment", default="", help="Optional transition comment")
def issue_close(key: str, requested_transition: str, comment: str) -> None:
    """Close an issue by transitioning it to a done/closed state."""
    try:
        client = get_jira_client()
        transition_id = resolve_transition_id(
            client,
            key,
            requested_transition,
            fallback_names=["Done", "Closed", "Resolve", "Resolved"],
        )
        client.transition_issue(key, transition_id, comment=comment or None)
        click.echo(f"Closed {key} via transition {transition_id}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@click.command(name="reopen")
@click.argument("key")
@click.option("--transition", "requested_transition", default="", help="Transition name or id override")
@click.option("--comment", default="", help="Optional transition comment")
def issue_reopen(key: str, requested_transition: str, comment: str) -> None:
    """Reopen an issue by transitioning it to an open state."""
    try:
        client = get_jira_client()
        transition_id = resolve_transition_id(
            client,
            key,
            requested_transition,
            fallback_names=["Reopen", "Reopened", "To Do", "Open", "Backlog"],
        )
        client.transition_issue(key, transition_id, comment=comment or None)
        click.echo(f"Reopened {key} via transition {transition_id}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
