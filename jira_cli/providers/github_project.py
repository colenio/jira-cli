"""GitHub Projects V2 provider powered by GraphQL via githubkit."""

from __future__ import annotations

import re
from typing import Any, Optional

from githubkit import GitHub

from jira_cli.models import JiraIssue, JiraIssueField, JiraSearchResult

from .base import ActionDescriptor, FilterDescriptor, ProviderDescriptor, ResourceDescriptor, SortDescriptor


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
            name="github-project",
            query_language="GitHub project filter",
            resources=(
                ResourceDescriptor(
                    kind="issues",
                    fields=("key", "summary", "status", "assignee", "labels", "updated", "issuetype"),
                    filters=(
                        FilterDescriptor(name="status", field="status", special_values=status_names),
                        FilterDescriptor(name="assignee", field="assignee", special_values=("me",)),
                        FilterDescriptor(name="label", field="labels"),
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

        labels_nodes = content.get("labels", {}).get("nodes", []) if isinstance(content, dict) else []
        labels_list = [l["name"] for l in labels_nodes if isinstance(l, dict) and "name" in l]

        issuetype_name = "Story" if item_type == "ISSUE" else ("PullRequest" if item_type == "PULL_REQUEST" else "Draft")

        fields = JiraIssueField(
            summary=content.get("title", "Untitled") if isinstance(content, dict) else "Untitled",
            status={"name": status_name},
            assignee=assignee_dict,
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
        """Return assignees present on project items or current user."""
        user = self.get_current_user()
        users = [user]
        items = self._fetch_all_items()
        seen = {user["accountId"]}
        for item in items:
            content = item.get("content") or {}
            assignees = content.get("assignees", {}).get("nodes", []) if isinstance(content, dict) else []
            for a in assignees:
                if isinstance(a, dict) and "login" in a:
                    login = a["login"]
                    if login not in seen:
                        seen.add(login)
                        users.append({"accountId": login, "displayName": a.get("name") or login, "active": True})
        return users[:max_results]

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
    status_name = status_val.get("name") if isinstance(status_val, dict) else "No Status"

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

    if "label" in filters:
        target_label = filters["label"].casefold()
        labels = content.get("labels", {}).get("nodes", []) if isinstance(content, dict) else []
        matched = any(target_label == l.get("name", "").casefold() for l in labels if isinstance(l, dict))
        if not matched:
            return False

    return True
