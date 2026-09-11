"""Version resource views for the Jira TUI."""

from .service import list_project_versions
from .widgets import VersionDetailWidget, VersionTableWidget

__all__ = ["VersionDetailWidget", "VersionTableWidget", "list_project_versions"]
