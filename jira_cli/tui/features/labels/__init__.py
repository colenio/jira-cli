"""Label resource views for the Jira TUI."""

from .service import list_project_labels
from .widgets import LabelDetailWidget, LabelTableWidget

__all__ = ["LabelDetailWidget", "LabelTableWidget", "list_project_labels"]
