"""Unified GitHub provider supporting both Repository Issues (REST) and Project V2 Boards (GraphQL)."""

from __future__ import annotations

from datetime import timezone
import re
from typing import Any, Optional

from githubkit import GitHub

from jira_cli.models import JiraIssue, JiraIssueField, JiraSearchResult

from .base import ActionDescriptor, FilterDescriptor, ProviderDescriptor, ResourceDescriptor, SortDescriptor

_REPO_GITHUB_PROVIDER_DESCRIPTOR = ProviderDescriptor(
    name="github",
    query_language="GitHub issue query",
    supports_board=False,
    resources=(
        ResourceDescriptor(
            kind="issues",
            fields=("key", "summary", "status", "assignee", "reporter", "labels", "milestone", "updated"),
            filters=(
                FilterDescriptor(name="status", field="state"),
                FilterDescriptor(name="assignee", field="assignee", special_values=("me",)),
                FilterDescriptor(name="reporter", field="author"),
                FilterDescriptor(name="label", field="labels"),
                FilterDescriptor(name="milestone", field="milestone"),
                FilterDescriptor(name="key", field="number"),
            ),
            sorts=(
                SortDescriptor(name="created", field="created", default_direction="desc"),
                SortDescriptor(name="updated", field="updated", default_direction="desc"),
                SortDescriptor(name="comments", field="comments", default_direction="desc"),
            ),
            actions=(
                ActionDescriptor(name="transition", requires_comment=False),
                ActionDescriptor(name="assign", requires_comment=False),
                ActionDescriptor(name="comment", requires_comment=False),
            ),
        ),
        ResourceDescriptor(
            kind="users",
            fields=("displayName", "emailAddress", "active", "accountId"),
            filters=(FilterDescriptor(name="query", field="query"),),
        ),
        ResourceDescriptor(
            kind="versions",
            fields=("name", "description", "releaseDate", "released", "archived"),
        ),
        ResourceDescriptor(
            kind="labels",
            fields=("name", "color", "description", "issueCount"),
        ),
    ),
)


def is_project_target(target: str) -> bool:
    """Check if target represents a GitHub Project V2 target (owner/number, orgs/owner/projects/number, or digits)."""
    if not target:
        return False
    cleaned = target.strip().strip("/")
    parts = [p for p in cleaned.split("/") if p and p not in ("orgs", "users", "projects")]
    if len(parts) == 2 and parts[1].isdigit():
        return True
    if len(parts) == 1 and parts[0].isdigit():
        return True
    return False


def parse_project_target(target: str, default_owner: str = "") -> tuple[str, int]:
    """Parse owner and project number from target strings like colenio/21 or orgs/colenio/projects/21."""
    cleaned = target.strip().strip("/")
    parts = [p for p in cleaned.split("/") if p and p not in ("orgs", "users", "projects")]
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], int(parts[1])
    if len(parts) == 1 and parts[0].isdigit() and default_owner:
        return default_owner, int(parts[0])
    raise ValueError(
        f"Invalid GitHub Project target '{target}'. Expected 'owner/number' (e.g. 'colenio/21') or 'orgs/owner/projects/21'."
    )


