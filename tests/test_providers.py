"""Tests for provider descriptors and provider-level capabilities."""

from types import SimpleNamespace

from jira_cli.providers.demo import DemoProvider
from jira_cli.providers.github import GITHUB_PROVIDER_DESCRIPTOR, GitHubProvider
from jira_cli.providers.jira import JIRA_PROVIDER_DESCRIPTOR
from jira_cli.providers.registry import ProviderRegistry


def test_jira_provider_describes_issue_filters_and_actions() -> None:
    issues = JIRA_PROVIDER_DESCRIPTOR.resource("issues")

    assert issues is not None
    assert {item.name for item in issues.filters} >= {"type", "status", "assignee", "priority", "key"}
    assert {item.name for item in issues.actions} >= {"comment", "assign", "transition"}


def test_jira_provider_describes_components_and_sprints() -> None:
    components = JIRA_PROVIDER_DESCRIPTOR.resource("components")
    sprints = JIRA_PROVIDER_DESCRIPTOR.resource("sprints")

    assert components is not None
    assert {"name", "description", "lead"} <= set(components.fields)
    assert sprints is not None
    assert {"name", "state", "startDate", "endDate", "board"} <= set(sprints.fields)


def test_jira_sprint_listing_skips_boards_without_sprints() -> None:
    from jira.exceptions import JIRAError
    from jira_cli.providers.jira import JiraProvider

    kanban = SimpleNamespace(id=1, name="Kanban")
    scrum = SimpleNamespace(id=2, name="Scrum")
    sprint = SimpleNamespace(id=7, raw={"name": "Sprint 1", "state": "active"})

    def list_sprints(board_id, **kwargs):
        if board_id == kanban.id:
            raise JIRAError(text="The board does not support sprints")
        return [sprint]

    provider = JiraProvider.__new__(JiraProvider)
    provider._jira = SimpleNamespace(
        boards=lambda **kwargs: [kanban, scrum],
        sprints=list_sprints,
    )

    assert provider.list_resource("sprints", "TIST") == [
        {"name": "Sprint 1", "state": "active", "board": "Scrum"}
    ]


def test_jira_epic_sprint_assignments_are_derived_from_children() -> None:
    from jira_cli.providers.jira import JiraProvider

    child = SimpleNamespace(
        fields=SimpleNamespace(
            parent={"key": "TIST-199"},
            model_extra={"customfield_10020": [{"id": 6072}, {"id": 6073}, {"id": 6072}]},
        )
    )
    calls = []
    provider = JiraProvider.__new__(JiraProvider)
    provider._sprint_field_id = None
    provider._jira = SimpleNamespace(
        fields=lambda: [
            {"id": "customfield_10030", "name": "Sprint", "schema": {"custom": "legacy:sprint"}},
            {
                "id": "customfield_10020",
                "name": "Sprint",
                "schema": {"custom": "com.pyxis.greenhopper.jira:gh-sprint"},
            },
        ]
    )
    provider.search = lambda jql, **kwargs: calls.append((jql, kwargs)) or SimpleNamespace(issues=[child], total=1)

    assert provider.list_epic_sprint_assignments("TIST") == {"TIST-199": ["6072", "6073"]}
    assert calls[0][1]["fields"] == ["summary", "parent", "customfield_10020"]


def test_github_milestones_are_provider_neutral_timeline_items() -> None:
    from jira_cli.providers.github import _github_milestone_timeline_items

    milestone = SimpleNamespace(
        number=4,
        title="0.7.0",
        state="open",
        due_on="2026-12-31T23:59:59Z",
        html_url="https://github.com/acme/app/milestone/4",
    )
    issue = SimpleNamespace(created_at="2026-09-10T12:00:00Z")

    class Rest:
        class Issues:
            list_milestones = object()
            list_for_repo = object()

        issues = Issues()

        def paginate(self, endpoint, **kwargs):
            return [milestone] if endpoint is self.issues.list_milestones else [issue]

    items = _github_milestone_timeline_items(SimpleNamespace(rest=Rest()), "acme", "app")

    assert len(items) == 1
    assert items[0].key == "app#M4"
    assert items[0].issue_type == "Milestone"
    assert items[0].start.isoformat() == "2026-09-10"
    assert items[0].end.isoformat() == "2026-12-31"
    assert items[0].target_url.endswith("/milestone/4")


