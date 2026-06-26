# Distribution

This document is for maintainers and owners.

## Release Model

- Source hosted in GitHub repository colenio/jira-cli.
- Publishing via GitHub Actions + PyPI Trusted Publisher.
- Install/execute target for users: uvx colenio-jira-cli ...

## Release Steps

1. Ensure tests/lint pass.
2. Bump version in pyproject.toml.
3. Create and push tag (for example v0.1.0).
4. GitHub workflow builds and publishes to PyPI.
5. Validate package metadata on PyPI (project links, classifiers, entry points).

## Notes

- Trusted Publisher handles auth for publishing, not project metadata.
- PyPI project links are controlled by project.urls in pyproject.toml.