class GitHubProjectProvider:
    """Provider for GitHub Projects V2 (boards) backed by GraphQL."""

    dry_run = False

    def __init__(self, target: str, token: str, default_owner: str = ""):
        self.target = target
        self.owner, self.number = parse_project_target(target, default_owner=default_owner)
        self.base_url = f"https://github.com/orgs/{self.owner}/projects/{self.number}"
        self._github = GitHub(token)

        self._project_id: str = ""
        self._project_title: str = f"GitHub Project #{self.number}"
        self._status_field_id: str = ""
        self._status_options: dict[str, str] = {}  # name -> option_id
        self._option_id_to_name: dict[str, str] = {}
        self._item_cache: dict[str, dict[str, Any]] = {}  # issue_key -> item_info

        self._ensure_meta()

    def _ensure_meta(self) -> None:
        """Fetch project ID, title, and status field configuration."""
        if self._project_id and self._status_field_id:
            return

        query_org = """
        query GetOrgProjectMeta($owner: String!, $number: Int!) {
          organization(login: $owner) {
            projectV2(number: $number) {
              id
              title
              fields(first: 50) {
                nodes {
                  ... on ProjectV2SingleSelectField {
                    id
                    name
                    options {
                      id
                      name
                    }
                  }
                }
              }
            }
          }
        }
        """
        query_user = """
        query GetUserProjectMeta($owner: String!, $number: Int!) {
          user(login: $owner) {
            projectV2(number: $number) {
              id
              title
              fields(first: 50) {
                nodes {
                  ... on ProjectV2SingleSelectField {
                    id
                    name
                    options {
                      id
                      name
                    }
                  }
                }
              }
            }
          }
        }
        """
        project_data = None
        try:
            data = self._github.graphql(query_org, {"owner": self.owner, "number": self.number})
            if isinstance(data, dict):
                project_data = (data.get("organization") or {}).get("projectV2")
        except Exception:
            pass

        if not project_data:
            try:
                data = self._github.graphql(query_user, {"owner": self.owner, "number": self.number})
                if isinstance(data, dict):
                    project_data = (data.get("user") or {}).get("projectV2")
            except Exception:
                pass

        if not project_data:
            raise ValueError(f"GitHub Project V2 #{self.number} not found for '{self.owner}'.")

        self._project_id = project_data.get("id", "")
        self._project_title = project_data.get("title", f"GitHub Project #{self.number}")

        fields = project_data.get("fields", {}).get("nodes", [])
        for field in fields:
            if isinstance(field, dict) and field.get("name") == "Status":
                self._status_field_id = field.get("id", "")
                options = field.get("options", [])
                for opt in options:
                    if isinstance(opt, dict) and "name" in opt and "id" in opt:
                        self._status_options[opt["name"]] = opt["id"]
                        self._option_id_to_name[opt["id"]] = opt["name"]
                break

    def get_issue_url(self, key: str) -> str:
        """Return the web URL for an issue key."""
        cached = self._item_cache.get(key)
        if cached and isinstance(cached.get("content"), dict):
            url = cached["content"].get("url")
            if url:
                return url
        return self.base_url

    def describe(self) -> ProviderDescriptor:
        """Describe GitHub Project V2 resources, filters, and actions."""
        status_names = tuple(self._status_options.keys()) if self._status_options else ("Todo", "In Progress", "Done")
        return ProviderDescriptor(
            name="github",
            query_language="GitHub project filter",
            supports_board=True,
            resources=(
                ResourceDescriptor(
                    kind="issues",
                    fields=("key", "summary", "status", "assignee", "reporter", "labels", "updated", "issuetype"),
                    filters=(
                        FilterDescriptor(name="status", field="status", special_values=status_names),
                        FilterDescriptor(name="assignee", field="assignee", special_values=("me",)),
                        FilterDescriptor(name="reporter", field="author"),
                        FilterDescriptor(name="label", field="labels"),
                        FilterDescriptor(name="repo", field="repository"),
                        FilterDescriptor(name="type", field="type"),
                    ),
                    sorts=(
                        SortDescriptor(name="updated", field="updated", default_direction="desc"),
                        SortDescriptor(name="key", field="key", default_direction="asc"),
                    ),
                    actions=(
                        ActionDescriptor(name="transition", requires_comment=False),
                        ActionDescriptor(name="comment", requires_comment=True),
                        ActionDescriptor(name="assign", requires_comment=False),
                    ),
                ),
                ResourceDescriptor(
                    kind="users",
                    fields=("displayName", "emailAddress", "active", "accountId"),
                    filters=(FilterDescriptor(name="query", field="query"),),
                ),
                ResourceDescriptor(
                    kind="labels",
                    fields=("name", "color", "description", "issueCount"),
                ),
            ),
        )

    def search(
        self,
        jql: str,
        fields: Optional[list[str]] = None,
        start_at: int = 0,
        max_results: int = 50,
        expand: Optional[list[str]] = None,
    ) -> JiraSearchResult:
        """Search items on the project board with optional filter string."""
        filters = _parse_filter_string(jql)
        items = self._fetch_all_items()

        # Apply filters
        filtered = []
        for item in items:
            if _matches_item(item, filters):
                filtered.append(item)

        issues = [self._to_jira_issue(item) for item in filtered[start_at : start_at + max_results]]
        return JiraSearchResult(
            issues=issues,
            total=len(filtered),
            startAt=start_at,
            maxResults=max_results,
        )

    def _fetch_all_items(self) -> list[dict[str, Any]]:
        """Fetch all Project V2 items with GraphQL pagination."""
        query_org = """
        query GetOrgProjectItems($owner: String!, $number: Int!, $first: Int!, $after: String) {
          organization(login: $owner) {
            projectV2(number: $number) {
              items(first: $first, after: $after) {
                totalCount
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  id
                  type
                  updatedAt
                  content {
                    ... on Issue {
                      id
                      number
                      title
                                            author { login name }
                      state
                      body
                      url
                      repository { nameWithOwner }
                      assignees(first: 10) { nodes { login name } }
                      labels(first: 10) { nodes { name } }
                    }
                    ... on PullRequest {
                      id
                      number
                      title
                                            author { login name }
                      state
                      body
                      url
                      repository { nameWithOwner }
                      assignees(first: 10) { nodes { login name } }
                      labels(first: 10) { nodes { name } }
                    }
                    ... on DraftIssue {
                      id
                      title
                      body
                    }
                  }
                  fieldValueByName(name: "Status") {
                    ... on ProjectV2ItemFieldSingleSelectValue {
                      name
                      optionId
                    }
                  }
                }
              }
            }
          }
        }
        """

        query_user = """
        query GetUserProjectItems($owner: String!, $number: Int!, $first: Int!, $after: String) {
          user(login: $owner) {
            projectV2(number: $number) {
              items(first: $first, after: $after) {
                totalCount
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  id
                  type
                  updatedAt
                  content {
                    ... on Issue {
                      id
                      number
                      title
                                            author { login name }
                      state
                      body
                      url
                      repository { nameWithOwner }
                      assignees(first: 10) { nodes { login name } }
                      labels(first: 10) { nodes { name } }
                    }
                    ... on PullRequest {
                      id
                      number
                      title
                                            author { login name }
                      state
                      body
                      url
                      repository { nameWithOwner }
                      assignees(first: 10) { nodes { login name } }
                      labels(first: 10) { nodes { name } }
                    }
                    ... on DraftIssue {
                      id
                      title
                      body
                    }
                  }
                  fieldValueByName(name: "Status") {
                    ... on ProjectV2ItemFieldSingleSelectValue {
                      name
                      optionId
                    }
                  }
                }
              }
            }
          }
        }
        """

        all_nodes = []
        has_next = True
        cursor = None
        use_user_query = False

        while has_next:
            query = query_user if use_user_query else query_org
            try:
                data = self._github.graphql(
                    query,
                    {"owner": self.owner, "number": self.number, "first": 50, "after": cursor},
                )
            except Exception:
                if not use_user_query:
                    use_user_query = True
                    continue
                break

            project_data = None
            if isinstance(data, dict):
                org_data = data.get("organization") or {}
                user_data = data.get("user") or {}
                project_data = org_data.get("projectV2") or user_data.get("projectV2")

            if not project_data and not use_user_query:
                use_user_query = True
                continue

            if not project_data:
                break

            items_data = project_data.get("items", {})
            nodes = items_data.get("nodes", [])
            all_nodes.extend(nodes)

            page_info = items_data.get("pageInfo", {})
            has_next = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

        return all_nodes

    def _to_jira_issue(self, node: dict[str, Any]) -> JiraIssue:
        """Convert a ProjectV2Item GraphQL node into a JiraIssue."""
        item_id = node.get("id", "")
        item_type = node.get("type", "ISSUE")
        content = node.get("content") or {}
        status_val = node.get("fieldValueByName") or {}

        status_name = status_val.get("name") if isinstance(status_val, dict) else ""
        if not status_name:
            status_name = "No Status"

        # Generate readable issue key
        if item_type in ("ISSUE", "PULL_REQUEST"):
            repo_full = content.get("repository", {}).get("nameWithOwner", "")
            repo_short = repo_full.split("/")[-1] if "/" in repo_full else repo_full
            number = content.get("number")
            key = f"{repo_short}#{number}" if repo_short else f"#{number}"
        else:
            key = f"DRAFT#{item_id[-6:]}"

        # Store in item cache
        self._item_cache[key] = {
            "item_id": item_id,
            "item_type": item_type,
            "content": content,
            "status_name": status_name,
        }

        assignees_nodes = content.get("assignees", {}).get("nodes", []) if isinstance(content, dict) else []
        assignee_dict = None
        if assignees_nodes:
            first = assignees_nodes[0]
            assignee_dict = {
                "accountId": first.get("login", ""),
                "displayName": first.get("name") or first.get("login", ""),
            }

        author = content.get("author") or {}
        reporter_dict = None
        if isinstance(author, dict) and author.get("login"):
            reporter_dict = {
                "accountId": author["login"],
                "displayName": author.get("name") or author["login"],
            }

        labels_nodes = content.get("labels", {}).get("nodes", []) if isinstance(content, dict) else []
        labels_list = [l["name"] for l in labels_nodes if isinstance(l, dict) and "name" in l]

        issuetype_name = "Story" if item_type == "ISSUE" else ("PullRequest" if item_type == "PULL_REQUEST" else "Draft")

        fields = JiraIssueField(
            summary=content.get("title", "Untitled") if isinstance(content, dict) else "Untitled",
            status={"name": status_name},
            assignee=assignee_dict,
            reporter=reporter_dict,
            issuetype={"name": issuetype_name},
            labels=labels_list,
            description=content.get("body", "") if isinstance(content, dict) else "",
            updated=node.get("updatedAt"),
        )

        return JiraIssue(key=key, fields=fields)

    def list_transitions(self, issue_key: str) -> list[dict]:
        """Return available status transitions for an item on this board."""
        cached = self._item_cache.get(issue_key, {})
        current_status = cached.get("status_name", "")

        transitions = []
        for name in self._status_options.keys():
            if name != current_status:
                transitions.append({"id": name, "name": name, "to": {"name": name}})
        return transitions

    def get_transitions(self, issue_key: str) -> list[dict]:
        """Alias for list_transitions to satisfy IssueTrackerProvider / workflow feature contract."""
        return self.list_transitions(issue_key)

    def transition_issue(self, issue_key: str, transition_id: str, comment: Optional[str] = None) -> bool:
        """Update an item's status in Project V2 via GraphQL mutation."""
        cached = self._item_cache.get(issue_key)
        if not cached:
            # Refresh search if missing
            self.search("")
            cached = self._item_cache.get(issue_key)

        if not cached:
            raise ValueError(f"Item '{issue_key}' not found on project board.")

        item_id = cached["item_id"]
        option_id = self._status_options.get(transition_id)
        if not option_id:
            raise ValueError(
                f"Unknown status '{transition_id}'. Available options: {list(self._status_options.keys())}"
            )

        if not self._status_field_id or not self._project_id:
            self._ensure_meta()

        mutation = """
        mutation UpdateStatus($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
          updateProjectV2ItemFieldValue(
            input: {
              projectId: $projectId
              itemId: $itemId
              fieldId: $fieldId
              value: { singleSelectOptionId: $optionId }
            }
          ) {
            projectV2Item {
              id
            }
          }
        }
        """

        self._github.graphql(
            mutation,
            {
                "projectId": self._project_id,
                "itemId": item_id,
                "fieldId": self._status_field_id,
                "optionId": option_id,
            },
        )

        # Update cache
        cached["status_name"] = transition_id

        # Post comment if provided and content is an Issue/PR
        if comment and cached.get("content"):
            content = cached["content"]
            repo_full = content.get("repository", {}).get("nameWithOwner", "")
            number = content.get("number")
            if repo_full and number:
                owner, repo_name = repo_full.split("/", 1)
                self._github.rest.issues.create_comment(owner, repo_name, number, body=comment)

        return True

    def add_comment(self, issue_key: str, body: str | dict, use_adf: bool = False) -> dict:
        """Add a comment to a board item's underlying GitHub issue or PR."""
        cached = self._item_cache.get(issue_key)
        if not cached:
            self.search("")
            cached = self._item_cache.get(issue_key)

        if not cached:
            raise ValueError(f"Item '{issue_key}' not found on project board.")

        content = cached.get("content") or {}
        repo_full = content.get("repository", {}).get("nameWithOwner", "")
        number = content.get("number")

        if not repo_full or not number:
            raise ValueError(f"Item '{issue_key}' is a draft or does not support comments.")

        owner, repo_name = repo_full.split("/", 1)
        text = body if isinstance(body, str) else str(body)
        res = self._github.rest.issues.create_comment(owner, repo_name, number, body=text).parsed_data
        return {"id": str(res.id), "body": res.body}

    def update_issue(self, issue_key: str, fields: dict) -> None:
        """Update canonical fields on a project item's underlying issue or PR."""
        cached = self._item_cache.get(issue_key)
        if not cached:
            self.search("")
            cached = self._item_cache.get(issue_key)
        if not cached:
            raise ValueError(f"Item '{issue_key}' not found on project board.")

        content = cached.get("content") or {}
        repo_full = content.get("repository", {}).get("nameWithOwner", "")
        number = content.get("number")
        if not repo_full or not number:
            raise ValueError(f"Item '{issue_key}' is a draft or does not support updates.")

        update_fields = {}
        if fields.get("summary"):
            update_fields["title"] = fields["summary"]
        if "description" in fields:
            update_fields["body"] = fields["description"]
        if "labels" in fields:
            update_fields["labels"] = fields["labels"]
        if fields.get("assignee"):
            update_fields["assignees"] = [self._resolve_assignee_login(fields["assignee"])]
        if not update_fields:
            raise ValueError("No supported issue fields supplied")

        owner, repo_name = repo_full.split("/", 1)
        self._github.rest.issues.update(owner, repo_name, number, **update_fields)
        content.update({"title": fields.get("summary", content.get("title")), "body": fields.get("description", content.get("body", ""))})

    def update_issue(self, issue_key: str, fields: dict) -> None:
        """Update the title of a project item's underlying issue or pull request."""
        cached = self._item_cache.get(issue_key)
        if not cached:
            self.search("")
            cached = self._item_cache.get(issue_key)
        if not cached:
            raise ValueError(f"Item '{issue_key}' not found on project board.")

        title = fields.get("summary", fields.get("title"))
        if not title:
            raise ValueError("GitHub Project item update currently supports title/summary only")

        content = cached.get("content") or {}
        repo_full = content.get("repository", {}).get("nameWithOwner", "")
        number = content.get("number")
        if not repo_full or not number:
            raise ValueError(f"Item '{issue_key}' is a draft or does not support title updates.")

        owner, repo_name = repo_full.split("/", 1)
        self._github.rest.issues.update(owner, repo_name, number, title=title)
        content["title"] = title

    def assign_issue(self, issue_key: str, assignee: str) -> bool:
        """Assign an issue/PR on the project board to a user."""
        cached = self._item_cache.get(issue_key)
        if not cached:
            self.search("")
            cached = self._item_cache.get(issue_key)

        if not cached:
            raise ValueError(f"Item '{issue_key}' not found on project board.")

        assignee_login = self._resolve_assignee_login(assignee)

        content = cached.get("content") or {}
        repo_full = content.get("repository", {}).get("nameWithOwner", "")
        number = content.get("number")

        if not repo_full or not number:
            raise ValueError(f"Item '{issue_key}' is a draft or does not support assignment.")

        owner, repo_name = repo_full.split("/", 1)
        self._github.rest.issues.update(owner, repo_name, number, assignees=[assignee_login] if assignee_login else [])
        return True

    def _resolve_assignee_login(self, input_val: str) -> str:
        input_clean = input_val.strip().lstrip("@")
        if not input_clean:
            return ""

        users = self.list_assignable_users(self.owner, max_results=100)
        for u in users:
            if u.get("accountId", "").casefold() == input_clean.casefold():
                return u["accountId"]
        for u in users:
            if u.get("displayName", "").casefold() == input_clean.casefold():
                return u["accountId"]
        for u in users:
            if input_clean.casefold() in u.get("displayName", "").casefold() or input_clean.casefold() in u.get("accountId", "").casefold():
                return u["accountId"]

        return input_clean

    def get_current_user(self) -> dict:
        """Return authenticated user."""
        user = self._github.rest.users.get_authenticated().parsed_data
        return {
            "accountId": user.login,
            "displayName": user.name or user.login,
            "emailAddress": user.email or "-",
            "active": True,
        }

    def list_labels(self, project_key: str) -> list[dict]:
        """Return distinct labels present on project items."""
        items = self._fetch_all_items()
        label_counts: dict[str, int] = {}
        for item in items:
            content = item.get("content") or {}
            labels = content.get("labels", {}).get("nodes", []) if isinstance(content, dict) else []
            for l in labels:
                if isinstance(l, dict) and "name" in l:
                    name = l["name"]
                    label_counts[name] = label_counts.get(name, 0) + 1

        return [
            {"name": name, "color": "0052cc", "description": "", "issueCount": count}
            for name, count in sorted(label_counts.items())
        ]

    def list_versions(self, project_key: str) -> list[dict]:
        """Return empty list for versions on board."""
        return []

    def list_assignable_users(self, project_key: str, max_results: int = 50) -> list[dict]:
        """Return assignees from org members, project repos, items, and current user."""
        users_dict: dict[str, dict] = {}

        # 1. Current user
        try:
            curr = self.get_current_user()
            users_dict[curr["accountId"]] = curr
        except Exception:
            pass

        # 2. Org members if owner is an organization
        try:
            members = self._github.rest.paginate(self._github.rest.orgs.list_members, org=self.owner, per_page=100)
            for m in members:
                login = getattr(m, "login", "") or (m.get("login", "") if isinstance(m, dict) else "")
                if login and login not in users_dict:
                    users_dict[login] = {"accountId": login, "displayName": login, "active": True}
        except Exception:
            pass

        # 3. Item assignees from project board
        items = self._fetch_all_items()
        for item in items:
            content = item.get("content") or {}
            assignees = content.get("assignees", {}).get("nodes", []) if isinstance(content, dict) else []
            for a in assignees:
                if isinstance(a, dict) and "login" in a:
                    login = a["login"]
                    display_name = a.get("name") or login
                    if login not in users_dict or users_dict[login].get("displayName") == login:
                        users_dict[login] = {"accountId": login, "displayName": display_name, "active": True}

        return list(users_dict.values())[:max_results]

    def find_assignable_users(self, project_key: str, query: str, max_results: int = 20) -> list[dict]:
        """Search assignees by displayName or accountId for autocomplete."""
        query_lower = query.casefold()
        users = [
            u
            for u in self.list_assignable_users(project_key, max_results=100)
            if query_lower in u.get("displayName", "").casefold() or query_lower in u.get("accountId", "").casefold()
        ]
        return users[:max_results]