def test_gitlab_context_resolves_project_path() -> None:
    from jira_cli.providers.registry import gitlab_context

    context = gitlab_context("/group/subgroup/project/")

    assert context.provider == "gitlab"
    assert context.target == "group/subgroup/project"
    assert context.label == "GitLab / group/subgroup/project"


def test_gitlab_validation_reports_missing_token(monkeypatch) -> None:
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    context = ProviderRegistry(load_env=False).resolve_context(provider="gitlab", project="group/project")

    warning = ProviderRegistry(load_env=False).validate_context(context)

    assert warning is not None
    assert "GITLAB_TOKEN" in warning


def test_gitlab_timeline_items_use_milestone_dates_and_issues() -> None:
    from jira_cli.providers.gitlab import GitLabProvider

    milestone = SimpleNamespace(
        id=17,
        title="Release 17",
        state="active",
        start_date=None,
        due_date="2026-12-01",
        web_url="https://gitlab.com/group/project/-/milestones/17",
    )
    issue = SimpleNamespace(created_at="2026-08-15T12:00:00Z")
    project = SimpleNamespace(
        milestones=SimpleNamespace(list=lambda **kwargs: [milestone]),
        issues=SimpleNamespace(list=lambda **kwargs: [issue]),
    )
    provider = GitLabProvider.__new__(GitLabProvider)
    provider.project = project
    provider.project_key = "group/project"

    items = provider.list_timeline_items("group/project")

    assert len(items) == 1
    assert items[0].key == "M17"
    assert items[0].issue_type == "Milestone"
    assert items[0].start.isoformat() == "2026-08-15"
    assert items[0].end.isoformat() == "2026-12-01"


def test_gitlab_user_email_uses_private_email_only_for_current_user() -> None:
    from jira_cli.providers.gitlab import GitLabProvider

    current = SimpleNamespace(id=1, username="me", name="Current User", email="me@example.com", public_email="")
    members = [
        SimpleNamespace(id=1, username="me", name="Current User", public_email=""),
        SimpleNamespace(id=2, username="other", name="Other User", public_email="other@example.com"),
        SimpleNamespace(id=3, username="private", name="Private User", public_email=""),
    ]
    provider = GitLabProvider.__new__(GitLabProvider)
    provider._gitlab = SimpleNamespace(user=current, auth=lambda: None)
    provider._gitlab_admin = None
    provider._admin_email_cache = {}
    provider.project = SimpleNamespace(members_all=SimpleNamespace(list=lambda **kwargs: members))

    assert provider.get_current_user()["emailAddress"] == "me@example.com"
    users = provider.list_assignable_users("group/project")
    assert users[0]["emailAddress"] == "me@example.com"
    assert users[1]["emailAddress"] == "other@example.com"
    assert users[2]["emailAddress"] == "-"


def test_gitlab_admin_token_opt_in_resolves_private_member_email() -> None:
    from jira_cli.providers.gitlab import GitLabProvider

    current = SimpleNamespace(id=1, username="me", name="Current User", email="me@example.com", public_email="")
    members = [
        SimpleNamespace(id=1, username="me", name="Current User", public_email=""),
        SimpleNamespace(id=2, username="other", name="Other User", public_email=""),
    ]
    admin_users = SimpleNamespace(users=SimpleNamespace(get=lambda user_id: SimpleNamespace(email="private@example.com")))
    provider = GitLabProvider.__new__(GitLabProvider)
    provider._gitlab = SimpleNamespace(user=current, auth=lambda: None)
    provider._gitlab_admin = admin_users
    provider._admin_email_cache = {}
    provider.project = SimpleNamespace(members_all=SimpleNamespace(list=lambda **kwargs: members))

    users = provider.list_assignable_users("group/project")

    assert users[0]["emailAddress"] == "me@example.com"
    assert users[1]["emailAddress"] == "private@example.com"


def test_jira_start_date_field_prefers_standard_cloud_field(monkeypatch) -> None:
    from jira_cli.providers.jira import JiraProvider

    monkeypatch.delenv("JIRA_START_DATE_FIELD", raising=False)
    provider = JiraProvider.__new__(JiraProvider)
    provider._start_date_field = None
    provider._jira = SimpleNamespace(
        fields=lambda: [
            {"id": "customfield_10040", "name": "Start Date", "schema": {"type": "date"}},
            {"id": "customfield_10015", "name": "Start date", "schema": {"type": "date"}},
        ]
    )

    assert provider.start_date_field() == "customfield_10015"


