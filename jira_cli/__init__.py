"""Jira CLI — modular command-line interface for Jira issue management."""

from importlib.metadata import PackageNotFoundError, version

try:
	__version__ = version("colenio-jira-cli")
except PackageNotFoundError:
	__version__ = "0+unknown"

__author__ = "Colenio"