def _parse_filter_string(query_str: str) -> dict[str, str]:
    """Parse key=value filters from query string."""
    filters = {}
    if not query_str:
        return filters

    pairs = re.findall(r'(\w+)\s*=\s*(?:"([^"]+)"|\'([^\']+)\'|(\S+))', query_str)
    for key, v1, v2, v3 in pairs:
        val = v1 or v2 or v3
        filters[key.lower()] = val
    return filters


def _matches_item(item: dict[str, Any], filters: dict[str, str]) -> bool:
    """Check if item matches parsed filters."""
    if not filters:
        return True

    content = item.get("content") or {}
    status_val = item.get("fieldValueByName") or {}
    status_name = status_val.get("name") if isinstance(status_val, dict) else ""
    status_name = status_name or "No Status"

    if "status" in filters:
        target = filters["status"].casefold()
        if target != status_name.casefold():
            return False

    if "assignee" in filters:
        target_assignee = filters["assignee"].casefold()
        assignees = content.get("assignees", {}).get("nodes", []) if isinstance(content, dict) else []
        matched = any(
            target_assignee in a.get("login", "").casefold() or target_assignee in a.get("name", "").casefold()
            for a in assignees
            if isinstance(a, dict)
        )
        if not matched:
            return False

    if "reporter" in filters:
        target_reporter = filters["reporter"].casefold()
        author = content.get("author") or {}
        login = author.get("login", "").casefold() if isinstance(author, dict) else ""
        name = author.get("name", "").casefold() if isinstance(author, dict) else ""
        if target_reporter not in login and target_reporter not in name:
            return False

    if "label" in filters:
        target_label = filters["label"].casefold()
        labels = content.get("labels", {}).get("nodes", []) if isinstance(content, dict) else []
        matched = any(target_label == l.get("name", "").casefold() for l in labels if isinstance(l, dict))
        if not matched:
            return False

    if "repo" in filters:
        target_repo = filters["repo"].casefold()
        repository = content.get("repository", {}) if isinstance(content, dict) else {}
        full_name = repository.get("nameWithOwner", "").casefold()
        short_name = full_name.rsplit("/", 1)[-1]
        if target_repo not in (full_name, short_name):
            return False

    return True

