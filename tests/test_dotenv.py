"""Tests for DotEnv parsing and quote stripping."""

import os
from pathlib import Path
from jira_cli.dotenv import DotEnv


def test_dotenv_strips_double_and_single_quotes(tmp_path: Path, monkeypatch):
    env_file = tmp_path / "local.env"
    env_file.write_text(
        'GH_PROJECT="colenio/21"\n'
        "JIRA_PROJECT='PROJ'\n"
        "PLAIN_VAL=unquoted_value\n"
        'EMPTY_QUOTES=""\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GH_PROJECT", raising=False)
    monkeypatch.delenv("JIRA_PROJECT", raising=False)
    monkeypatch.delenv("PLAIN_VAL", raising=False)
    monkeypatch.delenv("EMPTY_QUOTES", raising=False)

    loaded = DotEnv().load()

    assert loaded.get("GH_PROJECT") == "colenio/21"
    assert loaded.get("JIRA_PROJECT") == "PROJ"
    assert loaded.get("PLAIN_VAL") == "unquoted_value"
    assert loaded.get("EMPTY_QUOTES") == ""

    assert os.environ.get("GH_PROJECT") == "colenio/21"
    assert os.environ.get("JIRA_PROJECT") == "PROJ"