def test_jira_start_date_field_honors_override(monkeypatch) -> None:
    from jira_cli.providers.jira import JiraProvider

    monkeypatch.setenv("JIRA_START_DATE_FIELD", "customfield_12345")
    provider = JiraProvider.__new__(JiraProvider)
    provider._start_date_field = None

    assert provider.start_date_field() == "customfield_12345"


def test_demo_provider_describes_same_core_resources() -> None:
    descriptor = DemoProvider().describe()

    assert descriptor.name == "demo"
    assert descriptor.resource("issues") is not None
    assert descriptor.resource("users") is not None
    assert descriptor.resource("versions") is not None


def test_github_provider_describes_resources() -> None:
    issues = GITHUB_PROVIDER_DESCRIPTOR.resource("issues")
    labels = GITHUB_PROVIDER_DESCRIPTOR.resource("labels")

    assert issues is not None
    assert labels is not None
    assert GITHUB_PROVIDER_DESCRIPTOR.query_language == "GitHub issue query"
    assert {item.name for item in issues.filters} >= {"status", "assignee", "label", "milestone", "key"}
    assert {item.name for item in issues.sorts} >= {"created", "updated", "comments"}
    assert {item.name for item in issues.actions} >= {"transition", "assign", "comment"}
    assert {item.name for item in labels.actions} == {"create", "edit", "delete"}


def test_descriptor_resource_lookup_returns_none_for_unknown_kind() -> None:
    assert DemoProvider().describe().resource("unknown") is None