GITHUB_PROVIDER_DESCRIPTOR = _REPO_GITHUB_PROVIDER_DESCRIPTOR


def is_project_target(target: str) -> bool:
    """Check if target represents a GitHub Project V2 target (owner/number, orgs/owner/projects/number, or digits)."""
    if not target:
        return False
    cleaned = target.strip().strip("/")
    parts = [p for p in cleaned.split("/") if p and p not in ("orgs", "users", "projects")]
    if len(parts) == 2 and parts[1].isdigit():
        return True
    if len(parts) == 1 and parts[0].isdigit():
        return True
    return False


class GitHubProvider:
    """Unified GitHub provider dispatching to Repo REST or Project V2 GraphQL depending on target."""

    dry_run = False

    def __init__(self, target: str, token: str, default_owner: str = ""):
        self.target = target
        self.base_url = f"https://github.com/{target}"
        self._github = GitHub(token)

        if is_project_target(target):
            self._delegate = GitHubProjectProvider(target, token, default_owner=default_owner)
            self._owner = self._delegate.owner
            self._repo_name = ""
        else:
            self._delegate = None
            self.repository = target
            self._owner, self._repo_name = target.split("/", 1)

    def describe(self) -> ProviderDescriptor:
        """Describe GitHub resources and capabilities."""
        if getattr(self, "_delegate", None):
            return self._delegate.describe()
        return GITHUB_PROVIDER_DESCRIPTOR

    def get_issue_url(self, key: str) -> str:
        """Return the web URL for an issue key."""
        if self._delegate:
            return self._delegate.get_issue_url(key)
        number = key.lstrip("#")
        return f"{self.base_url.rstrip('/')}/issues/{number}"

    def search(
        self,
        jql: str,
        fields: Optional[list[str]] = None,
        start_at: int = 0,
        max_results: int = 50,
        expand: Optional[list[str]] = None,
    ) -> JiraSearchResult:
        """Search GitHub issues or project board items."""
        if self._delegate:
            return self._delegate.search(jql, fields, start_at, max_results, expand)

        filters, sort_field, sort_direction = _parse_query(jql)
        state = _github_state(filters.get("status"))
        labels = filters.get("labels")
        params: dict = {"state": state, "per_page": 100}
        if labels:
            params["labels"] = labels
        if filters.get("assignee"):
            params["assignee"] = self._assignee_login(filters["assignee"])
        milestone = _milestone_number(self._github, self._owner, self._repo_name, filters.get("milestone"))
        if milestone:
            params["milestone"] = milestone

        issues = list(
            self._github.rest.paginate(
                self._github.rest.issues.list_for_repo,
                owner=self._owner,
                repo=self._repo_name,
                **params,
            )
        )
        issues = [_issue for _issue in issues if _matches_issue(_issue, filters)]
        issues = _sort_issues(issues, sort_field, sort_direction)
        page = issues[start_at : start_at + max_results]
        return JiraSearchResult(
            issues=[self._to_jira_issue(issue) for issue in page],
            total=len(issues),
            startAt=start_at,
            maxResults=max_results,
        )

    def get_current_user(self) -> dict:
        """Return the authenticated GitHub user."""
        if self._delegate:
            return self._delegate.get_current_user()
        user = self._github.rest.users.get_authenticated().parsed_data
        return _github_user_dict(user)

    def list_assignable_users(self, project_key: str, max_results: int = 50) -> list[dict]:
        """Return repository assignees/collaborators assignable to GitHub issues."""
        if self._delegate:
            return self._delegate.list_assignable_users(project_key, max_results)

        users = list(
            self._github.rest.paginate(
                self._github.rest.issues.list_assignees,
                owner=self._owner,
                repo=self._repo_name,
                per_page=100,
            )
        )
        return [_github_user_dict(user) for user in users[:max_results]]

    def find_assignable_users(self, project_key: str, query: str, max_results: int = 20) -> list[dict]:
        """Search assignees by login/name."""
        if self._delegate:
            return self._delegate.find_assignable_users(project_key, query, max_results)

        query_lower = query.casefold()
        users = [
            user
            for user in self.list_assignable_users(project_key, max_results=100)
            if query_lower in user.get("displayName", "").casefold() or query_lower in user.get("accountId", "").casefold()
        ]
        return users[:max_results]

    def search_users(self, query: str, max_results: int = 20) -> list[dict]:
        """Search repository/board users."""
        return self.find_assignable_users(self.target, query, max_results=max_results)

    def list_versions(self, project_key: str) -> list[dict]:
        """Return repository milestones or empty list."""
        if self._delegate:
            return self._delegate.list_versions(project_key)

        milestones = self._github.rest.issues.list_milestones(
            self._owner, self._repo_name, state="all", per_page=100
        ).parsed_data
        return [_milestone_dict(milestone) for milestone in milestones]

    def list_labels(self, project_key: str) -> list[dict]:
        """Return repository or board labels."""
        if self._delegate:
            return self._delegate.list_labels(project_key)

        labels = self._github.rest.issues.list_labels_for_repo(
            self._owner, self._repo_name, per_page=100
        ).parsed_data
        return [_label_dict(label, self._label_issue_count(label)) for label in labels]

    def _label_issue_count(self, label) -> int:
        """Return open+closed issue count for one label."""
        return sum(
            1
            for _ in self._github.rest.paginate(
                self._github.rest.issues.list_for_repo,
                owner=self._owner,
                repo=self._repo_name,
                state="all",
                labels=label.name,
                per_page=100,
            )
        )

    def get_issue_comments(self, key: str, expand_changelog: bool = False) -> list[dict]:
        """Return comments for a GitHub issue key."""
        if self._delegate:
            return self._delegate.get_issue_comments(key, expand_changelog)

        comments = self._github.rest.paginate(
            self._github.rest.issues.list_comments,
            owner=self._owner,
            repo=self._repo_name,
            issue_number=_issue_number(key),
            per_page=100,
        )
        return [_comment_dict(comment) for comment in comments]

    def add_comment(self, key: str, body: str | dict, use_adf: bool = False) -> dict:
        """Add a comment to an issue."""
        if self._delegate:
            return self._delegate.add_comment(key, body, use_adf)

        num = _issue_number(key)
        text = body if isinstance(body, str) else str(body)
        res = self._github.rest.issues.create_comment(self._owner, self._repo_name, num, body=text).parsed_data
        return {"id": str(res.id), "body": res.body}

    def update_issue(self, key: str, fields: dict) -> None:
        """Update supported fields on a repository issue or project item."""
        if self._delegate:
            self._delegate.update_issue(key, fields)
            return

        update_fields = {}
        if "summary" in fields:
            update_fields["title"] = fields["summary"]
        if "title" in fields:
            update_fields["title"] = fields["title"]
        if "description" in fields:
            update_fields["body"] = fields["description"]
        if "labels" in fields:
            update_fields["labels"] = fields["labels"]
        if fields.get("assignee"):
            update_fields["assignees"] = [self._resolve_login(fields["assignee"])]
        if not update_fields:
            raise ValueError("No supported issue fields supplied")
        self._github.rest.issues.update(self._owner, self._repo_name, _issue_number(key), **update_fields)

    def get_transitions(self, key: str) -> list[dict]:
        """Return available status transitions for an issue."""
        if self._delegate:
            return self._delegate.get_transitions(key)

        # For repo issues, state is open or closed
        return [
            {"id": "closed", "name": "Closed", "to": {"name": "Closed"}},
            {"id": "open", "name": "Open", "to": {"name": "Open"}},
        ]

    def list_transitions(self, key: str) -> list[dict]:
        return self.get_transitions(key)

    def transition_issue(self, key: str, transition_id: str, comment: str | None = None) -> None:
        """Transition issue state (open/closed) in repository."""
        if self._delegate:
            self._delegate.transition_issue(key, transition_id, comment)
            return

        num = _issue_number(key)
        target_state = "closed" if transition_id.casefold() in ("closed", "close", "done") else "open"
        self._github.rest.issues.update(self._owner, self._repo_name, num, state=target_state)
        if comment:
            self.add_comment(key, comment)

    def assign_issue(self, key: str, account_id: str) -> None:
        """Assign issue to user login."""
        if self._delegate:
            self._delegate.assign_issue(key, account_id)
            return

        num = _issue_number(key)
        login = self._resolve_login(account_id)
        self._github.rest.issues.update(self._owner, self._repo_name, num, assignees=[login] if login else [])

    def _resolve_login(self, input_val: str) -> str:
        input_clean = input_val.strip().lstrip("@")
        if not input_clean:
            return ""
        users = self.list_assignable_users(self.repository, max_results=100)
        for u in users:
            if u.get("accountId", "").casefold() == input_clean.casefold():
                return u["accountId"]
        for u in users:
            if u.get("displayName", "").casefold() == input_clean.casefold():
                return u["accountId"]
        return input_clean

    def _to_jira_issue(self, issue) -> JiraIssue:
        labels = [label.name for label in issue.labels]
        assignees = getattr(issue, "assignees", []) or []
        assignee = _github_user_dict(assignees[0]) if assignees else None
        reporter = _github_user_dict(issue.user) if getattr(issue, "user", None) else None
        issue_type = _label_value(labels, "type") or "Issue"
        priority = _label_value(labels, "priority") or ""
        return JiraIssue(
            key=f"#{issue.number}",
            fields=JiraIssueField(
                summary=issue.title,
                issuetype={"name": issue_type},
                status={"name": issue.state},
                priority={"name": priority},
                assignee=assignee,
                reporter=reporter,
                updated=_datetime_text(issue.updated_at),
                labels=labels,
            ),
        )

    def _assignee_login(self, value: str | None) -> str:
        """Resolve a JQL assignee value to a GitHub login."""
        if not value:
            return ""
        if value == "*":
            return self.get_current_user().get("accountId", "")
        users = self.find_assignable_users(self.repository, value, max_results=1)
        return users[0].get("accountId", "") if users else value