def test_registry_always_exposes_demo_context(monkeypatch) -> None:
    monkeypatch.delenv("JIRA_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(ProviderRegistry, "github_token", staticmethod(lambda: ""))

    contexts = ProviderRegistry(load_env=False).available_contexts()

    assert [context.name for context in contexts] == ["demo"]


def test_registry_resolves_explicit_demo_target() -> None:
    context = ProviderRegistry(load_env=False).resolve_context(provider="demo", project="SANDBOX")

    assert context.provider == "demo"
    assert context.target == "SANDBOX"
    assert context.label == "Demo / SANDBOX"


def test_jira_validation_reports_missing_token(monkeypatch) -> None:
    monkeypatch.setenv("JIRA_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

    registry = ProviderRegistry(load_env=False)
    context = registry.resolve_context(provider="jira", project="DEMO")

    warning = registry.validate_context(context)
    assert warning is not None
    assert "missing JIRA_API_TOKEN" in warning
    assert "https://id.atlassian.com/manage-profile/security/api-tokens" in warning


def test_github_validation_reports_missing_token(monkeypatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(ProviderRegistry, "github_token", staticmethod(lambda: ""))

    registry = ProviderRegistry(load_env=False)
    context = registry.resolve_context(provider="github", repository="owner/repo")

    assert registry.validate_context(context).startswith("GitHub / owner/repo validation failed:")


def test_registry_resolves_jira_context_from_env(monkeypatch) -> None:
    monkeypatch.setenv("JIRA_PROJECT", "COM")
    monkeypatch.setenv("JIRA_URL", "https://herrenknecht.atlassian.net")

    context = ProviderRegistry(load_env=False).resolve_context(provider="jira")

    assert context.name == "jira:COM"
    assert context.provider == "jira"
    assert context.target == "COM"
    assert context.label == "Jira / COM (herrenknecht)"


def test_registry_resolves_explicit_github_repository() -> None:
    context = ProviderRegistry(load_env=False).resolve_context(provider="github", repository="colenio/jira-cli")

    assert context.name == "github:colenio/jira-cli"
    assert context.provider == "github"
    assert context.target == "colenio/jira-cli"


def test_registry_parses_github_remotes() -> None:
    assert ProviderRegistry.parse_github_remote("git@github.com:colenio/jira-cli.git") == "colenio/jira-cli"
    assert ProviderRegistry.parse_github_remote("https://github.com/colenio/jira-cli.git") == "colenio/jira-cli"
    assert ProviderRegistry.parse_github_remote("git@github.com:acme/repo.with.dots.git") == "acme/repo.with.dots"


def test_github_provider_descriptor_method_without_network() -> None:
    provider = GitHubProvider.__new__(GitHubProvider)

    assert provider.describe().name == "github"


def test_github_assignee_me_resolves_to_current_user() -> None:
    from jira_cli.providers.github import GitHubProjectProvider

    repo_provider = GitHubProvider.__new__(GitHubProvider)
    repo_provider.get_current_user = lambda: {"accountId": "mkoertgen"}
    assert repo_provider._resolve_login("me") == "mkoertgen"
    assert repo_provider._resolve_login("@me") == "mkoertgen"

    project_provider = GitHubProjectProvider.__new__(GitHubProjectProvider)
    project_provider.get_current_user = lambda: {"accountId": "mkoertgen"}
    assert project_provider._resolve_assignee_login("me") == "mkoertgen"


def test_github_label_dict_includes_issue_count() -> None:
    from jira_cli.providers.github import _label_dict

    class Label:
        name = "bug"
        color = "d73a4a"
        description = "Something is not working"

    assert _label_dict(Label(), issue_count=3) == {
        "name": "bug",
        "color": "d73a4a",
        "description": "Something is not working",
        "issueCount": 3,
    }


def test_github_repository_find_children_uses_sub_issue_endpoint() -> None:
    from jira_cli.providers.github import GitHubProvider

    class Response:
        def json(self):
            return [
                {
                    "number": 7,
                    "title": "Child issue",
                    "state": "open",
                    "body": "Details",
                    "updated_at": "2026-09-16T10:00:00Z",
                    "labels": [],
                    "assignees": [],
                    "user": {"login": "ada", "name": "Ada Lovelace"},
                }
            ]

    calls = []
    provider = GitHubProvider.__new__(GitHubProvider)
    provider._delegate = None
    provider._owner = "colenio"
    provider._repo_name = "jira-cli"
    provider._github = type("GitHub", (), {"request": lambda _, *args, **kwargs: calls.append((args, kwargs)) or Response()})()

    children = provider.find_children("#42")

    assert children[0].key == "#7"
    assert children[0].parent_key == "#42"
    assert calls[0][0] == ("GET", "/repos/colenio/jira-cli/issues/42/sub_issues")


def test_parse_project_target() -> None:
    from jira_cli.providers.github import parse_project_target

    assert parse_project_target("colenio/21") == ("colenio", 21)
    assert parse_project_target("orgs/colenio/projects/21") == ("colenio", 21)
    assert parse_project_target("21", default_owner="colenio") == ("colenio", 21)


def test_registry_resolves_github_project_context() -> None:
    context = ProviderRegistry(load_env=False).resolve_context(provider="github-project", project="colenio/21")

    assert context.name == "github:colenio/21"
    assert context.provider == "github"
    assert context.target == "colenio/21"
    assert context.label == "GitHub Project / colenio/21"


def test_registry_auto_detects_single_context(monkeypatch) -> None:
    monkeypatch.setenv("GH_PROJECT", "colenio/21")
    monkeypatch.setattr(ProviderRegistry, "github_token", staticmethod(lambda: "ghp_fake"))

    # When no provider requested, auto-detect single available real context
    context = ProviderRegistry(load_env=False).resolve_context(interactive=False)

    assert context.provider == "github"
    assert context.target == "colenio/21"


def test_registry_interactive_context_selection(monkeypatch) -> None:
    monkeypatch.setenv("GH_PROJECT", "colenio/21")
    monkeypatch.setenv("JIRA_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    monkeypatch.setenv("JIRA_PROJECT", "COM")
    monkeypatch.setattr(ProviderRegistry, "github_token", staticmethod(lambda: "ghp_fake"))
    monkeypatch.setattr(ProviderRegistry, "validate_context", lambda self, context: None)

    # Mock interactive prompt returning option 1 (github-project)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("click.prompt", lambda prompt, type, default, err: 1)

    context = ProviderRegistry(load_env=False).resolve_context(interactive=True)

    assert context.provider == "github"
    assert context.target == "colenio/21"


def test_github_project_provider_to_jira_issue() -> None:
    from jira_cli.providers.github import GITHUB_PROVIDER_DESCRIPTOR, GitHubProjectProvider

    assert GITHUB_PROVIDER_DESCRIPTOR.supports_board is False

    provider = GitHubProjectProvider.__new__(GitHubProjectProvider)
    provider._status_options = {"Todo": "opt1", "In Progress": "opt2", "Done": "opt3"}
    provider._item_cache = {}

    assert provider.describe().supports_board is True

    node = {
        "id": "PVTI_123456",
        "type": "ISSUE",
        "content": {
            "number": 42,
            "title": "Test Issue",
            "repository": {"nameWithOwner": "colenio/jira-cli"},
            "assignees": {"nodes": [{"login": "mkoertgen", "name": "Marcel Körtgen"}]},
            "labels": {"nodes": [{"name": "enhancement"}]},
            "body": "Test body",
        },
        "fieldValueByName": {"name": "In Progress", "optionId": "opt2"},
        "updatedAt": "2026-09-13T10:00:00Z",
    }

    issue = provider._to_jira_issue(node)

    assert issue.key == "jira-cli#42"
    assert issue.fields.summary == "Test Issue"
    assert issue.fields.status == {"name": "In Progress"}
    assert issue.fields.assignee == {"accountId": "mkoertgen", "displayName": "Marcel Körtgen"}


def test_github_project_repo_filter_matches_full_and_short_names() -> None:
    from jira_cli.providers.github import _matches_item

    item = {"content": {"repository": {"nameWithOwner": "colenio/website-astro"}}}

    assert _matches_item(item, {"repo": "colenio/website-astro"})
    assert _matches_item(item, {"repo": "website-astro"})
    assert not _matches_item(item, {"repo": "colenio/jira-cli"})


def test_github_project_status_filter_handles_null_status() -> None:
    from jira_cli.providers.github import _matches_item

    item = {"fieldValueByName": {"name": None}, "content": {}}

    assert not _matches_item(item, {"status": "In Progress"})


def test_github_project_reporter_filter_matches_author() -> None:
    from jira_cli.providers.github import _matches_item

    item = {"content": {"author": {"login": "mkoertgen", "name": "Marcel Körtgen"}}}

    assert _matches_item(item, {"reporter": "mkoertgen"})
    assert _matches_item(item, {"reporter": "Marcel"})
    assert not _matches_item(item, {"reporter": "someone-else"})


def test_github_project_lists_repositories_from_items() -> None:
    from jira_cli.providers.github import GitHubProjectProvider

    provider = GitHubProjectProvider.__new__(GitHubProjectProvider)
    provider._fetch_all_items = lambda: [
        {"content": {"repository": {"nameWithOwner": "colenio/website-astro"}}},
        {"content": {"repository": {"nameWithOwner": "colenio/colenio-infra"}}},
        {"content": {"repository": {"nameWithOwner": "colenio/website-astro"}}},
        {"content": None},
    ]

    assert provider.list_issue_repositories() == ["colenio/colenio-infra", "colenio/website-astro"]


def test_github_project_create_issue_adds_created_issue_to_project() -> None:
    from jira_cli.providers.github import GitHubProjectProvider

    calls = []
    issue = SimpleNamespace(number=7, node_id="I_kwDO123", html_url="https://github.com/colenio/jira-cli/issues/7")
    issues_api = SimpleNamespace(create=lambda owner, repo, **payload: SimpleNamespace(parsed_data=issue))
    github = SimpleNamespace(
        rest=SimpleNamespace(issues=issues_api),
        graphql=lambda query, variables: calls.append((query, variables)),
    )
    provider = GitHubProjectProvider.__new__(GitHubProjectProvider)
    provider._github = github
    provider._project_id = "PVT_123"

    created = provider.create_issue("colenio/21", "New issue", repository="colenio/jira-cli")

    assert created["key"] == "jira-cli#7"
    assert calls[0][1] == {"projectId": "PVT_123", "contentId": "I_kwDO123"}


def test_github_project_comment_lookup_uses_item_repository() -> None:
    from jira_cli.providers.github import GitHubProjectProvider

    provider = GitHubProjectProvider.__new__(GitHubProjectProvider)
    provider._item_cache = {
        "colenio-infra#1": {
            "content": {
                "repository": {"nameWithOwner": "colenio/colenio-infra"},
                "number": 1,
            }
        }
    }

    class FakeComments:
        def list_comments(self, **kwargs):
            return []

    class FakeIssues:
        list_comments = FakeComments().list_comments

    class FakeRest:
        issues = FakeIssues()

        @staticmethod
        def paginate(method, **kwargs):
            assert kwargs == {"owner": "colenio", "repo": "colenio-infra", "issue_number": 1, "per_page": 100}
            return []

    class FakeGithub:
        rest = FakeRest()

    provider._github = FakeGithub()

    assert provider.get_issue_comments("colenio-infra#1") == []