def _parse_query(query: str) -> tuple[dict[str, str], str, str]:
    query_part, _, order_part = query.partition(" ORDER BY ")
    filters: dict[str, str] = {}
    for condition in [part.strip() for part in query_part.split(" AND ")]:
        if not condition or condition.startswith("project ="):
            continue
        if condition == "assignee = currentUser()":
            filters["assignee"] = "*"
            continue
        field, _, raw_value = condition.partition("=")
        field = field.strip()
        value = raw_value.strip().strip('"')
        if field == "key":
            filters["number"] = value
        elif field == "status":
            filters["status"] = value
        elif field == "assignee":
            filters["assignee"] = value
        elif field == "reporter":
            filters["reporter"] = value
        elif field == "labels":
            filters["labels"] = value
        elif field == "priority":
            filters["priority"] = value
        elif field == "issuetype":
            filters["type"] = value
    if not order_part:
        return filters, "created", "desc"
    parts = order_part.split()
    return filters, parts[0].lower(), parts[1].lower() if len(parts) > 1 else "asc"


def _matches_issue(issue, filters: dict[str, str]) -> bool:
    if filters.get("number") and _issue_number(filters["number"]) != issue.number:
        return False
    labels = [label.name for label in issue.labels]
    if filters.get("priority") and _label_value(labels, "priority") != filters["priority"]:
        return False
    if filters.get("type") and _label_value(labels, "type") != filters["type"]:
        return False
    if filters.get("reporter"):
        user = getattr(issue, "user", None)
        login = getattr(user, "login", "") if user else ""
        name = getattr(user, "name", "") if user else ""
        target = filters["reporter"].casefold()
        if target not in login.casefold() and target not in name.casefold():
            return False
    return True


def _sort_issues(issues: list, field: str, direction: str) -> list:
    reverse = direction == "desc"
    accessors = {
        "created": lambda issue: issue.created_at,
        "updated": lambda issue: issue.updated_at,
        "comments": lambda issue: issue.comments,
    }
    accessor = accessors.get(field)
    return sorted(issues, key=accessor, reverse=reverse) if accessor else issues


def _github_state(status: str | None) -> str:
    if not status:
        return "open"
    normalized = status.casefold()
    if normalized in {"closed", "done"}:
        return "closed"
    if normalized in {"all", "any"}:
        return "all"
    return "open"


def _milestone_number(client: GitHub, owner: str, repo: str, title: str | None) -> str:
    if not title:
        return ""
    milestones = client.rest.issues.list_milestones(owner, repo, state="all", per_page=100).parsed_data
    for milestone in milestones:
        if milestone.title == title:
            return str(milestone.number)
    return ""


def _github_user_dict(user) -> dict:
    name = getattr(user, "name", None) or getattr(user, "login", "")
    login = getattr(user, "login", "")
    return {"accountId": login, "displayName": name, "emailAddress": getattr(user, "email", None) or "-", "active": True}


def _milestone_dict(milestone) -> dict:
    due_on = getattr(milestone, "due_on", None)
    return {
        "id": str(getattr(milestone, "number", "")),
        "name": getattr(milestone, "title", "?"),
        "description": getattr(milestone, "description", "") or "",
        "releaseDate": _date_text(due_on),
        "released": getattr(milestone, "state", "open") == "closed",
        "archived": False,
    }


def _label_dict(label, issue_count: int | str = "") -> dict:
    return {
        "name": getattr(label, "name", "?"),
        "color": getattr(label, "color", "") or "",
        "description": getattr(label, "description", "") or "",
        "issueCount": issue_count,
    }


def _comment_dict(comment) -> dict:
    return {
        "author": {"displayName": getattr(comment.user, "login", "unknown")},
        "created": _datetime_text(getattr(comment, "created_at", None)),
        "body": getattr(comment, "body", ""),
    }


def _label_value(labels: list[str], prefix: str) -> str:
    for label in labels:
        normalized = label.casefold()
        for separator in (":", "/"):
            token = f"{prefix}{separator}"
            if normalized.startswith(token):
                return label[len(token) :]
    return ""


def _issue_number(key: str) -> int:
    value = key.rsplit("#", 1)[-1].strip()
    if value.upper().startswith("GH-"):
        value = value[3:]
    return int(value)


def _datetime_text(value) -> str:
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _date_text(value) -> str:
    if not value:
        return "-"
    return value.date().isoformat()
